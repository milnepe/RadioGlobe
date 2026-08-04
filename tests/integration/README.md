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
| `rgb_led_gpio_led_test.py` | GPIO (experimental `gpio-led` overlay) | **Experimental.** Cycles the RGB LED through named colours by writing `/sys/class/leds/*/brightness` via the kernel's `leds-gpio` driver instead of `rgb_led.py`'s `RPi.GPIO`. Not wired into the app — see "Experimental: RGB LED via gpio-led overlay" below before running |

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

# Experimental: RGB LED via kernel leds-gpio driver (see setup section below
# before running - needs sudo, no udev rule grants write access yet)
sudo python tests/integration/rgb_led_gpio_led_test.py
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
| LED red | 22 | — (experimental `leds-gpio` label `led-red`) |
| LED green | 23 | — (experimental `leds-gpio` label `led-green`) |
| LED blue | 24 | — (experimental `leds-gpio` label `led-blue`) |

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

### Experimental: RGB LED via `gpio-led` overlay

`rgb_led_gpio_led_test.py` tries driving the RGB status LED (R=22, G=23,
B=24) through the kernel's `leds-gpio` driver instead of `rgb_led.py`'s
`RPi.GPIO` output calls, mirroring the kernel-driver approach already
adopted for the dial and all 4 buttons. **This is exploratory** — not
wired into `rgb_led.py` or the running service.

Requires adding, in `/boot/firmware/config.txt` (confirmed on-device via
`dtoverlay -h gpio-led`):

```
dtoverlay=gpio-led,gpio=22,label=led-red
dtoverlay=gpio-led,gpio=23,label=led-green
dtoverlay=gpio-led,gpio=24,label=led-blue
```

Unlike `gpio-key`'s `label=` param (which doesn't reliably set the evdev
device name, see above), `leds-gpio`'s `label=` reliably becomes the sysfs
class device name directly — each LED shows up at
`/sys/class/leds/<label>/brightness`, written with a plain `0`/`1`.

**Known gap:** `/sys/class/leds/*/brightness` is `root:root` mode `644` on
stock Raspberry Pi OS — confirmed on-device (tried writing to the existing
`ACT` LED as the `radioglobe` user: `Permission denied`). Unlike
`/dev/input/*` (readable via the `input` group), no udev rule grants
non-root write access to LED class devices here. Run the test script with
`sudo` for now. Adopting this for real would need a udev rule (e.g.
`SUBSYSTEM=="leds", RUN+="/bin/chmod g+w /sys%p/brightness"`) so the
running service doesn't need root — not set up, since this is still just
an experiment.

### Calibration note

`main_test.py` and `positional_encoders_test.py` call `zero()` to set the encoder origin. **Start with the reticule pointing at the equator / prime meridian (0°N, 0°E) before running.** The origin index should read `(512, 512)`.
