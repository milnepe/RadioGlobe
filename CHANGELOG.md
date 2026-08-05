# Changelog

All notable changes to this project are documented in this file.

## [0.9.1] - 2026-08-05
### Changed
- `buttons.py`: `ButtonManager.start()` is now synchronous (previously
  `async def` despite never awaiting anything), and `Button.stop()` is now
  `async def` (previously synchronous) — both now match every other HAL
  component's start()/stop() shape. `hal/protocols.py`'s shared
  `HardwareComponent`/role protocols updated to match.
- `display.py`'s `stop()` now cancels its background task directly
  (`task.cancel()` + await), matching `positional_encoders.py`'s pattern,
  instead of a cooperative `running` flag plus an event-set wakeup.
- `display.py`'s defensive catch around each LCD write now logs via
  `logging.exception()` (captures the traceback) instead of
  `logging.error(f"...: {e}")`, matching `buttons.py`'s equivalent
  defensive catch around user callbacks.
- `positional_encoders.py` now logs SPI parity failures at debug level;
  this module previously had no logging at all.
- `App.run()`'s teardown loop (`main.py`) now stops hardware in reverse
  of its actual start order, with a comment explaining why
  `audio_player`/`led` are included despite never being started.
- Renamed `AsyncDial` → `Dial`, `AsyncButton` → `Button`,
  `AsyncButtonManager` → `ButtonManager` — the "Async" prefix didn't
  correlate with actual async usage, and `hal/fake.py`'s Fakes already
  used the unprefixed names.
- Filled in missing parameter/return type hints across the HAL layer
  (`dial.py`, `positional_encoders.py`, `buttons.py`, `rgb_led.py`,
  `display.py`, `audio_async.py`) and their Fakes in `hal/fake.py`.

### Removed
- `RGBLed.start()` and `AudioPlayer.start()` — dead code, never called;
  both classes are fully ready after construction.

This release is an internal consistency pass across the HAL (hardware
abstraction) layer, prompted by a ranked audit of async/sync mismatches,
dead code, and inconsistent logging/naming/typing across `dial.py`,
`positional_encoders.py`, `buttons.py`, `rgb_led.py`, `display.py`, and
`audio_async.py`. No user-facing behavior change; verified on-device
before tagging.

## [0.9.0] - 2026-08-04
### Added
- `tests/integration/rgb_led_gpio_led_test.py`: standalone, zero-`radioglobe`-
  dependency diagnostic for the RGB LED via the kernel `gpio-led` driver,
  kept alongside `dial.py`/`buttons.py`'s equivalent diagnostics.
- `install.sh` installs a udev rule
  (`/etc/udev/rules.d/99-radioglobe-leds.rules`) granting the `gpio` group
  write access to LED sysfs brightness files, so the service doesn't need
  root.

### Changed
- `rgb_led.py` now drives all 3 LED channels via the kernel's `leds-gpio`
  driver + sysfs (`/sys/class/leds/<label>/brightness`) instead of
  `RPi.GPIO.output()` — the same kernel-driver approach `dial.py` and
  `buttons.py` already use. No brightness/dimming behavior change
  (`max_brightness` is `1` on these LEDs either way).
- `install.sh` adds the 3 required `dtoverlay=gpio-led` lines idempotently
  (reboot required).

### Removed
- `lgpio`/`rpi-lgpio` from `pyproject.toml`'s `pi` extra, and the
  `swig`/`liblgpio-dev` apt packages from `install.sh` — `rgb_led.py` was
  the last module using `RPi.GPIO`; migrating it means `import RPi.GPIO`
  has zero remaining consumers anywhere in `src/`.

## [0.8.0] - 2026-08-04
### Added
- `tests/integration/jog_gpio_keys_test.py`: standalone, zero-`radioglobe`-
  dependency diagnostic for the Jog button via the kernel `gpio-keys`
  driver, kept alongside `dial.py`'s equivalent `encoder_hardware_test.py`.

### Changed
- `buttons.py` now reads all 4 buttons (Jog, Top, Mid, Bottom) via the
  kernel's `gpio-keys` driver + evdev instead of `RPi.GPIO`
  edge-detection — the same kernel-driver approach `dial.py` already
  uses for the dial's rotation. Device discovery matches on a distinct
  keycode (`BTN_0`..`BTN_3`) per button rather than device name, since
  on-device testing showed the overlay's `label=` param doesn't
  reliably set the evdev device name.
- Removes the busy-wait release-polling state machine, the 50ms
  `_poll_buttons()` task, and the `loop.call_soon_threadsafe()`
  GPIO-interrupt-thread bridging entirely — every hardware source in
  the app is now purely event-driven. Also drops the now-vestigial
  `loop` parameter from `AsyncButton`/`AsyncButtonManager`/
  `create_button_manager()`.
- `install.sh` adds the 4 required `dtoverlay=gpio-key` lines
  idempotently (reboot required, same as the existing dial overlay).
- `button_test.py` rewritten around the real `create_button_manager()`
  production path for all 4 buttons.

### Removed
- `tests/integration/button_reliability_test.py` — the stuck-polling
  failure mode it existed to catch is now structurally impossible
  under the kernel-driven design.

## [0.7.2] - 2026-08-04
### Changed
- `display.py`: renamed `DISPLAY_COLUMNS`/`DISPLAY_ROWS`/`DISPLAY_I2C_PORT`
  to `_DISPLAY_COLUMNS`/`_DISPLAY_ROWS`/`_DISPLAY_I2C_PORT`, matching
  `_I2C_LCD_ADDR`'s privacy in the same file (all have zero consumers
  outside `display.py`).

### Fixed
- `update()`'s coords line now gets the same `[:_DISPLAY_COLUMNS]`
  truncation guard `location`/`station` already had — previously latent
  (`Coordinate.__str__()` always produces <20 chars) but not actually
  guaranteed by the code.

### Removed
- Dead code in `display.py`: a commented-out logger-setup block, a
  redundant `if not volume: volume = 0` no-op, and a commented-out
  trailing debug log.

## [0.7.1] - 2026-08-04
### Fixed
- Moved `_VOLUME_STEP`/`_VOLUME_ON_LEVEL`/`_VOLUME_OFF_LEVEL`/
  `_LED_FLASH_SHORT` (had landed in `buttons.py` in 0.7.0) and
  `_LED_FLASH_DIAL` (had landed in `dial.py`) back to `radio_config.py`.
  These describe App/UX behavior, not hardware — swapping the physical
  button or dial for a different part wouldn't change any of these
  values, so putting them in the HAL modules made those modules depend
  on App concepts they have no business knowing about. Concretely,
  importing `_LED_FLASH_DIAL` from `dial.py` had forced `main.py` to
  transitively require `evdev`, not just `RPi.GPIO`, just to read a
  plain float — confirmed this is gone; `radioglobe.main`/`cli` now
  import with only `RPi.GPIO` stubbed.
- `ARCHITECTURE.md` §8 now states the ownership test explicitly: would
  this constant's value need to change if the physical part were
  swapped for a different one doing the same job? The `COLOUR_*` move
  into `rgb_led.py` (also from 0.7.0) stays, since it passes this test.

## [0.7.0] - 2026-08-04
### Added
- Hardware Abstraction Layer (`radioglobe.hal`): `protocols.py` defines a
  `typing.Protocol` per hardware role (dial, positional encoders, buttons,
  RGB LED, display, audio) matching the existing hardware classes' real
  signatures exactly, with no changes needed to those modules. `fake.py`
  provides hand-written fakes (`FakeDial`, `FakePositionalEncoders`,
  `FakeButtonManager`, `FakeRGBLed`, `FakeDisplay`, `FakeAudioPlayer`) with
  test hooks for driving `App` end-to-end off real hardware. `factory.py`'s
  `build_hardware()` constructs the real Pi-backed bundle.
- `App.__init__` now takes its 5 hardware objects as constructor parameters
  instead of building them itself; `cli.py` and `main.py`'s `__main__` block
  call `App(*build_hardware())`.
- New unit tests (`tests/hal/`, `tests/main_test.py`) exercising previously
  hardware-locked `App` logic — the dial/encoder event loops, LED-flash
  behavior, and stream-failure handling — with no real I/O.

### Changed
- Pi-specific packages (`evdev`, `lgpio`, `rpi-lgpio`, `smbus`, `spidev`,
  `liquidcrystal-i2c`, `python-vlc`) moved from `pyproject.toml`'s base
  `dependencies` into an optional `pi` extra, so the core package, the HAL,
  and the unit test suite install and import cleanly off a Pi.
  `install.sh`/`update.sh`/the deploy scripts now install `.[pi]` on-device.
- Fixed button wiring (`button_definitions`/`AsyncButtonManager`
  construction) moved from `main.py` into `buttons.create_button_manager()`,
  taking a `ButtonCallbacks` bundle per button; callback bodies stay on
  `App` since they orchestrate other hardware/app state.
- Relocated several constants to the hardware module that's their only
  consumer: `_VOLUME_STEP`/`_VOLUME_ON_LEVEL`/`_VOLUME_OFF_LEVEL`/
  `_LED_FLASH_SHORT` into `buttons.py`, `_LED_FLASH_DIAL` into `dial.py`,
  and LED colour constants (`COLOUR_RED`/`GREEN`/`BLUE`/`WHITE`/`OFF`) into
  `rgb_led.py` — the last of these also fixes a pre-existing duplication
  where `RGBLed.COLOURS` independently hardcoded the same 5 colour strings
  `constants.py` also defined.

### Fixed
- A pre-existing wheel-path duplication bug in `update.sh` (noticed while
  updating it for the `pi` extra).

## [0.6.3] - 2026-08-03
### Changed
- Simplified `AsyncDial` (`dial.py`): removed the software debounce/coalescing
  timer added in 0.5.x to filter kernel `REL_X` contact-bounce bursts.
  On-device testing with the new `tests/integration/encoder_hardware_test.py`
  script showed raw per-event direction reporting is reliable, so each event
  now pushes its direction onto the queue directly.
- Swapped the rotary-encoder overlay's `pin_a`/`pin_b` (now 18/17) in
  `install.sh` to correct the physical CW/CCW direction of the dial.

### Fixed
- Corrected `ARCHITECTURE.md`, `tests/integration/README.md`, and `install.sh`
  comments that mislabeled the two encoder pins as a clock/direction pair —
  they're the encoder's two quadrature switch outputs (A/B).

## [0.6.0] - 2026-08-02
### Added
- Repackaged project into a standard src/ layout and added a console
  entrypoint (`radioglobe = radioglobe.cli:main`) so RadioGlobe is
  installable via pip/wheel.
- Reproducible, commit-aware versioning using setuptools_scm with
  write_to = `src/radioglobe/_version.py` and `local_scheme = "node-and-date"`.
- Robust deployment automation:
  - `Makefile` targets: `make build`, `make deploy`, `make force-deploy`,
    and `make device-version` for developer workflows.
  - `scripts/deploy_remote.sh` and `scripts/force_deploy_remote.sh` handle
    single-wheel upload, remote install into `/opt/radioglobe/venv`,
    stations.json copy and safe force-reinstall.
- Installer improvements: `install.sh` / `update.sh` now prefer a built
  wheel in `dist/`, safely manage `/opt/radioglobe/stations`, and write
  `/opt/radioglobe/VERSION` and `version.env` for the systemd unit.
- Documentation updated: `README.md`, `CONTRIBUTING.md`, and
  `ARCHITECTURE.md` now describe the src/ layout and the new deploy
  workflow.

### Changed
- `radio_config.py` now resolves runtime data paths robustly (environment
  override, `/opt/radioglobe/stations`, or repo default) so the installed
  package can find `stations.json` when run as a systemd service.
- Deployment scripts now remove old `/tmp/radioglobe-*.whl` on the device
  before uploading a single wheel to avoid pip dependency-resolution
  conflicts.
- Makefile `build` now writes the resolved setuptools_scm version into
  `VERSION` and builds a wheel to `dist/`.
- `update.sh` no longer performs interactive `sudo` provisioning; it
  reinstalls into the existing venv and restarts the service (safe for
  routine code updates).

### Fixed
- Various Makefile quoting and recipe-scoping issues that caused deploys
  to fail in certain shells; complex remote logic moved to dedicated
  scripts for robustness.
- `.gitignore` updated to ignore generated `src/radioglobe/_version.py`.

(See Git history and the updated docs for a more detailed breakdown.)

## [0.5.17] - 2026-08-01
### Fixed
- `update.sh` re-ran install-time system setup (chown, service-file
  reinstall, `enable-linger`, `daemon-reload`/`enable`) via `sudo` on
  every small update, which needs an interactive password prompt and
  can't be satisfied non-interactively over SSH — every routine update
  required running it by hand from a real terminal. Split
  responsibilities instead: `install.sh` remains the one-time,
  `sudo`-requiring system setup; since it already hands `/opt/radioglobe`
  ownership to the `radioglobe` user, `update.sh` now just copies the
  app/stations/VERSION and restarts the already-installed service — no
  `sudo` needed anywhere. It also now restarts the service itself
  instead of telling the operator to do it by hand.
- The above change had a side effect: the service unit baked its version
  banner in as a literal `Environment=RADIOGLOBE_VERSION=__VERSION__`,
  substituted once by `install.sh`. Since `update.sh` no longer touches
  the (sudo-only) unit file, that banner went stale after the first
  install and never updated again on routine updates, even though
  `/opt/radioglobe/VERSION` and the running code were correct. Fixed by
  switching the unit to `EnvironmentFile=__RADIOGLOBE_DIR__/version.env`
  — a plain file inside `/opt/radioglobe`, owned by the `radioglobe`
  user, that both `install.sh` and `update.sh` can freely rewrite.
  systemd re-reads an `EnvironmentFile` fresh on every service start, so
  a plain restart (no `daemon-reload`) is enough to pick up the new
  version.
- `make install`'s `ssh $(REMOTE) "..."` never allocated a pseudo-terminal
  on the remote side, so `sudo` inside `install.sh` had no controlling
  terminal to prompt through — `make install` failed with "a terminal is
  required to read the password" even when run from a genuinely
  interactive local terminal. Added `-t` to force pty allocation.

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
