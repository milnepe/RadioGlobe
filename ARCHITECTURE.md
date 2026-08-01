# RadioGlobe Architecture

This document is a guide for developers joining the project. It explains the physical hardware, how the software maps onto it, and what each module does. It also surfaces concrete improvement suggestions to make the code easier to maintain and extend.

This is not the setup guide — that's [README.md](README.md). For a brief asyncio design sketch, see [docs/DESIGN.md](docs/DESIGN.md). For how to submit changes, see [CONTRIBUTING.md](CONTRIBUTING.md).

---

## Table of Contents

1. [What RadioGlobe Is — Physical Context](#1-what-radioglobe-is--physical-context)
2. [Repository Layout](#2-repository-layout)
3. [Architecture Overview](#3-architecture-overview)
4. [Module Reference](#4-module-reference)
5. [Key Data Flows](#5-key-data-flows)
6. [State Management](#6-state-management)
7. [Concurrency Model](#7-concurrency-model)
8. [Configuration Reference](#8-configuration-reference)
9. [Testing](#9-testing)
10. [Contributing](#10-contributing)
11. [Suggested Improvements](#11-suggested-improvements)
12. [What's Already Good](#12-whats-already-good)

---

## 1. What RadioGlobe Is — Physical Context

Before the code makes sense, you need to picture the object.

A physical globe sits in a cradle. The cradle has a pivoting reticule — a crosshair arm — that the user positions over any point on the globe's surface. Two 10-bit absolute rotary encoders read the reticule's latitude and longitude as integer values from 0 to 1023. There is no "home position" — the encoders are absolute, not incremental, so they survive power cycles without recalibration (as long as the globe hasn't been physically moved).

Spinning the globe to point at London causes the software to look up London's radio stations and start playing one. A rotary dial on the base lets the user cycle through stations or cities. Four push-buttons handle volume, calibration, and power. A 20×4 character LCD and an RGB LED provide feedback.

The Raspberry Pi 4B runs Raspberry Pi OS Bookworm Lite. Audio plays through VLC via either the 3.5mm jack or Bluetooth.

### Hardware-to-Module Mapping

| Physical Component | Interface | GPIO / Address | Module |
|---|---|---|---|
| Globe reticule encoders (lat, lon) | SPI bus 0, devices 0 & 1 | — | `positional_encoders.py` |
| Station/city select dial | GPIO quadrature (kernel `rotary_encoder` driver + evdev) | Pins 17 (clock), 18 (direction) | `dial.py` |
| Jog button (mode toggle) | GPIO | Pin 27 | `buttons.py` |
| Top button (volume up) | GPIO | Pin 5 | `buttons.py` |
| Mid button (calibrate / shutdown) | GPIO | Pin 6 | `buttons.py` |
| Bottom button (volume down) | GPIO | Pin 12 | `buttons.py` |
| 20×4 character LCD | I2C | Bus 1, address 0x27 | `display.py` |
| RGB status LED | GPIO | R=22, G=23, B=24 | `rgb_led.py` |
| Audio output | VLC / PulseAudio | 3.5mm / Bluetooth | `audio_async.py` |

### Button Operations

| Button | Short Press | Long Press |
|---|---|---|
| **Jog** (27) | Toggle station / city mode | — |
| **Top** (5) | Volume +10 | Set volume to 80 |
| **Mid** (6) | Calibrate encoders to 0,0 | Shutdown (`sudo poweroff`) |
| **Bottom** (12) | Volume −10 | Mute (volume to 0) |

---

## 2. Repository Layout

```
RadioGlobe/
├── radioglobe/                       # Python application package
│   ├── main.py                       # App class: entry point, hardware orchestration, main loop
│   ├── app_state.py             # AppState dataclass: station/city selection state
│   ├── navigation.py            # Navigator: owns AppState + station/city data, no hardware deps
│   ├── radio_config.py               # App-behavior tuning constants (see §8)
│   ├── database.py                   # Pure functions: station/city spatial index
│   ├── coordinates.py                # Coordinate value object (lat/lon → display string)
│   ├── audio_async.py                # AudioPlayer: wraps python-vlc directly
│   ├── display.py              # 20×4 I2C LCD driver
│   ├── dial.py                 # evdev reader for kernel rotary-encoder device (station/city dial)
│   ├── dial_button.py (deleted)          # Combined dial + button (historical, unused in prod)
│   ├── positional_encoders.py  # SPI encoders → lat/lon + latch mechanism
│   ├── buttons.py              # Multi-button manager with short/long press
│   ├── rgb_led.py              # RGB LED flash controller
│   └── streaming/                    # Lab: historical streaming implementations
│       ├── streaming.py              # Oldest: subprocess + amixer volume
│       ├── streaming_cvlc.py         # cvlc subprocess wrapper (used in test scripts)
│       ├── python_vlc_streaming.py   # python-vlc Streamer class (informed audio_async.py)
│       ├── async_streamer.py         # Experimental: async playlist resolver via aiohttp
│       └── files.py                  # JSON loader helper for test scripts
│
├── tests/                            # Unit tests (run without hardware) + integration/ subfolder
│   ├── get_stations_by_city_test.py
│   ├── navigation_test.py
│   ├── buttons_test.py
│   ├── ...                           # See §9 Testing for the full list
│   └── integration/                  # Hardware / manual scripts — see tests/integration/README.md
│
├── stations/
│   └── stations.json                 # Radio station database (~705 KB, 500+ cities)
│
├── services/
│   └── radioglobe.service            # systemd user service definition
│
├── docs/
│   └── DESIGN.md                     # Asyncio design notes
│
├── board/                            # PCB Gerber files and schematics
├── pyproject.toml                    # Package config and dev dependencies
├── requirements.txt                  # Runtime dependencies (includes git-sourced packages)
├── Makefile                          # Build, deploy, release targets
└── install.sh                        # Installation script for Raspberry Pi
```

**Key notes:**
- `streaming/` is a development lab. The production audio code is `audio_async.py`, which does not import from `streaming/`.
- `tests/` contains unit tests (runnable on any machine) alongside `tests/integration/`, which holds the hardware integration scripts.

---

## 3. Architecture Overview

The application is a single-process asyncio program. One event loop runs on the main thread, and all hardware I/O runs as asyncio Tasks or is bridged into the loop from GPIO interrupt threads.

**The central concept is the reticule position.** `PositionalEncoders.run_encoder()` polls SPI every 50ms. While unlatched, every successful reading sets an `asyncio.Event` (`encoders.updated`); the `_encoder_loop()` task wakes on that event, searches the spatial city index for any city near the current position, and if one is found, latches and starts playing its radio stream. Once latched, the event only fires again when the reticule drifts far enough to unlatch. The dial and buttons adjust the experience once a city is latched.

**Two operating modes** are toggled by the jog button:
- `station` mode — the dial cycles through stations within the current city
- `city` mode — the dial cycles through other nearby cities, reloading the first station for each

**The latch mechanism** prevents jitter. Once a city is found, the encoder's raw position is frozen until the user moves the reticule more than `STICKINESS` encoder steps away. Without this, the station would change continuously while the user browses with the dial.

### Module Dependency Graph

```mermaid
graph TD
    main["main.py\n(App)"]

    main --> positional["positional_encoders.py\nSPI → lat/lon + latch"]
    main --> dial["dial.py\nkernel rotary-encoder + evdev"]
    main --> buttons["buttons.py\nGPIO button manager"]
    main --> display["display.py\nI2C LCD display"]
    main --> led["rgb_led.py\nGPIO LED"]
    main --> audio["audio_async.py\nVLC audio player"]
    main --> nav["navigation.py\n(Navigator)"]
    main --> database["database.py\nPure functions"]
    main --> coordinates["coordinates.py\nCoordinate type"]

    nav --> appstate["app_state.py\n(AppState)"]
    nav --> database
    nav --> coordinates

    database --> stations[("stations/stations.json")]
    audio --> vlc[("python-vlc")]
    positional --> spidev[("spidev")]
    display --> i2c[("liquidcrystal_i2c")]
    buttons --> gpio[("lgpio / RPi.GPIO")]
    dial --> input[("evdev /dev/input/eventN")]
    led --> gpio
```

`App` still imports `get_stations_by_city` (`database.py`) directly — used
in `_encoder_loop()`/`_dial_loop()` to fetch a city's station list before
handing it to `self.nav.state.select_station()` — and `Coordinate`
(`coordinates.py`) for the shutdown-display fallback, so those two edges
aren't purely routed through `Navigator`. `match_saved_station()` moved
fully into `Navigator.load_state()` in a follow-up — see §4.3.

The `streaming/` directory is intentionally omitted — none of its modules are imported by the main application.

---

## 4. Module Reference

### 4.1 `main.py` — App Controller

The `App` class is the central controller, but a much thinner one since the
2026-07-30 decoupling refactor (see git history from
`feature/decouple-database-helpers` through `feature/extract-navigator`).
`__init__` instantiates the 6 hardware wrapper objects plus a single
`Navigator` (`self.nav` — §4.3), which owns all station/city data and
navigation state. `App` itself now handles only: hardware construction, the
two event-driven loops, button dispatch, and `run()`.

`run()` wires up button definitions, restores any saved state, and then
starts and gathers the `_encoder_loop()` and `_dial_loop()` tasks — these
two event-driven loops are the app's actual "main loop."

**State** lives on `self.nav.state` (an `AppState` — §4.2); `App` no longer
holds it directly. `save_state()`/`load_state()` are thin wrappers around
`self.nav.save_state()`/`self.nav.load_state()` (§4.3) — `App`'s only job
is passing `self.encoders.get_calibration()`'s dict through to
`self.nav.save_state()`, and passing `load_state()`'s returned dict through
to `self.encoders.restore_calibration()`. `App` doesn't know or care what's
in that dict — `PositionalEncoders` owns its own calibration fields
(`latitude`/`longitude`/`latitude_offset`/`longitude_offset`) and their
dict representation entirely (§4.5); `Navigator` owns the JSON
(de)serialisation and `AppState` reconstruction (§4.3). On boot, if a saved
state is found, the latch is restored and the last station resumes playing
immediately (warm-restart path).

**Key methods:**

| Method | Purpose |
|---|---|
| `run()` | Restore saved state, then start and gather `_encoder_loop()` and `_dial_loop()` |
| `_encoder_loop()` | Wake on `encoders.updated`, ask `self.nav.refresh_nearby_cities()` for nearby cities, latch via `self.nav.select_city()` and start playback when one is found |
| `_dial_loop()` | Wake on `dial.queue`, delegate to `self.nav.next_station()` or `self.nav.next_city_and_select_station()`, update playback |
| `save_state()` | Pass `self.encoders.get_calibration()` to `self.nav.save_state()` (§4.3) |
| `load_state()` | Pass `self.nav.load_state()`'s (§4.3) returned dict to `self.encoders.restore_calibration()` |
| `_update_volume(delta)` | Adjust volume by delta, briefly show level on display |
| `_update_volume_level(level)` | Set volume to an absolute level, briefly show on display |
| `_play_station()` | Show and play `self.nav.state.station` (`display.show_station()` + `audio_player.play()`), returning the URL played. The one place that unpacks the `(name, url)` station tuple — every call site (`_encoder_loop`, `_dial_loop`, `run()`'s warm-restart path, `_monitor_stream`'s retry path) used to repeat `station[0]`/`station[1]` indexing inline |
| `_start_monitor_stream(url)` | Cancel any running monitor task, start a fresh `_monitor_stream` task, store the handle |
| `_monitor_stream(expected_url)` | Check VLC state every 3 s; on failure, flash LED red, drop the failed station (`self.nav.remove_failed_station()`), and play the next; exits once a station plays cleanly, all stations are exhausted, or the user switches away |
| `_handle_short_jog` / `_handle_long_jog` | Jog button handlers — short press calls `self.nav.switch_mode()` |
| `_handle_short_top` / `_handle_long_top` | Top button handlers |
| `_handle_short_mid` / `_handle_long_mid` | Mid button handlers |
| `_handle_short_bottom` / `_handle_long_bottom` | Bottom button handlers |
| `_on_jog_press` / `_on_sound_press` / `_on_mid_press` | Immediate press-down LED feedback |

Navigation logic that used to live here directly — `next_station`,
`next_city`, `switch_mode`, station-list bookkeeping, coordinate lookup,
and (as of the 2026-08-01 navigation-cleanup pass) city latching/selection
— now lives entirely on `Navigator` (§4.3). `App` performs zero direct
mutations of `nav.state` in either event loop; every mutation goes through
a named `Navigator` method.

**Non-obvious details:**
- `self.nav.state.city` is passed to `display.show_station()`/`display.update()` as a raw string (e.g. `"London,GB"`). The display truncates it to 20 characters before centering.
- `save_state()` always writes `"latch": True`; on `load_state()` this causes the app to immediately resume playing the last station on next boot.
- If the warm-restart state is incomplete (city or station is `None` after `load_state()`), the app logs a warning, clears the latch, and falls back to calibrate mode rather than crashing.
- `load_state()` no longer reaches into `Navigator`'s internals at all — an earlier version of this refactor had `App.load_state()` do `self.nav.state = AppState(...)` directly, but that was moved into `Navigator.load_state()` itself in a follow-up (§4.3), once it became clear the only real obstacle (needing `self.encoders`) could be solved by passing/returning plain dicts instead of a hardware object.
- `save_state()`/`load_state()` similarly no longer reach into
  `PositionalEncoders`' internal fields — an earlier version read/wrote
  `self.encoders.latitude`/`.longitude`/`.latitude_offset`/`.longitude_offset`
  directly (plus setting `.latch_stickiness = True` by hand on restore).
  `get_calibration()`/`restore_calibration()` (§4.5) were added so `App`
  only ever passes an opaque dict through, the same pattern already used
  for `Navigator`.

---

### 4.2 `app_state.py` — Selection State

A small dataclass holding the app's mutable station/city selection state,
owned by `Navigator` (§4.3) rather than `App` directly. Split out of
`main.py` into its own module specifically so it has no hardware
dependency: `main.py` imports `RPi.GPIO` at module level and can't be
imported off a Raspberry Pi at all, so anything meant to be unit-testable
has to live somewhere that doesn't transitively pull that in.

| Field | Type | Meaning |
|---|---|---|
| `stations` | `list[(name, url)]` | Stations for the current city |
| `station` | `tuple \| None` | Currently playing station |
| `station_idx` | `int` | Index of `station` within `stations` |
| `cities` | `list[str]` | Cities found in the current search zone |
| `city` | `str \| None` | Currently selected city (e.g. `"London,GB"`) |
| `city_idx` | `int` | Index of `city` within `cities` |
| `mode` | `str` | `"station"` or `"city"` |

**Methods:**
- `is_complete() -> bool` — whether both `city` and `station` are set. Used throughout `main.py` and `navigation.py` as the guard for "is there anything to display/play/navigate."
- `select_station(stations) -> bool` — sets `self.stations`, resets `self.station_idx = 0`, and if the list is non-empty, `self.station = stations[0]`; returns whether a station was selected.

Until 2026-08-01, `station_idx`/`city_idx` were a single shared `jog_idx`
field (station index in `MODE_STATION`, city index in `MODE_CITY`,
recomputed by `Navigator.switch_mode()` on every mode change via a linear
search). Splitting it into two independent fields removed that recompute
entirely and let `select_station()` always reset its own index safely —
see the correctness note in §4.3.

Unit-tested directly (`tests/app_state_test.py`) — pure data, no mocking needed.

---

### 4.3 `navigation.py` — Navigator

`Navigator` owns everything about *what city/station is currently selected
and how to change it* — the pure decision-making half of what used to be
`App`. Like `app_state.py`, it has no hardware dependency, so it's
constructible and unit-testable off a Pi the same way `database.py` always
was (`tests/navigation_test.py` builds one against an in-memory fixture
station dict, no mocking).

**Owns:**
- `self.state: AppState` (§4.2)
- `self.stations_info`, `self.cities_info`, `self.look_around_offsets` — built in `__init__` from `load_stations()`/`build_cities_index()`/`build_look_around_offsets()` (§4.4), defaulting to `STATIONS_JSON`/`FUZZINESS` but overridable via constructor args — this is how the test suite avoids loading the real 12.7k-entry `stations.json`

**Methods:**

| Method | Purpose |
|---|---|
| `current_coords` (property) | `Coordinate` for `self.state.city`, or `None` if no city is selected — replaces a manually-maintained cache `App` used to keep (the old `_current_coords` attribute) |
| `find_cities_near(origin)` | Thin wrapper around `database.find_cities_near()` using `self.look_around_offsets`/`self.cities_info` |
| `refresh_nearby_cities(coords)` | Recompute `self.state.cities` via `find_cities_near(coords)` and return it |
| `select_city()` | Latch onto the closest nearby city (`self.state.cities[0]`) and select its first station; returns `False` (state untouched) if there are no nearby cities or the closest one has no stations. Used by `App._encoder_loop()`'s latch path |
| `next_city_and_select_station(direction)` | Cycle to the next/previous city (`next_city()`) and select its first station; returns `False` (previous station keeps playing) if the new city has no stations. Used by `App._dial_loop()`'s `MODE_CITY` branch |
| `next_station(direction)` | Cycle `station_idx` within `self.state.stations` |
| `next_city(direction)` | Cycle `city_idx` within `self.state.cities` |
| `switch_mode()` | Toggle `self.state.mode` — no index recompute needed; `station_idx`/`city_idx` are independent fields, each kept correct by whichever method owns it |
| `remove_failed_station()` | Drop the current station from the session list and advance to the next by `station_idx`; called from `App._monitor_stream()` on playback failure |
| `save_state(encoder_offsets, cache)` | Serialise `self.state` + `encoder_offsets` (a plain dict — keys `lat`/`lon`/`lat_offset`/`lon_offset` — supplied by the caller, since `Navigator` has no hardware access of its own) to `cache` as JSON |
| `load_state(cache)` | Restore `self.state` from `cache`, re-querying/validating the saved city and station against the live `stations_info`; returns the saved encoder offsets as a plain dict (or `{}` if no cache file exists) for the caller to apply |

**What deliberately stayed on `App` instead:** hardware construction
(`App.__init__` still builds all 6 hardware wrappers directly as a flat
list — not wrapped in a factory, since that would add indirection serving
testability/hardware-swappability, which wasn't the goal of this refactor),
the two event loops (as timing/LED/logging orchestration around `Navigator`
calls), and button dispatch/`run()`.

`save_state()`/`load_state()` originally stayed on `App` too, for the same
reason: they touched `self.encoders`, a hardware object `Navigator` can't
depend on. They were moved into `Navigator` in a follow-up once it became
clear that dependency wasn't actually necessary — `Navigator.save_state()`/
`load_state()` take and return plain encoder-offset dicts instead of a
`PositionalEncoders` object (see Methods table above), so `App`'s versions
are now a few lines gathering/applying `self.encoders`' values around a
call into `self.nav`. The on-disk cache format (`~/cache/radioglobe.json`)
didn't change, so this was a behavior-preserving move — existing cache
files on deployed devices remain readable.

**Non-obvious detail — history of the `jog_idx` split (2026-08-01):**
Before this date, `station_idx`/`city_idx` were a single shared `jog_idx`
field (station index in `MODE_STATION`, city index in `MODE_CITY`).
`switch_mode()` had to re-derive it via a linear search (`items.index(current)`)
into the new mode's list on every toggle, and `select_station()` deliberately
never touched it, since resetting it while in `MODE_CITY` would have
corrupted city-cycling sharing the same field. Splitting the field removed
both hazards structurally — `switch_mode()` needs no recompute, and
`select_station()` can safely always reset `station_idx`. This also fixed
two latent low-severity bugs the shared field caused: `remove_failed_station()`
previously used `jog_idx` regardless of `self.state.mode`, so a stream
failure while the dial was in `MODE_CITY` could modulo a city index into
the station list; and `load_state()` always overwrote `jog_idx` with a
station-match index on warm restart, discarding city-index meaning if the
app was last in `MODE_CITY` at shutdown. Old on-disk cache files (single
`"jog_idx"` key) still load without error — `load_state()` simply defaults
both new fields to 0 and ignores the stale key.

---

### 4.4 `database.py` — Station Data

Pure functions with no side effects and no hardware dependencies. The most testable module in the project.

**Functions:**

| Function | Returns | Notes |
|---|---|---|
| `load_stations(path)` | `dict` keyed by `"City,CC"` | Returns empty dict on FileNotFoundError |
| `build_cities_index(stations_data)` | `dict[(lat_idx, lon_idx) → list[city_name]]` | Converts lat/lon degrees to 0–1023 grid indices; multiple cities per cell are supported |
| `build_look_around_offsets(fuzziness)` | `list` of `(dx, dy)` tuples | Pre-computes the search-zone offset pattern once, at startup (now `Navigator.__init__` — §4.3) |
| `look_around(origin, offsets)` | `list` of `(lat, lon)` tuples | Applies the pre-computed offsets to an origin point — cheap enough to call on every encoder event |
| `find_cities_near(origin, offsets, cities_index)` | `list` of city strings, closest-first | The production city search; wrapped by `Navigator.find_cities_near()` (§4.3), called from `_encoder_loop()` in `main.py` |
| `get_stations_by_city(stations, city)` | `list` of `(name, url)` tuples | The canonical station list format |
| `get_coords_by_city(stations, city)` | `Coordinate` | Raises `KeyError` if the city isn't in the data — backs `Navigator.current_coords` and the stale-city check in `Navigator.load_state()` (§4.3) |
| `match_saved_station(saved_name, stations)` | `(station, station_idx)` tuple | Finds a saved station by name in a refreshed station list, falling back to index 0 if not found; used by `Navigator.load_state()`'s warm-restart path (§4.3) |
| `get_found_cities(search_area, city_map)` | `list` of city strings | Used only by integration test scripts; superseded in production by `find_cities_near` |

**Coordinate formula:** `index = round((degrees + 180) * 1024 / 360)`. This maps −180°→0 and +180°→1024.

**`build_look_around_offsets()` detail:** `fuzziness=1` returns just the origin offset; `fuzziness=2` returns 9 offsets (3×3 area); `fuzziness=3` returns 25 offsets (5×5 area) — the app's default (`FUZZINESS = 3`, see [§8](#8-configuration-reference)). The pattern is built innermost-first, so `find_cities_near()` returns matches closest-first. The search starts bottom-left and scans horizontally — this matches ergonomics (70% of people are right-eye dominant and hold the globe below eye level).

**Legacy functions** at the bottom of the file (`get_stations_info`) are not used by the main application — only by integration test scripts.

`get_coords_by_city` and `match_saved_station` were pulled out of `App` and
into this module in the 2026-07-30 decoupling refactor — same "pure logic
goes in `database.py`" principle as everything else here.

---

### 4.5 `positional_encoders.py` — Globe Position

Reads two SPI absolute rotary encoders and maintains the current lat/lon position.

`_ENCODER_RESOLUTION` (1024) is owned by `database.py` — not this module — and
imported here, since `database.py`'s grid-coordinate math needs the same
value and is deliberately hardware-free (§4.4). Owning it in the pure module
rather than here avoids giving `database.py` a dependency on a
hardware-touching module.

**Key behaviour:**
- Each encoder is read via SPI bus 0, device 0 (latitude) and device 1 (longitude), at 1,000,000 Hz, SPI mode 1 — the datasheet maximum for the Bourns EMS22A50-D28-LT6 (raised from an original 5000 Hz; see `docs/KERNEL_ROTARY_ENCODER_INVESTIGATION.md`).
- Raw readings are 16 bits; the top 10 bits (after shifting right by 6) give the 0–1023 position.
- `check_parity()` validates each reading. If parity fails, the entire read returns `None` and is discarded.
- Latitude is inverted: `readings[0] = _ENCODER_RESOLUTION - readings[0]`. This corrects for encoder mounting orientation.
- `run_encoder()` is an event-driven task, not a target the app polls: while unlatched, it sets `self.updated` (an `asyncio.Event`) on every successful read; `main.py`'s `_encoder_loop()` awaits this event instead of polling on its own. Once latched, the event only fires again when the position drifts past `latch_stickiness`.

**The latch mechanism:**
- `latch(lat, lon, stickiness)` stores the latched position and sets `latch_stickiness` to the threshold value.
- While latched, `run_encoder()` still reads SPI but only updates `self.latitude`/`self.longitude` if the new reading differs by more than `latch_stickiness` steps. A deviation must be seen on `UNLATCH_CONFIRM_THRESHOLD` (2) consecutive readings before it actually unlatches — added to stop the faster 50ms poll rate from reacting to single-sample sensor noise (the EMS22A50 datasheet specifies ~0.12° RMS output transition noise) as if it were real movement. Once confirmed, `latch_stickiness` is set to `None` (unlatched) and reading resumes normally.
- `is_latched()` returns `True` if `latch_stickiness is not None`.

**Calibration:** `zero()` sets offsets so the current physical position maps to (512, 512), which corresponds to 0°N, 0°E (the equator / prime meridian intersection). `get_readings()` always returns the offset-adjusted value modulo `_ENCODER_RESOLUTION`. `reset_latch()` clears `latch_stickiness` so `_encoder_loop()` can re-detect cities after zeroing — `zero()` alone does not clear the latch.

**Persistence:** `get_calibration()` returns `{"lat", "lon", "lat_offset",
"lon_offset"}` as a plain dict; `restore_calibration(state)` applies one
back and also sets `latch_stickiness = True`, since a restored position
always represents a previously-latched city. These exist so `App.save_state()`/
`load_state()` (§4.1) never need to know this class's internal field names
— `PositionalEncoders` is the only thing that reads or writes its own
`latitude`/`longitude`/`latitude_offset`/`longitude_offset`/`latch_stickiness`.

---

### 4.6 `dial.py` — Station / City Selector

Reads a quadrature rotary encoder on GPIO pins 17 (clock) and 18 (direction) — but unlike
every other GPIO device in this project, decoding happens in the **kernel**, not in Python.
`install.sh` adds `dtoverlay=rotary-encoder,pin_a=17,pin_b=18,relative_axis=1` to
`/boot/firmware/config.txt`, which binds the stock `drivers/input/misc/rotary_encoder.c`
driver to those two pins. The driver's IRQ handler runs a gray-code state machine that
rejects invalid transition sequences, but — confirmed by a raw on-device event capture,
see `docs/KERNEL_ROTARY_ENCODER_INVESTIGATION.md` §9 — it does **not** fully suppress
mechanical contact bounce, even at the overlay's most conservative `steps-per-period=1`
default: bounce can still produce bursts of several extra same-sign or cancelling
opposite-sign `REL_X` events within a few milliseconds of a single physical click. A
software coalescing layer in `dial.py` (below) filters this out. Investigated in full in
`docs/KERNEL_ROTARY_ENCODER_INVESTIGATION.md` §6 and §9.

- `AsyncDial._find_rotary_device()` locates the resulting `/dev/input/eventN` device via
  `evdev.list_devices()`, matching by capability (`EV_REL`/`REL_X` present, `EV_KEY`
  absent) rather than a hardcoded device name or event-number, so it survives reboots and
  eventN renumbering.
- `start()` registers the device's file descriptor directly on the asyncio event loop with
  `loop.add_reader(fd, callback)` — no background task, no thread pool.
- `_on_readable()` accumulates the signed `REL_X` value of each event into a running sum
  and (re)arms a single `loop.call_later(_DIAL_DEBOUNCE_S, self._flush)` timer, cancelling
  and rescheduling it on every new event — so the timer only fires once the encoder goes
  quiet for `_DIAL_DEBOUNCE_S` (a private constant in this module). `_flush()` then pushes a single
  `_POLARITY * sign(sum)` onto `self.queue` (an `asyncio.Queue[int]`, via `put_nowait`) —
  or nothing at all if the accumulated sum is exactly zero, i.e. a bounce burst that fully
  cancelled itself. A single `_POLARITY` constant corrects for physical wiring, same role
  as the old code's sign inversion.
- `stop()` cancels any pending debounce timer before calling `loop.remove_reader(fd)`,
  which is synchronous and immediate — this fixed a real bug in the old GPIO-based
  version, where `stop()` awaited a task blocked inside
  `asyncio.to_thread(GPIO.wait_for_edge, ...)` and could hang until the next physical edge.
- `main.py`'s `_dial_loop()` is unchanged: it still consumes `await self.dial.queue.get()`
  — both the kernel-driver migration and the bounce-coalescing fix are entirely internal
  to `dial.py`.

---

### 4.7 `buttons.py` — Button Manager

Manages four GPIO buttons with short and long press detection.

**Button definition tuple:**
```python
ButtonDefinition(name, pin, short_cb, long_cb, press_cb)
```
- `press_cb` fires immediately on press-down (used for instant LED feedback)
- `short_cb` fires on release if held < 1.0 second
- `long_cb` fires on release if held ≥ 1.0 second

The name+pin pairing is fixed by this project's custom board (Jog/Top/Mid/Bottom
are wired to specific header pins, not an app-level choice), so `buttons.py`
owns it completely: `JOG_BUTTON`, `TOP_BUTTON`, `MID_BUTTON`, `BOTTOM_BUTTON`
are module-level `ButtonDefinition` constants with `name`/`pin` set and every
callback field left at its `None` default. `main.py` never imports a pin
number — it attaches its own callbacks via `NamedTuple._replace()`:
```python
button_definitions = [
    JOG_BUTTON._replace(short_cb=self._handle_short_jog, press_cb=self._on_jog_press),
    TOP_BUTTON._replace(short_cb=self._handle_short_top, long_cb=self._handle_long_top, press_cb=self._on_sound_press),
    ...
]
```
The underlying `_PIN_BTN_*` constants (§8) are truly private — nothing
outside `buttons.py` imports them; callers that need a specific pin (e.g.
the single-button integration test scripts under `tests/integration/`) read
`TOP_BUTTON.pin` etc. instead.

`AsyncButton` uses GPIO fall-edge callbacks that bridge into the asyncio event loop via `loop.call_soon_threadsafe()`. `AsyncButtonManager` holds all buttons, runs a background polling task, and dispatches events via an `asyncio.Queue`.

`AsyncButtonManager.__init__` calls `GPIO.setmode(GPIO.BCM)` itself, before
constructing any `AsyncButton` (whose `GPIO.setup()` call requires it). This
used to be centralized in `App.__init__` (`main.py`, §4.1) instead, on the
assumption every `AsyncButton` is constructed via `App` — but the standalone
integration scripts under `tests/integration/` construct
`AsyncButtonManager` directly without ever building an `App`, so that
assumption broke them (`GPIO.setup()` raising "Please set pin numbering
mode..."). `AsyncButtonManager` now guarantees its own precondition instead
of trusting the caller. `rgb_led.py`'s `RGBLed` owns the identical call for
the identical reason (§4.10) — `App.__init__` no longer calls
`GPIO.setmode()` at all as of the 2026-07-31 hardware-config release; each
GPIO-owning class is fully self-sufficient. `GPIO.setmode()` is idempotent,
so constructing both an `AsyncButtonManager` and an `RGBLed` in the same
process (as `App` does) calls it twice harmlessly.

Teardown mirrors setup: `AsyncButtonManager.stop()` calls
`GPIO.cleanup([btn.pin for btn in self.buttons])`, releasing only the pins
this manager itself set up. `App.run()`'s `finally` block no longer calls a
bare `GPIO.cleanup()` — it just awaits `.stop()` on every hardware object it
holds (including `button_manager`, §4.1), and each object releases exactly
the channels it owns. `rgb_led.py` does the same in `RGBLed.stop()` (§4.10).

`handle_events()` wraps each handler call in try/except, logging failures
via `logging.exception()`. Without this, an unhandled exception from any
one button's `short_cb`/`long_cb` would kill this loop outright — since
it's the single consumer for every button's queued events, that silently
stops short/long dispatch for *all four buttons*, not just the one whose
handler failed. Press-down feedback (`press_cb`) keeps working regardless,
since it runs on each button's own independent task — the failure mode
without this fix looks like "the LED still flashes on press but nothing
else ever happens again," with no visible error beyond an easy-to-miss
"Task exception was never retrieved" warning.

---

### 4.8 `display.py` — LCD Display

Drives a 20×4 I2C character LCD at address 0x27 on bus 1, using the `liquidcrystal_i2c` library.

- Internally maintains a 4-line text buffer and an `asyncio.Event` (`changed`). When `update()` or `message()` is called, the buffer is updated and the event is set.
- `_display_loop()` is an asyncio Task that waits for the event, writes all 4 lines to the LCD, and sleeps 100ms. This coalesces rapid updates — important because I2C is slow.
- All strings are truncated to `DISPLAY_COLUMNS` characters before `center()` is applied, so overlong city or station names never overflow the hardware line buffer.
- `show_station(coords, city, station_name)` and `show_status(status, coords=None)` wrap `update()`'s 5-argument shape for the two call patterns `App` actually uses (added in the decoupling refactor so `App` no longer needs to know `update()`'s full signature or repeat its `volume=0, arrows=False` boilerplate). The one place `App` still calls `update()` directly is the volume overlay in `_show_volume_briefly()`, which needs the `volume` argument `show_station()` hardcodes to 0.

**Display layout when playing:**
```
Line 0: 51.50N, 0.13W        ← Coordinate.__str__()
Line 1: London,GB             ← City name
Line 2: --------              ← Volume bar (ASCII dashes, scales 0–100)
Line 3: BBC Radio 2           ← Station name
```

---

### 4.9 `audio_async.py` — Audio Player

Wraps `python-vlc` directly. Does not import from `streaming/`.

```python
class AudioPlayer:
    def __init__(self):
        self.instance = vlc.Instance(
            "--input-repeat=-1",
            "--network-caching=2000",
        )
        self.player = self.instance.media_player_new()
        self.current_url = None
```

- `play(url)` stops any current playback and starts the new URL immediately. VLC handles playlist URLs (`.m3u`, `.pls`) internally. It records `current_url` so `_monitor_stream` can detect when the user has moved to a new station. `AudioPlayer` only ever deals in URL strings — it has no concept of a "city" or "station"; callers extract the URL from `self.nav.state.station[1]` before calling.
- `--input-repeat=-1` means VLC retries the stream automatically if the connection drops.
- `--network-caching=2000` adds a 2 s jitter buffer to absorb network hiccups without triggering error state.
- Volume is managed via VLC's `audio_get_volume` / `audio_set_volume`, range 0–100.
- `is_error()` returns `True` if VLC is in `State.Error` **or** `State.Ended`. Both indicate failure for a live stream: `Error` for codec/protocol failures, `Ended` for HTTP 404 responses.
- Dead-stream detection is handled by `App._monitor_stream(expected_url)` in `main.py`. It checks `is_error()` every 3 s. On failure it flashes the LED red, removes the failed station from the session list (`self.nav.remove_failed_station()` — `Navigator`, §4.3), and immediately plays and displays the next station — looping until one plays cleanly, all stations for the city are exhausted, or the user selects something else, at which point the loop exits silently.

---

### 4.10 `rgb_led.py` — Status LED

Three GPIO output pins (R=22, G=23, B=24) with simple on/off control (no PWM).

`RGBLed.flash(colour, duration)` is an async method, always spawned with `asyncio.create_task()` rather than awaited. It:
1. Checks its own `self._running` Event to prevent overlapping flashes (a no-op if a flash is already in progress)
2. Sets the event, turns the LED on
3. Sleeps for `duration` seconds
4. Turns the LED off and clears the event

This used to be a standalone coroutine (`led_task(led, led_running, colour, duration)`) that every call site in `main.py` had to pass a shared `asyncio.Event` into by reference — folded into `RGBLed` itself in the decoupling refactor so `App` only needs to know `self.led.flash(colour, duration)` exists, not that it needs a co-owned `Event`. `RGBLed.__init__` also calls `GPIO.setmode(GPIO.BCM)` itself, for the same self-sufficiency reason as `AsyncButtonManager` — see §4.7. `RGBLed.stop()` mirrors this on teardown: it turns the LED off, then calls `GPIO.cleanup(list(self.pins.values()))` to release only its own 3 pins, rather than relying on a process-wide `GPIO.cleanup()` call in `main.py`.

**Colour conventions used in `main.py`:**
- Green: city found/latched, button press feedback
- Blue: dial turned, volume button press

---

### 4.11 `coordinates.py` — Coordinate Type

A simple value object. `__str__` produces the display format used on the LCD:

```python
>>> str(Coordinate(51.5074, -0.1278))
'51.51N, 0.13W'
```

Equality comparison rounds to 2 decimal places (`ROUNDING = 2`). Used consistently throughout `main.py` and `display.py` — all `display.update()` call sites pass a `Coordinate` object.

---

### 4.12 `radio_config.py` — Configuration

Defines app-behavior tuning constants shared across modules (volume levels, display/LED durations, search fuzziness/stickiness, file paths, log level). Constants tied to a single piece of physical hardware (GPIO pins, I2C address, encoder resolution, dial debounce timing) live as private (leading-underscore) constants in the module that owns that hardware instead — see [§8 Configuration Reference](#8-configuration-reference) for the full list and rationale.

No side-effects on import — it is a constants-only module. Logging is configured in `main.py`'s `__main__` block.

---

### 4.13 `streaming/` — Historical Streaming Implementations

This directory contains four streaming approaches developed over time. None are imported by the production code (`audio_async.py`).

| File | Approach | Status |
|---|---|---|
| `streaming.py` | subprocess + amixer volume | Legacy |
| `streaming_cvlc.py` | `cvlc` CLI subprocess | Used in integration test scripts |
| `python_vlc_streaming.py` | python-vlc with explicit playlist detection | Informed `audio_async.py` design |
| `async_streamer.py` | Async playlist URL resolver using aiohttp | Experimental, not used |
| `files.py` | JSON station loader helper | Used by test scripts |

If you need to understand the audio subsystem, read `audio_async.py`. The `streaming/` directory is useful historical context.

---

## 5. Key Data Flows

### Flow A: Globe Spun to a New City

1. `PositionalEncoders.run_encoder()` polls SPI every 50ms. While unlatched, each successful read sets `encoders.updated` (an `asyncio.Event`).
2. `_encoder_loop()` wakes on that event, clears it, and calls `encoders.get_readings()` — returns the offset-adjusted `(lat, lon)` tuple.
3. `self.nav.refresh_nearby_cities(coords)` (`Navigator`, §4.3) applies the pre-computed offset pattern — 25 points (5×5 area) for the default `FUZZINESS = 3` — stores and returns matching cities, closest-first.
4. If cities are found and the encoders are not already latched:
   - `encoders.latch(*coords, stickiness=STICKINESS)` freezes the position.
   - The LED flashes green (`self.led.flash(...)`, §4.10).
   - `self.nav.select_city()` (`Navigator`, §4.3) latches `state.cities[0]` as the current city, resets `city_idx` to 0, and selects its first station via `get_stations_by_city()` + `AppState.select_station()`; returns `False` (and the latch is undone) if the closest city has no stations.
5. `audio_player.play(station[1])` passes the URL to VLC.
6. `display.show_station(coords, city, station_name)` refreshes the LCD (§4.8).
7. `_start_monitor_stream(station_url)` cancels any previous monitor and starts a new one, which checks playback every 3 s and switches to the next station on failure.

### Flow B: User Turns the Dial

1. The kernel's `rotary_encoder` driver decodes GPIO 17/18 transitions and emits an `EV_REL`/`REL_X` evdev event; `AsyncDial`'s `loop.add_reader` callback reads it and pushes the direction onto `dial.queue`.
2. `_dial_loop()` wakes with `await self.dial.queue.get()` — no polling.
3. The LED flashes blue.
4. If `mode == "station"`: `self.nav.next_station(direction)` increments/decrements `station_idx` within `self.nav.state.stations` (wraps around).
5. If `mode == "city"`: `self.nav.next_city_and_select_station(direction)` (`Navigator`, §4.3) increments/decrements `city_idx` within `self.nav.state.cities` and selects the new city's first station in one call, returning `False` (previous station keeps playing) if the new city has no stations.
6. `display.show_station()` and `audio_player.play()` update immediately.

---

## 6. State Management

Application state lives on `self.nav.state` — an `AppState` (§4.2) owned by
`Navigator` (§4.3), not held directly by `App`. See §4.2 for the field
table.

Encoder state (lat/lon, offsets, latch) is owned by `PositionalEncoders` on
`self.encoders` — separate from `AppState` and unaffected by the decoupling
refactor.

On shutdown (long press of mid button), `App.save_state()` gets a plain
dict from `self.encoders.get_calibration()` (§4.5) and hands it to
`self.nav.save_state()` (§4.3), which calls `dataclasses.asdict(self.state)`
and appends the encoder offsets and latch flag, writing the result to
`~/cache/radioglobe.json`. On the next boot, `App.load_state()` calls
`self.nav.load_state()`, which reconstructs an `AppState(...)` from the
JSON, then immediately re-queries `get_stations_by_city()` from the live
database and calls `match_saved_station()` (`database.py`, §4.4) to match
the saved station by name (falling back to index 0 if not found) — this
means a `stations.json` update between boots never causes a wrong URL or
stale index. `Navigator.load_state()` returns the saved encoder offsets as
a plain dict, which `App.load_state()` passes straight to
`self.encoders.restore_calibration()` (§4.5) without inspecting it —
`App` never touches an encoder's internal fields directly.

---

## 7. Concurrency Model

The entire application runs on a single asyncio event loop, made up of several independent, event-driven tasks rather than one polling "main loop." Understanding this is essential before modifying any hardware module.

**Tasks running concurrently (started from `run()` and component `start()` calls):**
```python
# dial.start() is NOT a task — it's a loop.add_reader(fd, callback) registration.
# The kernel's rotary_encoder driver does the decode/debounce; the event loop invokes
# the callback directly whenever the evdev fd is readable, pushing to dial.queue.
asyncio.create_task(encoders.run_encoder())          # polls SPI every 50ms, sets encoders.updated
asyncio.create_task(display._display_loop())         # writes LCD on `changed` event
asyncio.create_task(button_manager._poll_buttons())  # polls button state every 50ms, pushes to event_queue
asyncio.create_task(button_manager.handle_events())  # dispatches queued button events
asyncio.create_task(self._encoder_loop())            # wakes on encoders.updated — latches cities
asyncio.create_task(self._dial_loop())               # wakes on dial.queue — navigates stations/cities
```
`run()` only awaits the last two (`await asyncio.gather(encoder_task, dial_task)`); the others run in the background for the app's lifetime.

**GPIO interrupt bridging:** RPi.GPIO fires button callbacks on a separate interrupt thread. These callbacks call `loop.call_soon_threadsafe(...)` to schedule coroutines back onto the asyncio event loop. This is the correct pattern — do not call `asyncio.create_task()` directly from a GPIO callback thread.

**Blocking calls:** `GPIO.wait_for_edge()` is blocking and is wrapped with `asyncio.to_thread()` in `buttons.py`'s underlying GPIO callback dispatch. Any new hardware code that polls with blocking calls must do the same. For anything that exposes a pollable file descriptor instead (evdev devices, sockets, pipes), prefer `loop.add_reader(fd, callback)` — this is what `dial.py` now does, avoiding a thread entirely rather than wrapping a blocking call in one.

**LED tasks** are always `create_task`'d rather than awaited — they are fire-and-forget. `RGBLed`'s own internal `self._running` Event prevents concurrent flashes (§4.10).

**What to be careful about:** Do not put any blocking call (file I/O, `time.sleep()`, synchronous network calls) directly in any of these loop bodies. Every blocking call holds up all other hardware tasks.

---

## 8. Configuration Reference

As of the 2026-07-31 config-relocation release, `radio_config.py` holds only
app-behavior tuning constants — values about UX/timing/search behaviour, not
tied to a specific piece of physical hardware. Constants describing a single
component's wiring or protocol (a GPIO pin, an I2C address, an SPI timing
value, an encoder's bit resolution) live as private (leading-underscore)
constants in the module that owns that hardware, and are not re-exported.
Where another module genuinely needs the value, it imports it directly from
the owning module by name (e.g. `positional_encoders.py` imports
`_ENCODER_RESOLUTION` from `database.py`, §4.5). This mirrors `display.py`'s
pre-existing `DISPLAY_COLUMNS`/`DISPLAY_ROWS` pattern. `buttons.py` goes a
step further: its `_PIN_BTN_*` pin constants have zero consumers outside the
module — `main.py` and the integration test scripts consume the higher-level
`JOG_BUTTON`/`TOP_BUTTON`/`MID_BUTTON`/`BOTTOM_BUTTON` constants instead
(§4.7), never a raw pin number.

### `radio_config.py` — app-behavior tuning (shared)

| Parameter | Value | Where used |
|---|---|---|
| `STATIONS_JSON` | `"stations/stations.json"` | `navigation.py` — station data path |
| `FUZZINESS` | 3 | `navigation.py` — `Navigator.__init__` default, builds the 25-point (5×5) search zone; also logged (but not otherwise used) in `main.py`'s `_encoder_loop()` debug output |
| `STICKINESS` | 2 | `main.py` — unlatch threshold in encoder steps |
| `VOLUME_STEP` / `DEFAULT_VOLUME` / `VOLUME_ON_LEVEL` / `VOLUME_OFF_LEVEL` | 10 / 50 / 80 / 0 | `main.py` — volume handling |
| `BRIEF_DISPLAY_DURATION` / `MESSAGE_DISPLAY_DURATION` | 0.5 / 2 | `main.py` — display hold durations |
| `STREAM_CHECK_INTERVAL` | 3 | `main.py` — stream health check grace period |
| `LED_FLASH_SHORT` / `LED_FLASH_LONG` / `LED_FLASH_DIAL` | 0.2 / 0.5 / 0.1 | `main.py` — LED feedback durations passed to `RGBLed.flash()` |
| `STATE_CACHE_PATH` | `"~/cache/radioglobe.json"` | `main.py` — default arg for `App.save_state()`, passed explicitly to `self.nav.load_state()`; also `navigation.py` — default arg for `Navigator.save_state()`/`load_state()` |
| `LOG_LEVEL` | `"DEBUG"` | `main.py` — `__main__` logging setup |

### Hardware modules — private, module-owned

| Parameter | Value | Owning module |
|---|---|---|
| `_ENCODER_RESOLUTION` | 1024 | `database.py` — owned here (not `positional_encoders.py`) so the pure grid-math module stays hardware-free; `positional_encoders.py` imports it from `database.py` (§4.5) |
| `_DIAL_DEBOUNCE_S` | 0.03 | `dial.py` — `AsyncDial._on_readable()`/`_flush()`; coalesces bursts of kernel `REL_X` events (contact bounce) into a single net direction per physical click |
| `_PIN_BTN_JOG` / `_PIN_BTN_TOP` / `_PIN_BTN_MID` / `_PIN_BTN_BOTTOM` | 27 / 5 / 6 / 12 | `buttons.py` — never imported elsewhere; exposed to `main.py` only indirectly via the `JOG_BUTTON`/`TOP_BUTTON`/`MID_BUTTON`/`BOTTOM_BUTTON` `ButtonDefinition` constants (§4.7), which pair each pin with its fixed board role |
| `_PIN_LED_R` / `_PIN_LED_G` / `_PIN_LED_B` | 22 / 23 / 24 | `rgb_led.py` — `RGBLed.__init__` defaults; never needed outside this module (`main.py` constructs `RGBLed()` with no args) |
| `_I2C_LCD_ADDR` | `0x27` | `display.py`, alongside the pre-existing `DISPLAY_I2C_PORT`/`DISPLAY_COLUMNS`/`DISPLAY_ROWS` |
| SPI poll interval | 50ms (`asyncio.sleep(0.05)`) | `positional_encoders.py` — `run_encoder()`; hardcoded. Raised from an original 200ms — see `docs/KERNEL_ROTARY_ENCODER_INVESTIGATION.md` |
| SPI clock speed | `max_speed_hz = 1000000` | `positional_encoders.py` — `read_spi()`; hardcoded. Raised from an original 5000 Hz to the Bourns EMS22A50-D28-LT6 datasheet maximum |
| `UNLATCH_CONFIRM_THRESHOLD` | 2 | `positional_encoders.py` class constant — consecutive out-of-band readings required before unlatching, added to filter sensor noise at the faster poll rate |

**Dial clock/direction pins (removed):** `PIN_DIAL_CLOCK`/`PIN_DIAL_DIR`
(BCM 17/18) used to exist in `radio_config.py` despite having zero Python
consumers — the kernel `rotary_encoder` driver reads the pins directly from
`install.sh`'s `dtoverlay=rotary-encoder,pin_a=17,pin_b=18,...` line (§4.6),
which is the only place they're configured. They were deleted rather than
relocated; `install.sh` now has a comment marking that line as the single
source of truth for those two pins.

---

## 9. Testing

Unit tests run on any machine. Hardware integration scripts require a connected Raspberry Pi.

**Unit tests (run without hardware):**
```bash
uv run pytest
```
`pyproject.toml` configures `testpaths = ["tests"]` and `norecursedirs = ["integration"]`, so `pytest` finds only the unit tests and skips the hardware scripts automatically. A `[build-system]` table in `pyproject.toml` makes `uv sync`/`uv run` install `radioglobe` into the venv so this works standalone — without it, `radioglobe` isn't importable and every test file fails with `ModuleNotFoundError` (this was broken for a while; fixed 2026-07-30).

| Test file | Covers |
|---|---|
| `get_stations_by_city_test.py` | `database.get_stations_by_city` |
| `get_coords_by_city_test.py` | `database.get_coords_by_city` |
| `match_saved_station_test.py` | `database.match_saved_station` |
| `app_state_test.py` | `AppState.is_complete`, `AppState.select_station` (§4.2) |
| `navigation_test.py` | `Navigator` — `next_station`, `next_city`, `switch_mode`, `remove_failed_station`, `current_coords`, `find_cities_near`, `save_state`/`load_state` (§4.3), against an in-memory fixture station dict |
| `buttons_test.py` | `AsyncButtonManager.handle_events()` stays alive after a handler raises, and logs the failure (§4.7) |

All follow the same style: plain `unittest.TestCase`, in-memory fixture data, no mocking — the module structure introduced in the decoupling refactor made `AppState` and `Navigator` testable this way for the first time; before it, only `database.py` had real unit tests. `buttons_test.py` stubs `RPi.GPIO` in `sys.modules` before importing `radioglobe.buttons`, since that module still touches real GPIO functions at construction time.

**Hardware / integration scripts** live in `tests/integration/` and must be run directly on the Pi. See [tests/integration/README.md](tests/integration/README.md) for the full, maintained list, usage examples, and hardware setup notes — duplicating it here previously went stale (a `simulation_test.py` that never existed lingered in this table for a while; three scripts also silently broke when `led_task` was folded into `RGBLed.flash()`, since nothing exercises them automatically). Highlights:

| Script | What it tests |
|---|---|
| `button_test.py` | GPIO button short/long press detection — `python ../tests/integration/button_test.py mid` |
| `button_reliability_test.py` | Compares a raw GPIO poll against `AsyncButtonManager`'s registered presses to catch dropped/stuck presses (§4.7) — see CHANGELOG.md for the Mid button connector fault this diagnosed |
| `positional_encoders_test.py` | SPI encoder reading and latch mechanism |
| `dial_test.py` | Kernel rotary-encoder evdev device discovery and direction detection |

---

## 10. Contributing

Branching, PR, and release conventions live in [CONTRIBUTING.md](CONTRIBUTING.md) — feature branches off `develop`, PRs into `develop`, releases cut from `master` via the `Makefile` version bump targets.

---

## 11. Suggested Improvements

These are ordered from lowest to highest effort. None require a rewrite — all are incremental changes.

---

### Improvement A: ~~`IndexError` if a city has no stations at latch time~~ — Resolved

This was fixed as an incidental side effect of the 2026-07-30 decoupling
refactor (`AppState.select_station()`, §4.2), not pursued as a deliberate
bug-fix in its own right. `select_station(stations)` guards the
empty-list case and returns `False` instead of indexing blindly, and both
call sites that used to have the unguarded `self.state.stations[0]`
pattern — the latch block in `App._encoder_loop()` and the `MODE_CITY`
branch of `App._dial_loop()` — now check its return value before
proceeding (`if not self.nav.state.select_station(stations): ...`). No
action needed.

---

### Improvement B: `save_state()` serialises `stations` and `cities` snapshots that are ignored on restore

**Problem:** `Navigator.save_state()` uses `dataclasses.asdict(self.state)`, which includes `stations` (a list of `(name, url)` tuples for the current city) and `cities` (all cities found in the search zone at latch time). Both can be large. `load_state()` re-queries `stations` from the live database on startup, and `cities` is repopulated by `App._encoder_loop()` the next time `encoders.updated` fires — so the saved values are read from JSON and immediately discarded. They bloat the cache file for no benefit.

**Fix:** Build the dict manually in `Navigator.save_state()`, omitting the two lists:
```python
state = {
    "station": list(self.state.station) if self.state.station else None,
    "station_idx": self.state.station_idx,
    "city": self.state.city,
    "city_idx": self.state.city_idx,
    "mode": self.state.mode,
}
state.update(encoder_offsets)
```

**Effort:** 15 minutes.

---

### Improvement C: Volume display updates can be overwritten by a concurrent display update

**Problem:** `_update_volume()`/`_update_volume_level()` call `_show_volume_briefly()`, which calls `display.update()` directly, then `await asyncio.sleep(0.5)`, then calls `display.show_station()` to clear the volume bar. During the 0.5 s yield, `_encoder_loop()` or `_dial_loop()` may also update the display — for example if a city is freshly latched while the volume overlay is showing. The second call then overwrites that update with a stale "volume cleared" view.

This is cosmetic and non-crashing, but the display momentarily shows the wrong city or station after the sleep. A fix requires either a timestamp/generation counter to skip the second update if the display has moved on, or removing the two-call pattern entirely in favour of a timed overlay in `_display_loop`.

**Effort:** 30–60 minutes.

---

## 12. What's Already Good

**`database.py` pure-function design.** All station and city lookups are stateless functions with no hardware dependencies. They're unit-testable without mocking anything and straightforward to reason about. The one-time index build at startup (`build_cities_index`, now called from `Navigator.__init__` — §4.3) is the right trade-off — it makes every city lookup in `_encoder_loop()` O(1).

**`app_state.py`/`navigation.py` following `database.py`'s lead.** The 2026-07-30 decoupling refactor pulled `AppState` and the navigation logic that mutates it out of `main.py` and into their own hardware-free modules, deliberately mirroring `database.py`'s pure-function/no-side-effects style rather than introducing a new pattern. `Navigator` is now unit-testable the same way `database.py` always was (`tests/navigation_test.py`), closing what had been the biggest test-coverage gap in the project — before this, the core station/city navigation logic (latching, dial cycling, mode switching) had zero automated tests.

**The spatial search approach.** Building a 1024×1024 grid dict at startup and doing dict lookups in `find_cities_near()` is efficient and simple. `build_look_around_offsets()` with fuzziness is the right way to handle the physical imprecision of pointing at a globe.

**The asyncio architecture is fundamentally sound.** GPIO interrupt callbacks are correctly bridged back to the event loop via `call_soon_threadsafe`. Blocking GPIO calls are wrapped in `asyncio.to_thread` — `dial.py` is the one exception, since it reads a pollable evdev fd via `loop.add_reader` instead of a blocking GPIO call, needing neither a thread nor `call_soon_threadsafe`. Event-driven waits (`encoders.updated`, `dial.queue`) mean idle tasks cost nothing, rather than burning CPU on a fixed-interval poll.

**The latch mechanism.** Freezing the encoder position until the user moves significantly is a genuinely clever UX solution. Without it, browsing stations while holding the globe still would be impossible — any tiny vibration would trigger a city change.

**Display update coalescing.** The buffer + `asyncio.Event` pattern in `display.py` correctly batches rapid updates. I2C is slow (~100µs per byte); writing all 4 LCD lines takes several milliseconds, so coalescing is not just an optimisation — it's necessary for responsiveness.

**The systemd user service** (not system service) is the correct approach for an application that uses PulseAudio. PulseAudio runs per-user; a system service cannot see the user's audio session. Running as the logged-in user (with `loginctl enable-linger`) is the only reliable way to get auto-detected audio outputs including Bluetooth.
