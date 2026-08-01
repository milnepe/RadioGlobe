# Changelog

All notable changes to this project are documented in this file.

## [0.5.16] - 2026-08-01
### Changed
- Simplified the city/station navigation logic in `AppState`/`Navigator`/
  `main.py` for readability, with no functional or performance change.
  `AppState.jog_idx` was dual-purpose (station index in `MODE_STATION`,
  city index in `MODE_CITY`), forcing `Navigator.switch_mode()` to
  re-derive it via a linear search on every mode toggle, and forcing
  `select_station()` to deliberately never touch it. Split into
  independent `station_idx`/`city_idx` fields instead — `switch_mode()`
  now needs no recompute at all. This also fixed two latent low-severity
  bugs the shared field caused: `remove_failed_station()` could modulo a
  city index into the station list if a stream failed while the dial was
  in `MODE_CITY`, and `load_state()` always overwrote the shared index
  with a station-match value on warm restart, discarding city-index
  meaning from a `MODE_CITY` shutdown. Old on-disk cache files (single
  `"jog_idx"` key) still load without error.
- Moved city-latching/selection out of `main.py`'s `App` and into
  `Navigator` (`select_city()`, `next_city_and_select_station()`,
  `refresh_nearby_cities()`), matching the codebase's existing convention
  that `Navigator` owns all state mutation — `App` no longer touches
  `nav.state` directly anywhere, and the two event loops shrink to their
  real hardware/orchestration concerns.
- `database.py`'s legacy `look_around`/`get_found_cities`/`get_stations_info`
  (superseded in production, used only by two hand-run hardware
  diagnostic scripts) now have docstring notes explaining the duplication.

## [0.5.15] - 2026-08-01
### Fixed
- A raw JSON `NaN` in a station's `name` field (some entries in
  `stations.json` had never been cleaned up) reached `Display.update()`
  and crashed the whole service with `TypeError: 'float' object is not
  subscriptable`, since floats aren't subscriptable. Third recurrence of
  this class of bug (see `c5d5058`, `d9df2d9`), fixed in code this time
  instead of just the data: `database.get_stations_by_city()` now filters
  out any station entry whose `name`/`url` aren't strings, and
  `Display.update()` coerces `station` to `str()` before slicing in the
  branch that was missed by an earlier fix (`7c44cc5`) to the arrows
  branch.

## [0.5.14] - 2026-07-31
### Changed
- `AudioPlayer.play()` took a `city` string (used only for a debug log) and
  a `(name, url)` station tuple, when all VLC ever needed was the URL.
  `audio_async.py` now only ever deals in URL strings — it has no concept
  of a "city" or "station". No user-facing behavior change.
- Extracted `App._play_station()`: three of the four call sites that showed
  and played `self.nav.state.station` (`_encoder_loop`, `_dial_loop`,
  `run()`'s warm-restart path) were byte-identical
  `display.show_station()` + `audio_player.play()` blocks, each repeating
  the same opaque `station[0]`/`station[1]` tuple indexing. `_play_station()`
  unpacks `(name, url)` once and returns the URL; call sites pass it to
  `_start_monitor_stream()`, or in `_monitor_stream()`'s own retry path,
  assign it directly to `expected_url`.

## [0.5.13] - 2026-07-31
### Changed
- Follow-up to 0.5.12's decoupling work, focused entirely on removing
  remaining hardware-knowledge leaks between `main.py`'s `App` and the
  hardware wrapper modules it owns. No user-facing behavior changes —
  verified after each step with unit tests, a hardware-mocked smoke test
  constructing a real `App()`, and (for the button pin change) inspection
  of the resulting `ButtonDefinition`s against the real pin/callback wiring.
  - Moved every constant in `radio_config.py` describing a single
    component's physical wiring or protocol — GPIO pins, the I2C address,
    dial debounce timing, encoder resolution — into the module that owns
    that hardware, as private (leading-underscore) constants. `radio_config.py`
    now holds only app-behavior tuning (volume, display/LED durations,
    search fuzziness/stickiness, paths, log level). `ENCODER_RESOLUTION`
    was placed in `database.py` rather than `positional_encoders.py`, so
    the pure grid-math module stays hardware-free — `positional_encoders.py`
    imports it from there. `PIN_DIAL_CLOCK`/`PIN_DIAL_DIR` had zero Python
    consumers (the kernel rotary-encoder driver reads the pins straight
    from `install.sh`'s `dtoverlay` line) and were deleted rather than
    relocated; that line is now commented as the single source of truth.
  - `buttons.py` and `rgb_led.py` now each own their own
    `GPIO.setmode(GPIO.BCM)` call instead of relying on `App.__init__` to
    have set it first — the same self-sufficiency fix 0.5.12 already made
    for `buttons.py` alone, now applied consistently. `App.__init__` no
    longer calls `GPIO.setmode()` at all.
  - Button GPIO pins are now fully encapsulated in `buttons.py`: since the
    name-to-pin mapping is fixed by this project's custom board (not an
    app-level choice), `main.py` no longer imports a single raw pin number.
    It builds `button_definitions` from `buttons.py`'s new `JOG_BUTTON`/
    `TOP_BUTTON`/`MID_BUTTON`/`BOTTOM_BUTTON` constants via
    `NamedTuple._replace()`, attaching only its own callbacks.
  - `GPIO.cleanup()` ownership moved the same way as `setmode()`:
    `AsyncButtonManager.stop()` and `RGBLed.stop()` each release only the
    GPIO channels they set up, instead of `App.run()` calling a bare
    process-wide `GPIO.cleanup()` in its teardown. `main.py` no longer
    imports `RPi.GPIO` at all — `App` has zero direct GPIO dependency left.
  - `PositionalEncoders` gained `get_calibration()`/`restore_calibration()`.
    `App.save_state()`/`load_state()` used to read and write
    `self.encoders.latitude`/`longitude`/`latitude_offset`/`longitude_offset`
    directly (and set `latch_stickiness = True` by hand on restore) — the
    last place `App` knew a hardware object's internal field names instead
    of going through its public API. Cache file format is unchanged.

## [0.5.12] - 2026-07-31
### Changed
- Decoupled `radioglobe/main.py`'s `App` god object, which had mixed
  hardware orchestration, station/city selection state, navigation logic,
  display formatting, and LED signalling in one ~440-line class. `App` is
  now just hardware construction, the two event loops, and button dispatch.
  - `AppState` (selection state) and `Navigator` (station/city data and the
    logic that mutates it) moved into new hardware-free modules
    (`radioglobe/app_state.py`, `radioglobe/navigation.py`), unit-testable
    off a Pi the same way `database.py` always was — previously this
    navigation logic (latching, dial cycling, mode switching) had zero
    automated test coverage.
  - `database.py` gained `get_coords_by_city()`/`match_saved_station()`.
  - `Display` gained `show_station()`/`show_status()`, replacing ad hoc
    argument-building in `App`.
  - `RGBLed` gained a `flash()` method, absorbing the old free-function
    `led_task()` + a manually shared `asyncio.Event`.
  - `save_state()`/`load_state()` moved into `Navigator`, taking/returning
    plain encoder-offset dicts rather than a `PositionalEncoders` object,
    so `Navigator` stays hardware-free. The on-disk cache format
    (`~/cache/radioglobe.json`) is unchanged — existing cache files remain
    readable.

  No user-facing behavior changes — internal readability/testability
  refactor, verified after each step with a hardware-mocked smoke test
  against the real `stations.json` and, for the riskier steps, full
  on-device regression passes (globe latch, dial in both modes, all 4
  buttons, save/restore across a restart).

### Fixed
- `AsyncButtonManager.handle_events()` is the single consumer for every
  button's short/long-press events. An unhandled exception from any one
  button's handler killed that shared loop outright — silently stopping
  press dispatch for *all four buttons*, not just the one that failed.
  Press-down LED feedback kept working (it runs on a separate per-button
  task), making the failure look like "the LED still flashes but nothing
  else happens," with no visible error. Now wrapped in try/except with the
  failure logged.
- `buttons.py`'s `AsyncButton`/`AsyncButtonManager` no longer depended on
  `App` having already called `GPIO.setmode(GPIO.BCM)` — a regression from
  centralizing that call into `App.__init__` (0.5.x internal refactor)
  that broke every standalone script constructing `AsyncButtonManager`
  directly (`tests/integration/button_test.py` and a new
  `button_reliability_test.py`), which would otherwise fail with
  "Please set pin numbering mode..." on real hardware.
  `AsyncButtonManager` now guarantees this precondition itself.
- Investigated a real-hardware report of the Mid button (calibrate/
  shutdown) going completely unresponsive. Confirmed via direct GPIO edge
  monitoring (`gpiomon`) with the app fully stopped that the press wasn't
  reaching the pin at all — a wiring/connector fault, not a software bug.
  Traced to the shared `J1` "Disp Buttons" connector (all four push-buttons
  share one connector, per the board schematic): reseating/reconnecting it
  resolved the issue, confirmed with a purpose-built reliability check
  (`tests/integration/button_reliability_test.py`, comparing a raw GPIO
  poll against `AsyncButtonManager`'s registered presses) run against
  Top/Mid/Bottom individually and then with each other subsystem
  reconnected in turn.

## [0.5.11] - 2026-07-28
### Fixed
- Dial contact bounce caused inconsistent/skipped city and station selection:
  the kernel `rotary_encoder` driver (introduced when the dial migrated off
  `RPi.GPIO` polling) doesn't fully suppress mechanical contact bounce even
  at its most conservative setting. `AsyncDial` (`radioglobe/dial.py`) now
  coalesces bursts of raw `REL_X` events into a single net direction over a
  short quiescence window (`DIAL_DEBOUNCE_S`) before enqueuing, instead of
  acting on every raw kernel event individually.
- City-mode dial navigation never registered counter-clockwise turns —
  traced to a wiring fault, not software: encoder pin A was connected to
  GND and pin C (Common) to GPIO17, swapped from the correct wiring.
  Corrected on-device; see `docs/JOG_WHEEL_INVESTIGATION.md` for the full
  diagnostic trail and the correct pinout.

Both fixes were verified end-to-end on real hardware: dial turns in
city/station mode now produce exactly one clean step per physical click in
both directions, confirmed via live `journalctl` logs during controlled
clockwise/counter-clockwise testing.

## [0.5.10] - 2026-07-27
### Fixed
- `make deploy`'s rsync only excluded `.git`, `__pycache__`, and `*.pyc`,
  so it shipped the entire local dev environment to the device's
  `~/RadioGlobe` staging checkout: the x86_64 `.venv` (wrong architecture,
  irrelevant since the device has its own venv under `/opt/radioglobe`),
  `.pytest_cache`, `.ruff_cache`, `.claude` (local Claude Code settings),
  `.python-version`, and `.lgd-nfy0`. Added the missing excludes.

Found and fixed while deploying v0.5.9 to real hardware this session;
already-deployed stray files were cleaned up by hand on the device, and
`make deploy` was re-run afterward to confirm only `Makefile`/`VERSION`
transferred.

## [0.5.9] - 2026-07-27
### Fixed
- Shutdown (Mid button long-press) had stopped working on real hardware:
  `radioglobe.service` runs with no TTY, so `sudo poweroff` had no way to
  prompt for a password, and no `NOPASSWD` rule existed for the
  `radioglobe` user. `install.sh` now installs a scoped
  `/etc/sudoers.d/radioglobe-poweroff` drop-in (`NOPASSWD` for
  `/usr/sbin/poweroff` only, validated with `visudo -c` before being put
  in place) instead of relying on the default user having blanket
  passwordless sudo.

### Changed
- README updated to reflect testing on Raspberry Pi OS Trixie: OS
  installation, upgrading, and troubleshooting sections no longer assume
  Bookworm only.

Verified on real hardware via `sudo -n -l`, which now lists
`(root) NOPASSWD: /usr/sbin/poweroff` for `radioglobe`. Did not trigger an
actual `poweroff` during verification, to avoid requiring a physical
power-cycle of the device.

## [0.5.8] - 2026-07-27
### Fixed
- `install.sh` failed on Raspberry Pi OS Trixie: the bluetooth `rfkill`
  check used the bare command, but the `radioglobe` user's non-interactive
  `PATH` excludes `/usr/sbin` on Trixie, causing "command not found"; now
  run via `sudo`, whose `secure_path` includes it.
- Added `swig` and `liblgpio-dev` to the apt dependency list — building the
  `lgpio` Python wheel needs `swig`, and linking it needs `liblgpio-dev`
  (only `liblgpio1`, the runtime lib, is pulled in transitively on Trixie).
- `install.sh` crashed copying a missing `VERSION` file even though it
  already had a fallback to report `"unknown"` for display; now writes the
  resolved version string instead of copying the file.
- `install.sh` now falls back to `git describe --tags --always --dirty`
  for `VERSION` when run from a real git clone on the target host (no
  `VERSION` file, but a real `.git` dir), instead of always reporting
  `"unknown"` in that case.

Physically tested end to end on real RadioGlobe hardware (Debian 13/Trixie)
after each fix; confirmed `install.sh` completes cleanly and
`/opt/radioglobe/VERSION` / the rendered `radioglobe.service` unit show the
correct resolved version.

## [0.5.7] - 2026-07-27
### Changed
- Replaced positional button-definition tuples with a `ButtonDefinition`
  NamedTuple (`radioglobe/buttons.py`), removing the `len(definition) == 5`
  arity-branching hack in `AsyncButtonManager.__init__` in favor of a
  default `press_cb=None` field.

No user-facing behavior change — physically tested all four buttons
(Jog, Top, Mid, Bottom, short and long press) on real hardware.

## [0.5.6] - 2026-07-27
### Changed
- Organized `radioglobe/main.py` imports into stdlib/third-party/local groups
  (PEP 8), consolidating repeated single-name imports.
- Removed the redundant `import dataclasses` module import alongside
  `from dataclasses import dataclass, field`.
- Replaced hardcoded sleep/LED-flash/volume-level magic numbers in async
  methods with named constants in `radio_config.py`.
- Extracted ten duplicated `self.display.update(...)` call shapes into
  `_display_current_station()` and `_display_status()`.
- `Display.update()` call sites now pass `volume`/`station`/`arrows` as
  keyword arguments instead of unclear bare positionals.

### Fixed
- `_get_coords_by_city()` now raises `KeyError` instead of silently logging
  a warning and returning a fake `Coordinate(0, 0)` when a city isn't found.
  Only `load_state()` (the one place a cached city can go stale after a
  `stations.json` update) catches it, falling back to the existing
  calibrate-mode recovery path.

No user-facing behavior changes — internal readability/robustness cleanup.

## [0.5.5] - 2026-07-27
### Changed
- Extracted mode (`station`/`city`) and LED colour magic strings into a new
  `radioglobe/constants.py` module, removing repeated raw string literals.
- Simplified `App.switch_mode()` by replacing nested ternaries with a flat
  if/else.
- Extracted the saved-station matching logic in `load_state()` into a
  standalone `_match_saved_station()` helper.
- Extracted the repeated city/station validity check into a single
  `_has_essential_state()` helper.
- Deduplicated the volume-display logic shared by `_update_volume()` and
  `_update_volume_level()` into `_show_volume_briefly()`.

No behavior changes — internal readability refactors only.

## [0.5.4] - 2026-07-26
### Fixed
- Bluetooth radio (`hci0`) was left soft rfkill-blocked on the device,
  silently preventing Bluetooth speaker pairing even though `bluetoothd`
  was running. `install.sh` now checks and unblocks it during setup.
