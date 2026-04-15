# Integration Tests

Hardware integration tests for RadioGlobe. Each test targets a specific subsystem and must be run directly as a script on the Raspberry Pi. They are excluded from the normal `pytest` run (`norecursedirs = ["integration"]` in `pyproject.toml`) and will skip automatically if the required hardware libraries are not present.

## Tests

| Script | Hardware required | Purpose |
|--------|-------------------|---------|
| `led_test.py` | GPIO | Cycles RED → GREEN → BLUE then blinks concurrently with async tasks to verify LED wiring and `led_task` behaviour |
| `button_test.py` | GPIO | Confirms short and long press detection for a single named button |
| `dial_test.py` | GPIO | Prints Clockwise / Counter-clockwise on each encoder pulse to verify dial wiring and direction |
| `positional_encoders_test.py` | SPI | Reads the two SPI positional encoders and prints coordinates continuously |
| `main_test.py` | GPIO + SPI | Encoder index diagnostic: shows current index, search area, and matched cities on latch. LED blinks red on latch. No audio. |
| `streaming_cvlc_test.py` | GPIO + SPI + cvlc | Full stack test: encoders → city lookup → cvlc audio stream |
| `async_streamer_test.py` | Network | Resolves and plays a list of internet radio URLs using the async aiohttp streamer (no Pi hardware needed) |

## Examples

```bash
# LED — cycles colours then blinks
python tests/integration/led_test.py

# Buttons — test one button at a time; prints SHORT / LONG for each press
python tests/integration/button_test.py top
python tests/integration/button_test.py mid
python tests/integration/button_test.py bottom
python tests/integration/button_test.py top --long-threshold 0.5

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
| Dial clock | 17 |
| Dial direction | 18 |
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

### Calibration note

`main_test.py` and `positional_encoders_test.py` call `zero()` to set the encoder origin. **Start with the reticule pointing at the equator / prime meridian (0°N, 0°E) before running.** The origin index should read `(512, 512)`.
