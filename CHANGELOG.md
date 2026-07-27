# Changelog

All notable changes to this project are documented in this file.

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
