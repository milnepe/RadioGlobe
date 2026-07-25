# Activity Diagram: Moving the Reticule to a New Station

This diagram traces what happens when the user spins the globe to a new
reticule position, from the encoder's raw SPI reading through to a new
station playing. It assumes the origin has already been calibrated
(`zero()` has been called), so `encoders.get_readings()` returns an
absolute `(lat, lon)` position rather than a raw, uncalibrated one.

It complements [ARCHITECTURE.md](../ARCHITECTURE.md) — see
[§5 Flow A](../ARCHITECTURE.md#5-key-data-flows) for the prose version of
the happy path, and [§11 Improvement A](../ARCHITECTURE.md#11-suggested-improvements)
for the unguarded-`IndexError` bug shown below.

## Legend

- `[ box ]` — an action: a function call or state change
- `<< box >>` — a decision point
- `|` / `v` — control flows downward along the main spine
- boxes to the right of the spine are the **no** branch of the decision
  directly above them; the **yes** branch continues straight down
- `LOOP-A` — a jump target; branches that say "back to LOOP-A" return
  control to that point rather than falling off the page

## Diagram

```
Assumption: origin has already been calibrated -- zero() has been called,
so encoders.get_readings() returns the absolute (lat, lon) position.

                              ( start )
                                 |
                                 v
      +----------------------------------------------------+
      |  User spins the globe to a new reticule position   |
      +----------------------------------------------------+
                                 |
                                 v
      +==== LOOP-A =======================================+
                                 |
                                 v
      +----------------------------------------------------+
      |           run_encoder() polls SPI bus 0            |
      |        (background task, runs every 200 ms)        |
      +----------------------------------------------------+
                                 |
                                 v
      +----------------------------------------------------+
      |    check_parity() validates the raw SPI reading    |
      +----------------------------------------------------+
                                 |
                                 v
      +----------------------------------------------------+
      |                  << parity OK? >>                  |
      +----------------------------------------------------+
                                 |    no
                                 |    +----------------------------------+
                                 |    |       Discard the reading.       |
                                 |    +----------------------------------+
                                 |    (loops back to LOOP-A on the
                                 |     next 200 ms SPI poll)
                                 v   (yes)
      +----------------------------------------------------+
      |       Update self.latitude / self.longitude        |
      |        set encoders.updated (asyncio.Event)        |
      +----------------------------------------------------+
                                 |
                                 v
      +----------------------------------------------------+
      |     _encoder_loop() wakes on encoders.updated;     |
      |                  clears the event                  |
      +----------------------------------------------------+
                                 |
                                 v
      +----------------------------------------------------+
      |          coords = encoders.get_readings()          |
      +----------------------------------------------------+
                                 |
                                 v
      +----------------------------------------------------+
      |         cities = find_cities_near(coords,          |
      |         look_around_offsets, cities_index)         |
      +----------------------------------------------------+
                                 |
                                 v
      +----------------------------------------------------+
      |             cities found AND encoders              |
      |                not already latched?                |
      +----------------------------------------------------+
                                 |    no
                                 |    +----------------------------------+
                                 |    |   No city near this position.    |
                                 |    |     Encoders stay unlatched;     |
                                 |    |      no station is played.       |
                                 |    +----------------------------------+
                                 |    ----> back to LOOP-A
                                 v   (yes)
      +----------------------------------------------------+
      |   encoders.latch(*coords, stickiness=STICKINESS)   |
      |           freezes the reticule position            |
      +----------------------------------------------------+
                                 |
                                 v
      +----------------------------------------------------+
      |         city = cities[0]  (closest match)          |
      |        jog_idx = 0   |   LED flashes green         |
      +----------------------------------------------------+
                                 |
                                 v
      +----------------------------------------------------+
      |          stations = get_stations_by_city(          |
      |                 stations_info, city)               |
      +----------------------------------------------------+
                                 |
                                 v
      +----------------------------------------------------+
      |           << stations list non-empty? >>           |
      +----------------------------------------------------+
                                 |    no
                                 |    +----------------------------------+
                                 |    |    ** Known bug, unguarded **    |
                                 |    |      station = stations[0]       |
                                 |    |       raises IndexError --       |
                                 |    |     _encoder_loop() crashes;     |
                                 |    |       app needs a restart.       |
                                 |    |       See ARCHITECTURE.md,       |
                                 |    |          Improvement A.          |
                                 |    +----------------------------------+
                                 |    (( end: crash ))
                                 v   (yes)
      +----------------------------------------------------+
      |               station = stations[0]                |
      +----------------------------------------------------+
                                 |
                                 v
      +----------------------------------------------------+
      |          display.update(coords, city, 0,           |
      |                 station[0], False)                 |
      +----------------------------------------------------+
                                 |
                                 v
      +----------------------------------------------------+
      |          audio_player.play(city, station)          |
      +----------------------------------------------------+
                                 |
                                 v
      +----------------------------------------------------+
      |         _start_monitor_stream(station[1])          |
      |     (watches for stream failure -- see Flow A      |
      |                in ARCHITECTURE.md)                 |
      +----------------------------------------------------+
                                 |
                                 v
                    (( end: new station is playing ))
```

## What happens if a station isn't found at the new location?

There are two distinct cases, and the codebase handles them very
differently:

**1. No city is found near the new position (the common case).**
`find_cities_near()` returns an empty list. Because the decision
`cities found AND encoders not already latched?` is now false, nothing
is latched, no display update happens, and no station starts playing.
`_encoder_loop()` simply loops back to `LOOP-A` and keeps waiting on
`encoders.updated` — the app stays exactly where it was (still
unlatched, still showing whatever it showed before, or the calibrate
screen if this is the first move since boot). As soon as the reticule
drifts over a point close enough to a known city, the next `updated`
event picks it up and plays it. This is the expected, everyday
behaviour of "spinning between cities" — nothing is ever a hard error.

**2. A city is found, but its station list is empty.** This can only
happen with malformed data — a city key present in `stations.json` with
no (or an empty) `"urls"` entry, e.g. from a partial database update.
Unlike case 1, this path is **not** guarded in the current code:
`self.state.station = self.state.stations[0]` runs unconditionally
right after the latch, so an empty list raises an unhandled
`IndexError`. Because this happens inside `_encoder_loop()`, that task
dies — reticule movement stops working until the app is restarted. This
is a known, documented bug (see
[ARCHITECTURE.md §11, Improvement A](../ARCHITECTURE.md#11-suggested-improvements)),
along with a second, identical unguarded call site in `_dial_loop()`
and the proposed fix (guard on `if not self.state.stations` before
indexing).
