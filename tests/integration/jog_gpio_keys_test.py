#!/usr/bin/env python3
"""
jog_gpio_keys_test.py

Experiment: read the Jog button (GPIO 27) via the Linux kernel's gpio-keys
driver instead of buttons.py's userspace RPi.GPIO edge-detection, mirroring
the kernel-driver approach already used for the dial's rotation
(see docs/KERNEL_ROTARY_ENCODER_INVESTIGATION.md).

Requires, in /boot/firmware/config.txt (exact param names/defaults not
yet confirmed on-device - check `dtoverlay -h gpio-key` first):

    dtoverlay=gpio-key,gpio=27,gpio_pull=up,label=jog,keycode=<code>

The gpio-key overlay claims GPIO 27 at boot, before Linux starts - the same
mechanism documented for dtoverlay=rotary-encoder in
docs/JOG_WHEEL_INVESTIGATION.md §4. This conflicts with buttons.py's
RPi.GPIO.setup(27, ...) for the Jog button, so:

    1. Stop the running service first: systemctl --user stop radioglobe.service
    2. Add the overlay line above and reboot.
    3. Run this script and press the Jog button a few times, short and long.
    4. When done, comment the overlay line out, reboot, and confirm
       radioglobe.service starts normally with the Jog button working via
       buttons.py again.

This program does not import anything from radioglobe - it's a standalone
diagnostic, not wired into the app.
"""

import time

from evdev import InputDevice, list_devices, ecodes

LONG_PRESS_THRESHOLD = 1.0  # matches buttons.py's AsyncButton default


def find_jog_button() -> InputDevice:
    """Locate the gpio-keys input device for the Jog button.

    Matches by the overlay's label= parameter first (expected name "jog");
    falls back to any EV_KEY-capable device with no other event types, same
    capability-matching spirit as dial.py's _find_rotary_device().
    """
    fallback = None
    for path in list_devices():
        dev = InputDevice(path)
        if dev.name == "jog":
            return dev
        caps = dev.capabilities()
        if ecodes.EV_KEY in caps and ecodes.EV_REL not in caps and fallback is None:
            fallback = dev

    if fallback is not None:
        print(f"No device named 'jog' found; falling back to {fallback.name!r} "
              f"by capability match - confirm this is really the Jog button.")
        return fallback

    raise RuntimeError(
        "No gpio-keys input device found - check "
        "'dtoverlay=gpio-key,gpio=27,...' in /boot/firmware/config.txt and reboot"
    )


def main():
    button = find_jog_button()

    print(f"Using device : {button.path}")
    print(f"Device name  : {button.name}")
    print(f"Long-press threshold: {LONG_PRESS_THRESHOLD}s")
    print("Press the Jog button (Ctrl+C to quit)\n")

    press_start = None

    try:
        for event in button.read_loop():
            if event.type != ecodes.EV_KEY:
                continue

            if event.value == 1:  # key down
                press_start = time.monotonic()
                print("... button down (waiting for release)")
            elif event.value == 0 and press_start is not None:  # key up
                held = time.monotonic() - press_start
                press_start = None
                kind = "LONG" if held >= LONG_PRESS_THRESHOLD else "SHORT"
                print(f"{kind} press  (held {held:.3f}s)")

    except KeyboardInterrupt:
        print("\nFinished.")


if __name__ == "__main__":
    main()
