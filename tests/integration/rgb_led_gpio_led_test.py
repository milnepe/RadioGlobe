#!/usr/bin/env python3
"""
rgb_led_gpio_led_test.py

Experiment: drive the RGB status LED (R=22, G=23, B=24) via the kernel's
leds-gpio driver (dtoverlay=gpio-led) instead of rgb_led.py's RPi.GPIO
output calls, mirroring the kernel-driver approach already adopted for
the dial (rotary_encoder) and all 4 buttons (gpio-keys).

Requires, in /boot/firmware/config.txt:

    dtoverlay=gpio-led,gpio=22,label=led-red
    dtoverlay=gpio-led,gpio=23,label=led-green
    dtoverlay=gpio-led,gpio=24,label=led-blue

KNOWN GAP: /sys/class/leds/*/brightness is root:root mode 644 on stock
Raspberry Pi OS - no udev rule grants the radioglobe user write access
(confirmed on-device: writing to the existing ACT LED as radioglobe was
denied, unlike /dev/input/* which works via the `input` group). Run this
script with sudo for now:

    sudo python3 rgb_led_gpio_led_test.py

Production adoption would need a udev rule (e.g. SUBSYSTEM=="leds",
RUN+="/bin/chmod g+w /sys%p/brightness") so the running service doesn't
need root - not set up yet, this is purely an experiment.

This program does not import anything from radioglobe - it's a standalone
diagnostic, not wired into the app.
"""

import time
from pathlib import Path

LEDS = {
    "red": Path("/sys/class/leds/led-red/brightness"),
    "green": Path("/sys/class/leds/led-green/brightness"),
    "blue": Path("/sys/class/leds/led-blue/brightness"),
}

# Mirrors radioglobe.rgb_led.RGBLed.COLOURS, plus a couple of extra
# combinations to prove independent per-channel control works.
COLOURS = {
    "red": (1, 0, 0),
    "green": (0, 1, 0),
    "blue": (0, 0, 1),
    "yellow": (1, 1, 0),
    "cyan": (0, 1, 1),
    "magenta": (1, 0, 1),
    "white": (1, 1, 1),
    "off": (0, 0, 0),
}


def set_color(name: str) -> None:
    r, g, b = COLOURS[name]
    for channel, value in zip(("red", "green", "blue"), (r, g, b)):
        LEDS[channel].write_text(str(value))


def main():
    for path in LEDS.values():
        if not path.exists():
            raise RuntimeError(
                f"{path} not found - check 'dtoverlay=gpio-led,...' lines in "
                "/boot/firmware/config.txt and reboot"
            )

    print("Cycling colours (Ctrl+C to stop)...")
    try:
        while True:
            for name in COLOURS:
                print(f"  {name}")
                set_color(name)
                time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        set_color("off")
        print("\nFinished.")


if __name__ == "__main__":
    main()
