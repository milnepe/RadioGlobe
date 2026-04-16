# Reticule to Station: Code Path Walkthrough

How the RadioGlobe goes from a physical globe movement to finding a station to play.

---

## 1. Hardware: Encoders → `PositionalEncoders.run_encoder()` (`positional_encoders.py:74`)

The two rotary encoders (latitude and longitude) are read over **SPI** every 200ms in a polling loop. Each reads 2 bytes from SPI devices 0 and 1 on bus 0, checks parity, and shifts right 6 bits to get the raw position value.

```
read_spi()  →  check_parity()  →  readings[0..1]
```

When the globe moves **and there's no latch**, the new `latitude`/`longitude` values are stored and `self.updated` (an `asyncio.Event`) is **set** (`positional_encoders.py:85`).

**Stickiness**: Once latched, the encoder only fires `updated` again if the physical movement exceeds `STICKINESS=2` encoder counts — this suppresses jitter.

---

## 2. `_encoder_loop()` wakes up (`main.py:232`)

`_encoder_loop` sits in an `await self.encoders.updated.wait()` — it wakes as soon as the event fires, then clears it and proceeds.

```python
coords = self.encoders.get_readings()   # applies latitude/longitude offsets
zone   = look_around(coords, self.look_around_offsets)
self.state.cities = self._find_all_cities(zone, self.cities_info)
```

`get_readings()` adds the calibration offsets and wraps at 1024 (`positional_encoders.py:31`).

---

## 3. `look_around()` — fuzzy search (`database.py:67`)

Expands `coords` into a list of neighbouring grid squares using **pre-computed offsets** (built once at startup via `build_look_around_offsets(FUZZINESS=5)`). At fuzziness 5 this produces 25+ offsets, so the search covers a patch of grid squares around the current position.

---

## 4. City index lookup — `build_cities_index` / `_find_all_cities` (`database.py:22`, `main.py:152`)

At startup, `build_cities_index()` maps every city in `stations.json` to a grid coordinate `(lat_idx, lon_idx)` using:

```python
latitude  = round((coords["n"] + 180) * 1024 / 360)
longitude = round((coords["e"] + 180) * 1024 / 360)
```

`_find_all_cities` walks the `zone` list, checks each grid square against this index, and collects matching city names.

---

## 5. Latching (`main.py:242`)

If cities were found **and the encoder isn't already latched**:

1. **LED flashes green**
2. `encoders.latch(*coords, stickiness=STICKINESS)` — freezes the encoder position, sets `latch_stickiness=2`. Future SPI readings are compared against this; only a movement >2 counts breaks the latch.
3. `state.city = cities[0]`, `state.jog_idx = 0`
4. `state.stations = get_stations_by_city(stations_info, city)` — looks up the city in `stations.json` and returns a list of `(name, url)` tuples
5. `state.station = stations[0]` — picks the first station

---

## 6. Display update (`main.py:263`)

```python
coords = self._get_coords_by_city(self.state.city)  # real lat/lon from stations.json
self.display.update(coords, city, 0, station[0], False)
```

The display shows the city name and station name on the LCD.

---

## Summary diagram

```
Physical rotation
      │
      ▼
SPI poll (200ms)  positional_encoders.py:77
      │  check_parity → raw_reading >> 6
      │  latch_stickiness check
      ▼
encoders.updated.set()          ← asyncio.Event
      │
      ▼
_encoder_loop wakes              main.py:232
      │
      ├─ get_readings()           apply offsets, wrap at 1024
      │
      ├─ look_around()            database.py:67  — expand to 25 grid squares
      │
      ├─ _find_all_cities()       main.py:152     — check against cities index
      │
      └─ if cities found & not latched:
            ├─ encoders.latch()   freeze position with stickiness
            ├─ get_stations_by_city()  database.py:79  — (name, url) list
            ├─ state.station = stations[0]
            └─ display.update()   show city + station name
```

At this point `audio_player.play()` is called to start streaming the station.

---

## Potential improvements

### 1. Merge `look_around` + city search into one pass, eliminating the intermediate list (biggest win)

Currently the encoder loop always does two full passes:
- `look_around()` allocates a list of 25+ tuples
- `_find_all_cities()` then iterates the whole list doing dict lookups

The full list of nearby cities must be preserved — it is needed when the user jogs through cities in city-mode, and cities near each other on the globe should all appear. However, because `build_look_around_offsets` builds offsets innermost-first, the **first city found is naturally the closest to the reticule**, so the list ordering is meaningful and should be maintained.

The two passes can be merged into one, eliminating the intermediate `zone` list allocation entirely:

```python
def find_cities_near(origin: tuple, offsets: list, cities_index: dict) -> list:
    lat, lon = origin
    seen = set()
    cities = []
    for dx, dy in offsets:
        coord = ((lat + dx) % ENCODER_RESOLUTION, (lon + dy) % ENCODER_RESOLUTION)
        if coord in cities_index:
            for city in cities_index[coord]:
                if city not in seen:
                    seen.add(city)
                    cities.append(city)
    return cities   # ordered closest-first because offsets are innermost-first
```

This collects all nearby cities (preserving proximity order) while avoiding the 25-tuple intermediate list. In `_encoder_loop` the two lines become one:

```python
self.state.cities = find_cities_near(coords, self.look_around_offsets, self.cities_info)
```

### 2. Cache `_get_coords_by_city` result in `AppState`

`_get_coords_by_city` is a `stations_info` dict lookup called in `_encoder_loop`, `_dial_loop`, `_update_volume`, `_update_volume_level`, and `_monitor_stream` — every time the display needs updating. The city doesn't change between those calls.

Store it when the city is set:

```python
self.state.city = self.state.cities[0]
self.state.coords = self._get_coords_by_city(self.state.city)   # cache it once
```

Then replace every `self._get_coords_by_city(self.state.city)` call site with `self.state.coords`. Add `coords: Optional[Coordinate] = None` to `AppState`.

### 3. Skip the lookup when coords haven't changed

The `updated` event fires whenever the SPI reading changes, but if the globe is vibrating around the same position the coords from `get_readings()` (after offset) may be identical to the previous call. A one-line guard skips the whole search:

```python
coords = self.encoders.get_readings()
if coords == self._last_coords:
    continue
self._last_coords = coords
```

Store `_last_coords: Optional[tuple] = None` on `App`. This is especially useful before latching, when the encoder is firing freely at 5Hz.

### 4. Remove dead code in `database.py`

`get_found_cities` (`database.py:88`) and `get_stations_info` (`database.py:106`) are never called — they are superseded by `_find_all_cities` and `get_stations_by_city`. Delete both.

### 5. Minor: `jog_idx = 0` is set twice in `_encoder_loop`

`main.py:248` and `main.py:255` both set `self.state.jog_idx = 0` with no code between them. One is redundant.

---

### Summary table

| Change | Where | Benefit |
|---|---|---|
| Merge `look_around` + city search, closest-first order | `database.py` | Eliminates 25-tuple allocation; single pass; proximity ordering preserved |
| Cache coords in `AppState` | `main.py` | Removes repeated dict lookups on every display update |
| Skip search when coords unchanged | `_encoder_loop` | Eliminates work at 5Hz when globe is still |
| Delete `get_found_cities`, `get_stations_info` | `database.py` | Remove dead code |
| Remove duplicate `jog_idx = 0` | `_encoder_loop:255` | Trivial cleanup |
