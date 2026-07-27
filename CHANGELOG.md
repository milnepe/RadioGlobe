# Changelog

All notable changes to this project are documented in this file.

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
