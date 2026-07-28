# Changelog

All notable changes to this project are documented in this file.

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
