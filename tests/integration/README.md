# Integration Tests

Hardware integration tests for RadioGlobe. Each test targets a specific subsystem and must be run directly as a script on the Raspberry Pi. They are excluded from the normal `pytest` run (`norecursedirs = ["integration"]` in `pyproject.toml`) and will skip automatically if the required hardware libraries are not present.

See [../../CONTRIBUTING.md](../../CONTRIBUTING.md) for how to submit changes.

## Tests

| Script | Hardware required | Purpose |
|--------|-------------------|---------|
| `led_test.py` | GPIO | Cycles RED → GREEN → BLUE then blinks concurrently with async tasks to verify LED wiring and `RGBLed.flash()` behaviour |
| `button_test.py` | GPIO (kernel `gpio-keys` overlay + evdev) | Confirms short and long press detection for a single named button (jog/top/mid/bottom), via the real `create_button_manager()` production path |
| `dial_test.py` | GPIO (kernel `rotary-encoder` overlay + evdev) | Prints Clockwise / Counter-clockwise on each encoder pulse to verify dial wiring and direction |
| `positional_encoders_test.py` | SPI | Reads the two SPI positional encoders and prints coordinates continuously |
| `main_test.py` | GPIO + SPI | Encoder index diagnostic: shows current index, search area, and matched cities on latch. LED blinks red on latch. No audio. |
| `streaming_cvlc_test.py` | GPIO + SPI + cvlc | Full stack test: encoders → city lookup → cvlc audio stream |
| `async_streamer_test.py` | Network | Resolves and plays a list of internet radio URLs using the async aiohttp streamer (no Pi hardware needed) |
| `rgb_led_gpio_led_test.py` | GPIO (kernel `gpio-led` overlay) | Low-level diagnostic: cycles the RGB LED through named colours by writing `/sys/class/leds/*/brightness` directly, with no `radioglobe` dependency — same role `encoder_hardware_test.py`/`jog_gpio_keys_test.py` play for the dial/buttons |

## Examples

```bash
# LED — cycles colours then blinks
python tests/integration/led_test.py

# Buttons — test one button at a time; prints SHORT / LONG for each press
python tests/integration/button_test.py jog
python tests/integration/button_test.py top
python tests/integration/button_test.py mid
python tests/integration/button_test.py bottom

# Dial — prints direction on each pulse
python tests/integration/dial_test.py

# Positional encoders — prints coordinates every 2 s
python tests/integration/positional_encoders_test.py

# Main encoder diagnostic — shows index / search area / cities on latch
python tests/integration/main_test.py
python tests/integration/main_test.py --stickiness 3 --fuzziness 7 --polling-sec 0.5

# Streaming (cvlc)
python tests/integration/streaming_cvlc_test.py

# Async streamer (network only)
python tests/integration/async_streamer_test.py

# RGB LED via kernel leds-gpio driver (no sudo needed once install.sh's
# udev rule is installed - see setup section below)
python tests/integration/rgb_led_gpio_led_test.py
```

## Hardware setup

### Prerequisites

Run `install.sh` from the project root to set up the venv and install all dependencies:

```bash
sudo bash install.sh
```

Then activate the venv before running any test:

```bash
source /opt/radioglobe/venv/bin/activate
```

Or from a development clone with the package installed in the local venv:

```bash
source venv/bin/activate
pip install -e .
```

### GPIO pin assignments (BCM numbering)

| Signal | Pin | Keycode |
|--------|-----|---------|
| Dial switch A (`pin_a`) | 18 | — |
| Dial switch B (`pin_b`) | 17 | — |
| Jog button | 27 | `BTN_0` (256) |
| Top button | 5 | `BTN_1` (257) |
| Mid button | 6 | `BTN_2` (258) |
| Bottom button | 12 | `BTN_3` (259) |
| LED red | 22 | — (`leds-gpio` label `led-red`) |
| LED green | 23 | — (`leds-gpio` label `led-green`) |
| LED blue | 24 | — (`leds-gpio` label `led-blue`) |

### SPI

The positional encoders use SPI bus 0, devices 0 (latitude) and 1 (longitude). Ensure SPI is enabled:

```bash
sudo raspi-config   # Interface Options → SPI → Enable
```

### Dial (kernel rotary-encoder overlay)

The dial is read via the kernel's `rotary_encoder` driver, not directly via `RPi.GPIO`.
`pin_a`/`pin_b` are the encoder's two quadrature switch outputs (A/B) — not a
clock/direction pair. `install.sh` adds the required
`dtoverlay=rotary-encoder,pin_a=18,pin_b=17,relative_axis=1` line to
`/boot/firmware/config.txt` idempotently — a reboot is required for it to take effect
(covered by the same reboot prompt `install.sh` already prints). No `raspi-config` step
is needed for this; `rotary-encoder` isn't one of its interface toggles.

### Buttons (kernel `gpio-keys` overlay)

All 4 buttons (Jog, Top, Mid, Bottom) are read via the kernel's `gpio-keys`
driver, not directly via `RPi.GPIO` — the same kernel-driver approach
already used for the dial's rotation. `install.sh` adds the required
`dtoverlay=gpio-key,gpio=<pin>,gpio_pull=up,label=<name>,keycode=<code>`
line for each button idempotently — a reboot is required for them to take
effect (covered by the same reboot prompt `install.sh` already prints). No
`raspi-config` step is needed; `gpio-key` isn't one of its interface
toggles.

Each button's `keycode=` must match `buttons.py`'s `_KEYCODE_BTN_*`
constants (see the pin table above) — device discovery matches on the
keycode a device reports, **not** on its `label=` param, since the overlay
was found on-device to not reliably set the evdev device name (every
instance shows up as `button@<hex-gpio>` regardless of `label`).

### RGB LED (kernel `gpio-led` overlay)

The RGB status LED (R=22, G=23, B=24) is driven through the kernel's
`leds-gpio` driver, not directly via `RPi.GPIO` — the same kernel-driver
approach already used for the dial and all 4 buttons. `install.sh` adds
the required `dtoverlay=gpio-led,gpio=<pin>,label=<name>` line for each
channel idempotently — a reboot is required for them to take effect
(covered by the same reboot prompt `install.sh` already prints).

Unlike `gpio-key`'s `label=` param (which doesn't reliably set the evdev
device name, see above), `leds-gpio`'s `label=` reliably becomes the sysfs
class device name directly — each LED shows up at
`/sys/class/leds/<label>/brightness`, written with a plain `0`/`1`. Labels
must match `rgb_led.py`'s `_LED_LABEL_RED`/`_GREEN`/`_BLUE` constants (see
the pin table above).

**Permissions:** `/sys/class/leds/*/brightness` is `root:root` mode `644`
by default — unlike `/dev/input/*` (readable via the `input` group), no
kernel/overlay mechanism grants non-root write access on its own.
`install.sh` also installs a udev rule
(`/etc/udev/rules.d/99-radioglobe-leds.rules`) granting the `gpio` group
(which `radioglobe` is already a member of) write access, so neither the
running service nor `rgb_led_gpio_led_test.py` need `sudo`.

### Calibration note

`main_test.py` and `positional_encoders_test.py` call `zero()` to set the encoder origin. **Start with the reticule pointing at the equator / prime meridian (0°N, 0°E) before running.** The origin index should read `(512, 512)`.
