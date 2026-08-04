# Integration Tests

Hardware integration tests for RadioGlobe. Each test targets a specific subsystem and must be run directly as a script on the Raspberry Pi. They are excluded from the normal `pytest` run (`norecursedirs = ["integration"]` in `pyproject.toml`) and will skip automatically if the required hardware libraries are not present.

See [../../CONTRIBUTING.md](../../CONTRIBUTING.md) for how to submit changes.

## Tests

| Script | Hardware required | Purpose |
|--------|-------------------|---------|
| `led_test.py` | GPIO | Cycles RED → GREEN → BLUE then blinks concurrently with async tasks to verify LED wiring and `RGBLed.flash()` behaviour |
| `button_test.py` | GPIO | Confirms short and long press detection for a single named button |
| `button_reliability_test.py` | GPIO | Compares a raw GPIO poll against AsyncButton's registered presses to catch dropped/stuck presses |
| `dial_test.py` | GPIO (kernel `rotary-encoder` overlay + evdev) | Prints Clockwise / Counter-clockwise on each encoder pulse to verify dial wiring and direction |
| `positional_encoders_test.py` | SPI | Reads the two SPI positional encoders and prints coordinates continuously |
| `main_test.py` | GPIO + SPI | Encoder index diagnostic: shows current index, search area, and matched cities on latch. LED blinks red on latch. No audio. |
| `streaming_cvlc_test.py` | GPIO + SPI + cvlc | Full stack test: encoders → city lookup → cvlc audio stream |
| `async_streamer_test.py` | Network | Resolves and plays a list of internet radio URLs using the async aiohttp streamer (no Pi hardware needed) |
| `jog_gpio_keys_test.py` | GPIO (experimental `gpio-key` overlay + evdev) | **Experimental.** Reads the Jog button via the kernel's `gpio-keys` driver instead of `buttons.py`'s `RPi.GPIO`, printing SHORT/LONG on each press. Not wired into the app — see "Experimental: Jog button via gpio-keys overlay" below before running |

## Examples

```bash
# LED — cycles colours then blinks
python tests/integration/led_test.py

# Buttons — test one button at a time; prints SHORT / LONG for each press
python tests/integration/button_test.py top
python tests/integration/button_test.py mid
python tests/integration/button_test.py bottom
python tests/integration/button_test.py top --long-threshold 0.5

# Button reliability — checks for dropped/stuck presses against a raw GPIO poll
python tests/integration/button_reliability_test.py mid
python tests/integration/button_reliability_test.py mid --presses 30

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

# Experimental: Jog button via kernel gpio-keys driver (see setup section below
# before running - conflicts with the running service on GPIO 27)
python tests/integration/jog_gpio_keys_test.py
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

| Signal | Pin |
|--------|-----|
| Dial switch A (`pin_a`) | 18 |
| Dial switch B (`pin_b`) | 17 |
| Jog button | 27 |
| Top button | 5 |
| Mid button | 6 |
| Bottom button | 12 |
| LED red | 22 |
| LED green | 23 |
| LED blue | 24 |

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

### Experimental: Jog button via `gpio-keys` overlay

`jog_gpio_keys_test.py` tries reading the Jog button (GPIO 27) through the
kernel's `gpio-keys` driver instead of `buttons.py`'s `RPi.GPIO`
edge-detection, mirroring the kernel-driver approach already adopted for
the dial's rotation. **This is exploratory** — not wired into `buttons.py`
or the running service.

Requires adding, in `/boot/firmware/config.txt` (confirm exact parameter
names/defaults on-device first with `dtoverlay -h gpio-key` — don't assume
these without checking, same as every other overlay in this project):

```
dtoverlay=gpio-key,gpio=27,gpio_pull=up,label=jog,keycode=<code>
```

The overlay claims GPIO 27 at boot, before Linux starts — the same
mechanism documented for `dtoverlay=rotary-encoder` above and in
`docs/JOG_WHEEL_INVESTIGATION.md` §4. This **conflicts** with
`buttons.py`'s `RPi.GPIO.setup(27, ...)` for the Jog button, so:

1. `systemctl --user stop radioglobe.service` first.
2. Add the overlay line and reboot.
3. Run `jog_gpio_keys_test.py` and press the Jog button — short and long —
   to check the reported classification and timing feel reliable.
4. When done, comment the overlay line back out, reboot, and confirm
   `radioglobe.service` starts normally with the Jog button working via
   `buttons.py` again before deciding whether this is worth adopting for
   real.

### Calibration note

`main_test.py` and `positional_encoders_test.py` call `zero()` to set the encoder origin. **Start with the reticule pointing at the equator / prime meridian (0°N, 0°E) before running.** The origin index should read `(512, 512)`.
