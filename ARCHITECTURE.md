# RadioGlobe Architecture

This document is a guide for developers joining the project. It explains the physical hardware, how the software maps onto it, and what each module does. It also surfaces concrete improvement suggestions to make the code easier to maintain and extend.

This is not the setup guide — that's [README.md](README.md). For a brief asyncio design sketch, see [docs/DESIGN.md](docs/DESIGN.md).

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
10. [Suggested Improvements](#10-suggested-improvements)
11. [What's Already Good](#11-whats-already-good)

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
| Station/city select dial | GPIO quadrature | Pins 17 (clock), 18 (direction) | `dial.py` |
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
│   ├── main.py                       # App class: entry point and main loop
│   ├── radio_config.py               # Configuration constants (see caveat in §8)
│   ├── database.py                   # Pure functions: station/city spatial index
│   ├── coordinates.py                # Coordinate value object (lat/lon → display string)
│   ├── audio_async.py                # AudioPlayer: wraps python-vlc directly
│   ├── display.py              # 20×4 I2C LCD driver
│   ├── dial.py                 # Quadrature encoder for station/city selection
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
├── tests/                            # Mix of unit tests and hardware integration scripts
│   ├── get_stations_by_city_test.py  # Unit tests (run without hardware)
│   ├── simulation_test.py            # Integration: requires Pi hardware
│   ├── async_streamer_test.py        # Integration: requires network
│   └── ...                           # Other hardware / manual test scripts
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
- `tests/` contains both proper unit tests (runnable on any machine) and hardware integration scripts. They are not yet separated — see [Improvement 11](#improvement-11-separate-integration-test-scripts).

---

## 3. Architecture Overview

The application is a single-process asyncio program. One event loop runs on the main thread, and all hardware I/O runs as asyncio Tasks or is bridged into the loop from GPIO interrupt threads.

**The central concept is the reticule position.** Every 100ms the main loop reads the encoder position, searches the spatial city index for any city near that position, and if one is found, starts playing its radio stream. The dial and buttons adjust the experience once a city is latched.

**Two operating modes** are toggled by the jog button:
- `station` mode — the dial cycles through stations within the current city
- `city` mode — the dial cycles through other nearby cities, reloading the first station for each

**The latch mechanism** prevents jitter. Once a city is found, the encoder's raw position is frozen until the user moves the reticule more than `STICKINESS` encoder steps away. Without this, the station would change continuously while the user browses with the dial.

### Module Dependency Graph

```mermaid
graph TD
    main["main.py\n(App)"]

    main --> positional["positional_encoders.py\nSPI → lat/lon + latch"]
    main --> dial["dial.py\nGPIO quadrature encoder"]
    main --> buttons["buttons.py\nGPIO button manager"]
    main --> display["display.py\nI2C LCD display"]
    main --> led["rgb_led.py\nGPIO LED"]
    main --> audio["audio_async.py\nVLC audio player"]
    main --> database["database.py\nPure functions"]
    main --> coordinates["coordinates.py\nCoordinate type"]

    database --> stations[("stations/stations.json")]
    audio --> vlc[("python-vlc")]
    positional --> spidev[("spidev")]
    display --> i2c[("liquidcrystal_i2c")]
    buttons --> gpio[("lgpio / RPi.GPIO")]
    dial --> gpio
    led --> gpio
```

The `streaming/` directory is intentionally omitted — none of its modules are imported by the main application.

---

## 4. Module Reference

### 4.1 `main.py` — App Controller

The `App` class is the central controller. `__init__` instantiates all hardware objects and loads the station database. `run()` contains the entire main loop and all button callback definitions.

**Key methods:**

| Method | Purpose |
|---|---|
| `run()` | Main async loop: poll encoders, search cities, drive display and audio |
| `next_station(direction)` | Cycle `jog_idx` within `self.stations` |
| `next_city(direction)` | Cycle `jog_idx` within `self.cities`, reload station list |
| `switch_mode()` | Toggle `self.mode` between `"station"` and `"city"` |
| `save_state()` | Serialise app state to `~/cache/radioglobe.json` |
| `load_state()` | Restore state from cache on startup |

**Non-obvious details:**
- `load_state()` is called **twice** in `run()`: once at line 128 (before the splash screen) and once at line 242 (after). The second call is wrapped in a try/except and overwrites the first. Only the second call matters.
- Button callback functions are defined as nested `async def` closures inside `run()`, capturing `self`. This works but makes the ~70 lines hard to navigate and impossible to unit-test.
- `self.city` is passed to `display.update()` as a raw string (e.g. `"London,GB"`) but the display formats it directly — no truncation for long city names.
- `save_state()` always writes `"latch": True`; on `load_state()` this causes the app to immediately resume playing the last station on next boot (the warm-restart path).

---

### 4.2 `database.py` — Station Data

Pure functions with no side effects and no hardware dependencies. The most testable module in the project.

**Functions:**

| Function | Returns | Notes |
|---|---|---|
| `load_stations(path)` | `dict` keyed by `"City,CC"` | Returns empty dict on FileNotFoundError |
| `build_cities_index(stations_data)` | `dict[(lat_idx, lon_idx) → city_name]` | Converts lat/lon degrees to 0–1023 grid indices |
| `look_around(origin, fuzziness)` | `list` of `(lat, lon)` tuples | Returns search zone around a point |
| `get_stations_by_city(stations, city)` | `list` of `(name, url)` tuples | The canonical station list format |
| `get_found_cities(search_area, city_map)` | `list` of city strings | Used in some test scripts; superseded by `find_all_cities` in `main.py` |

**Coordinate formula:** `index = round((degrees + 180) * 1024 / 360)`. This maps −180°→0 and +180°→1024.

**`look_around()` detail:** `fuzziness=1` returns just the origin point; `fuzziness=2` returns 9 points (3×3 area); `fuzziness=3` returns 25 points (5×5 area). The search starts bottom-left and scans horizontally — this matches ergonomics (70% of people are right-eye dominant and hold the globe below eye level).

**Important bug in `build_cities_index()`:** The docstring says the index supports multiple cities per cell (`{(609, 178): ['Riverside,US-CA', 'San Bernardino,US-CA'], ...}`), but the actual code does not — it stores only the first city that maps to each cell and silently ignores the rest:

```python
if city_coords not in cities_index:
    cities_index[city_coords] = location  # second city at same cell is dropped
```

At ENCODER_RESOLUTION=1024, one grid cell covers ~0.35°, meaning cities within ~40 km can collide. See [Improvement 8](#improvement-8-fix-build_cities_index-city-collision).

**Legacy functions** at the bottom of the file (`get_station_by_index`, `get_first_station`, `get_all_urls`, `get_stations_info`) are not used by the main application. They exist for test scripts and older code paths.

---

### 4.3 `positional_encoders.py` — Globe Position

Reads two SPI absolute rotary encoders and maintains the current lat/lon position.

**Key behaviour:**
- Each encoder is read via SPI bus 0, device 0 (latitude) and device 1 (longitude), at 5000 Hz, SPI mode 1.
- Raw readings are 16 bits; the top 10 bits (after shifting right by 6) give the 0–1023 position.
- `check_parity()` validates each reading. If parity fails, the entire read returns `None` and is discarded.
- Latitude is inverted: `readings[0] = ENCODER_RESOLUTION - readings[0]`. This corrects for encoder mounting orientation.

**The latch mechanism:**
- `latch(lat, lon, stickiness)` stores the latched position and sets `latch_stickiness` to the threshold value.
- While latched, `run_encoder()` still reads SPI but only updates `self.latitude`/`self.longitude` if the new reading differs by more than `latch_stickiness` steps. If it does, `latch_stickiness` is set to `None` (unlatched) and reading resumes normally.
- `is_latched()` returns `True` if `latch_stickiness is not None`.

**Calibration:** `zero()` sets offsets so the current physical position maps to (512, 512), which corresponds to 0°N, 0°E (the equator / prime meridian intersection). `get_readings()` always returns the offset-adjusted value modulo ENCODER_RESOLUTION.

**Note:** The `if __name__ == "__main__":` block at the bottom of this file (lines 109–142) is a hardware test script, not part of the class. It hardcodes `STICKINESS = 10`.

---

### 4.4 `dial.py` — Station / City Selector

Reads a quadrature rotary encoder on GPIO pins 17 (clock) and 18 (direction).

- `run_encoder()` uses `asyncio.to_thread(GPIO.wait_for_edge, pin, GPIO.FALLING)` to avoid blocking the event loop. On each falling edge it reads the direction pin and stores the result (debounced at 300ms).
- `get_direction()` is a one-shot read: it returns the stored direction and resets the internal value to 0. The main loop calls this every 100ms.
- The returned value is inverted (`* -1`) to correct for physical wiring convention. +1 means clockwise, −1 means counter-clockwise.

---

### 4.5 `buttons.py` — Button Manager

Manages four GPIO buttons with short and long press detection.

**Button definition tuple:**
```python
("Name", gpio_pin, short_handler, long_handler, press_callback)
```
- `press_callback` fires immediately on press-down (used for instant LED feedback)
- `short_handler` fires on release if held < 1.0 second
- `long_handler` fires on release if held ≥ 1.0 second

`AsyncButton` uses GPIO fall-edge callbacks that bridge into the asyncio event loop via `loop.call_soon_threadsafe()`. `AsyncButtonManager` holds all buttons, runs a background polling task, and dispatches events via an `asyncio.Queue`.

---

### 4.6 `display.py` — LCD Display

Drives a 20×4 I2C character LCD at address 0x27 on bus 1, using the `liquidcrystal_i2c` library.

- Internally maintains a 4-line text buffer and an `asyncio.Event` (`changed`). When `update()` or `message()` is called, the buffer is updated and the event is set.
- `_display_loop()` is an asyncio Task that waits for the event, writes all 4 lines to the LCD, and sleeps 100ms. This coalesces rapid updates — important because I2C is slow.

**Display layout when playing:**
```
Line 0: 51.50N, 0.13W        ← Coordinate.__str__()
Line 1: London,GB             ← City name
Line 2: --------              ← Volume bar (ASCII dashes, scales 0–100)
Line 3: BBC Radio 2           ← Station name
```

**Non-obvious detail:** `update()` accepts a `Coordinate` object for the first argument, but some call sites in `main.py` pass bare tuples (e.g. `self.display.update((0, 0), "CALIBRATE", 0, "", False)` at line 258). This works accidentally because `str((0, 0))` produces `"(0, 0)"` rather than a formatted coordinate string. See [Improvement 9](#improvement-9-surface-the-coordinate-type-consistently).

---

### 4.7 `audio_async.py` — Audio Player

Wraps `python-vlc` directly. Does not import from `streaming/`.

```python
class AudioPlayer:
    def __init__(self):
        self.instance = vlc.Instance("--input-repeat=-1")  # infinite repeat
        self.player = self.instance.media_player_new()
```

- `play(city, station)` stops any current playback and starts the new URL immediately. VLC handles playlist URLs (`.m3u`, `.pls`) internally.
- `--input-repeat=-1` means the stream restarts automatically if the connection drops.
- Volume is managed via VLC's `audio_get_volume` / `audio_set_volume`, range 0–100.
- There is no async integration — `play()` returns immediately and VLC streams in its own threads. There is currently no way to detect whether a stream has actually connected. Silent failures produce silence. See [Improvement 12](#improvement-12-add-dead-stream-detection).

---

### 4.8 `rgb_led.py` — Status LED

Three GPIO output pins (R=22, G=23, B=24) with simple on/off control (no PWM).

`led_task(led, led_running, colour, duration)` is a standalone coroutine, always spawned with `asyncio.create_task()` rather than awaited. It:
1. Checks the `led_running` Event to prevent overlapping flashes
2. Sets the event, turns the LED on
3. Sleeps for `duration` seconds
4. Turns the LED off and clears the event

**Colour conventions used in `main.py`:**
- Green: city found/latched, button press feedback
- Blue: dial turned, volume button press

---

### 4.9 `coordinates.py` — Coordinate Type

A simple value object. `__str__` produces the display format used on the LCD:

```python
>>> str(Coordinate(51.5074, -0.1278))
'51.51N, 0.13W'
```

Equality comparison rounds to 2 decimal places (`ROUNDING = 2`). Used by `main.py` and `display.py` but not consistently — see [Improvement 9](#improvement-9-surface-the-coordinate-type-consistently).

---

### 4.10 `radio_config.py` — Configuration

Defines constants for the application. **Warning: many of these are not actually used.** See [§8 Configuration Reference](#8-configuration-reference) for the full discrepancy table.

Also has a side-effect on import: sets up `logging.basicConfig()`. Logging setup should live in `main.py`.

---

### 4.11 `streaming/` — Historical Streaming Implementations

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

1. `PositionalEncoders.run_encoder()` reads SPI every 200ms and updates `self.latitude` / `self.longitude` (unless latched).
2. The main loop (100ms sleep) calls `encoders.get_readings()` — returns the offset-adjusted `(lat, lon)` tuple.
3. `look_around(coords, FUZZINESS=3)` generates 25 grid coordinates surrounding the current position.
4. `find_all_cities(zone, self.cities_info)` checks each coordinate against the spatial index dict.
5. If cities are found and the encoders are not already latched:
   - `encoders.latch(*coords, stickiness=10)` freezes the position.
   - `jog_idx` and `city_idx` reset to 0.
   - The LED flashes green.
6. `get_stations_by_city(self.stations_info, city)` fetches the station list as `[(name, url), ...]`.
7. `audio_player.play(city, station)` passes the URL to VLC.
8. `display.update(coords, city, 0, station_name, False)` refreshes the LCD.

### Flow B: User Turns the Dial

1. `AsyncDial.run_encoder()` detects a falling edge on GPIO 17, reads direction from GPIO 18.
2. The main loop reads `dial.get_direction()` — non-zero means rotation.
3. The LED flashes blue.
4. If `mode == "station"`: `next_station(direction)` increments/decrements `jog_idx` within `self.stations` (wraps around).
5. If `mode == "city"`: `next_city(direction)` increments/decrements `jog_idx` within `self.cities`, fetches the first station for the new city.
6. `display.update()` and `audio_player.play()` update immediately.

---

## 6. State Management

The app maintains several pieces of mutable state in `App` instance attributes:

| Attribute | Type | Meaning |
|---|---|---|
| `self.stations` | `list[(name, url)]` | Stations for the current city |
| `self.station` | `tuple(name, url)` | Currently playing station |
| `self.station_idx` | `int` | Index of `station` in `stations` |
| `self.cities` | `list[str]` | Cities found in the current search zone |
| `self.city` | `str` | Currently selected city (e.g. `"London,GB"`) |
| `self.city_idx` | `int` | Index of `city` in `cities` |
| `self.jog_idx` | `int` | Shared index used by both station and city navigation |
| `self.mode` | `str` | `"station"` or `"city"` |
| `self.encoders.*` | — | Lat/lon, offsets, latch state (owned by `PositionalEncoders`) |

On shutdown (long press of mid button), `save_state()` serialises all of this to `~/cache/radioglobe.json`. On the next boot, `load_state()` restores it, sets `latch_stickiness = True`, and the app immediately resumes playing the last station.

**Fragility note:** The saved `stations` and `cities` lists are snapshots. If `stations.json` is updated between boots (e.g. after an install), the saved indices may point to different or non-existent stations. The restore currently uses the saved lists as-is rather than re-querying from `stations_info`.

---

## 7. Concurrency Model

The entire application runs on a single asyncio event loop. Understanding this is essential before modifying any hardware module.

**Tasks running concurrently:**
```python
asyncio.create_task(dial.run_encoder())           # polls GPIO, 300ms debounce
asyncio.create_task(encoders.run_encoder())       # reads SPI every 200ms
asyncio.create_task(display._display_loop())      # writes LCD on change event
asyncio.create_task(button_manager.handle_events()) # dispatches button callbacks
# main while loop sleeps 100ms between iterations
```

**GPIO interrupt bridging:** RPi.GPIO fires button callbacks on a separate interrupt thread. These callbacks call `loop.call_soon_threadsafe(...)` to schedule coroutines back onto the asyncio event loop. This is the correct pattern — do not call `asyncio.create_task()` directly from a GPIO callback thread.

**Blocking calls:** `GPIO.wait_for_edge()` is blocking and is wrapped with `asyncio.to_thread()` in `dial.py`. Any new hardware code that polls with blocking calls must do the same.

**LED tasks** are always `create_task`'d rather than awaited — they are fire-and-forget. The `led_running` Event prevents concurrent flashes.

**What to be careful about:** Do not put any blocking call (file I/O, `time.sleep()`, synchronous network calls) directly in the main loop body. Every blocking call holds up all other hardware tasks.

---

## 8. Configuration Reference

`radio_config.py` is not reliably used. Here is the ground truth:

| Parameter | `radio_config.py` value | Actual value used | Notes |
|---|---|---|---|
| `FUZZINESS` | 3 | Imported in `main.py` | ✓ Fixed |
| `STICKINESS` | 10 | Imported in `main.py` | ✓ Fixed |
| `ENCODER_RESOLUTION` | 1024 | Imported in `database.py` and `positional_encoders.py` | ✓ Fixed |
| `VOLUME_INCREMENT` | 1 | Not used — `main.py` hardcodes delta of 10 | Dead constant |
| GPIO pin numbers | `PIN_DIAL_CLOCK`, `PIN_BTN_*`, `PIN_LED_*` | Imported in each hardware module | ✓ Fixed |
| I2C address | `I2C_LCD_ADDR = 0x27` | Imported in `display.py` | ✓ Fixed |

The intended fix is straightforward: see [Improvement 1](#improvement-1-centralise-encoder_resolution-and-use-radio_configpy) and [Improvement 2](#improvement-2-fix-the-stickiness-inconsistency).

---

## 9. Testing

Some files in `tests/` are proper unit tests that run on any machine. Others are hardware integration scripts that require a connected Raspberry Pi.

**Unit tests (run without hardware):**
```bash
uv run pytest tests/get_stations_by_city_test.py
```

**Hardware / integration scripts** (require Pi): `simulation_test.py`, `positional_encoders_test.py`, `dial_test.py`, `streaming_cvlc_test.py`, `async_streamer_test.py`.

These are not separated by directory, and there is no `pytest.ini` or `pyproject.toml` test config that marks or excludes them. Running `pytest tests/` on a development machine will fail on all hardware scripts. See [Improvement 11](#improvement-11-separate-integration-test-scripts).

---

## 10. Suggested Improvements

These are ordered from lowest to highest effort. None require a rewrite — all are incremental changes. The project is a hobby/maker project; these are suggestions, not mandates.

---

### Improvement 1: Centralise `ENCODER_RESOLUTION` and use `radio_config.py`

**Problem:** `ENCODER_RESOLUTION = 1024` is defined in three separate files (`radio_config.py`, `database.py`, `positional_encoders.py`). The import in `database.py` is commented out (line 5).

**Fix:** Uncomment the import in `database.py` and add an import to `positional_encoders.py`. Remove the three local definitions.

**Effort:** ~20 minutes.

---

### Improvement 2: Fix the `STICKINESS` inconsistency

**Problem:** `radio_config.py` defines `STICKINESS = 3`, but `main.py` uses a local `STICKINESS = 10` (line 124) that shadows the imported value. The config value is never used. A developer reading `radio_config.py` will have the wrong mental model.

**Fix:** Update `radio_config.py` to `STICKINESS = 10` (reflecting actual behaviour), then import it in `main.py` instead of using a local. Similarly, the `FUZZINESS` local in `main.py` shadows `radio_config.FUZZINESS` with the same value — remove the local and just import.

**Effort:** 10 minutes.

---

### Improvement 3: Remove the duplicate `load_state()` call

**Problem:** `load_state()` is called at `main.py` line 128 (before the splash screen) and again at line 242 (inside the try block, after the splash screen). The second call is in a try/except and overwrites everything the first call did. The first call is dead code.

**Fix:** Remove line 128. Keep only line 242.

**Effort:** 2 minutes.

---

### Improvement 4: Rename the `_async` modules

**Done.** Modules renamed: `display_async` → `display`, `dial_async` → `dial`, `buttons_async` → `buttons`, `positional_encoders_async` → `positional_encoders`, `rgb_led_async` → `rgb_led`. `dial_button_async.py` deleted (unused).

**Fix:** Rename to `display.py`, `dial.py`, `buttons.py`, `positional_encoders.py`, `rgb_led.py`. Update imports in `main.py` and tests. While at it, `dial_button.py (deleted)` is an unused alternative to `dial.py` + `buttons.py` that can be deleted.

**Effort:** ~30 minutes including import updates. Do this in one commit.

---

### Improvement 5: Centralise GPIO pin constants

**Done.** All GPIO pins and the I2C address are now defined in `radio_config.py` and imported in `dial.py`, `rgb_led.py`, `display.py`, `buttons.py`, and `main.py`.

---

### Improvement 6: Move button callbacks out of `App.run()`

**Problem:** `App.run()` contains ~70 lines of nested `async def` functions (the button handlers), defined as closures that capture `self`. This makes `run()` hard to read and the handlers impossible to unit-test.

**Fix:** Move each handler to a named method on `App`:
```python
async def _on_volume_up(self): ...
async def _on_volume_down(self): ...
async def _on_calibrate(self): ...
async def _on_shutdown(self): ...
```
Wire them up in `run()` using `self._on_volume_up` etc. No functional change.

**Effort:** ~1 hour. Mechanical refactor.

---

### Improvement 7: Add a `start()` / `stop()` lifecycle protocol

**Problem:** Each hardware module has a slightly different lifecycle API. `AsyncDial` has `start()`/`stop()`. `PositionalEncoders` has `start()`/`stop()`. `Display` has `start()`/`stop()`. `AudioPlayer` only has `stop()`. `RGBLed` has neither. The cleanup block in `App.run()` is ad-hoc as a result.

**Fix:** Document (or enforce with an ABC) that all hardware objects implement `start()` and `async stop()`. Add the missing methods to `AudioPlayer` and `RGBLed`. Then the cleanup block becomes:
```python
finally:
    for hw in [self.audio_player, self.dial, self.encoders, self.display]:
        await hw.stop()
    GPIO.cleanup()
```

**Effort:** ~1 hour.

---

### Improvement 8: Fix `build_cities_index()` city collision

**Problem:** The docstring for `build_cities_index()` says it supports multiple cities per grid cell, but the code does not — it uses `if city_coords not in cities_index`, silently dropping any second city that maps to the same cell. Cities within ~40 km of each other can collide at 1024-step resolution.

**Fix:** Change the index value from a string to a list:
```python
cities_index.setdefault(city_coords, []).append(location)
```
Then update `find_all_cities()` in `main.py` (line 139) to flatten the lists it receives.

**Effort:** ~30 minutes including test updates.

---

### Improvement 9: Surface the `Coordinate` type consistently

**Problem:** `display.update()` accepts a `Coordinate` object for its first argument, but `main.py` passes bare tuples in two places (lines 258 and 215). A bare tuple `(0, 0)` displays as `"(0, 0)"` on the LCD rather than `"0.00N, 0.00E"` — a visual bug that's easy to miss.

**Fix:** Update those two call sites:
```python
# line 258
self.display.update(Coordinate(0, 0), "CALIBRATE", 0, "", False)
# line 215
self.display.update(Coordinate(0, 0), "Shutdown", 0, "", False)
```
Add a type hint to `display.update()` to prevent recurrence.

**Effort:** 10 minutes.

---

### Improvement 10: Introduce an `AppState` dataclass

**Problem:** `App` carries ~8 closely related mutable attributes (`stations`, `station`, `station_idx`, `cities`, `city`, `city_idx`, `jog_idx`, `mode`) that are always modified together. `save_state()` and `load_state()` reference them via fragile string keys in a raw dict.

**Fix:** Define a dataclass:
```python
@dataclass
class AppState:
    stations: list = field(default_factory=list)
    station: tuple = None
    station_idx: int = 0
    cities: list = field(default_factory=list)
    city: str = None
    city_idx: int = 0
    jog_idx: int = 0
    mode: str = "station"
```
Use `dataclasses.asdict()` for serialisation. Store as `self.state` on `App`. This makes the state boundary explicit and the serialisation type-safe.

**Effort:** ~1–2 hours.

---

### Improvement 11: Separate integration test scripts

**Problem:** `tests/` contains a mix of proper unit tests and hardware scripts. Running `pytest tests/` on a development machine fails on the hardware scripts. There's no test configuration to separate them.

**Fix:** Move hardware scripts to `tests/integration/`. Add to `pyproject.toml`:
```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
ignore = ["tests/integration"]
```
CI (if added) can then run only the unit tests.

**Effort:** ~30 minutes.

---

### Improvement 12: Add dead-stream detection

**Problem:** If a station URL is offline or unreachable, VLC starts, encounters an error, and the app produces silence. There is no feedback to the user and no recovery attempt.

**Fix:** Fire a background task after `audio_player.play()` that polls `player.get_state()` after a 3-second delay:
```python
async def _check_stream():
    await asyncio.sleep(3)
    if self.audio_player.player.get_state() == vlc.State.Error:
        asyncio.create_task(led_task(led, led_running, "red", 0.5))
        self.display.update(coords, self.city, 0, "Stream error", False)
```

**Effort:** ~2 hours including hardware testing.

---

## 11. What's Already Good

**`database.py` pure-function design.** All station and city lookups are stateless functions with no hardware dependencies. They're unit-testable without mocking anything and straightforward to reason about. The one-time index build at startup (`build_cities_index`) is the right trade-off — it makes every 100ms poll O(1).

**The spatial search approach.** Building a 1024×1024 grid dict at startup and doing dict lookups in the main loop is efficient and simple. `look_around()` with fuzziness is the right way to handle the physical imprecision of pointing at a globe.

**The asyncio architecture is fundamentally sound.** GPIO interrupt callbacks are correctly bridged back to the event loop via `call_soon_threadsafe`. Blocking GPIO calls are wrapped in `asyncio.to_thread`. The cooperative sleep pattern in the main loop gives all tasks CPU time.

**The latch mechanism.** Freezing the encoder position until the user moves significantly is a genuinely clever UX solution. Without it, browsing stations while holding the globe still would be impossible — any tiny vibration would trigger a city change.

**Display update coalescing.** The buffer + `asyncio.Event` pattern in `display.py` correctly batches rapid updates. I2C is slow (~100µs per byte); writing all 4 LCD lines takes several milliseconds, so coalescing is not just an optimisation — it's necessary for responsiveness.

**The systemd user service** (not system service) is the correct approach for an application that uses PulseAudio. PulseAudio runs per-user; a system service cannot see the user's audio session. Running as the logged-in user (with `loginctl enable-linger`) is the only reliable way to get auto-detected audio outputs including Bluetooth.
