#!/usr/bin/env python3
"""
encoder-hardware-test.py

Test the Linux rotary-encoder kernel driver.

Designed for:
    Raspberry Pi 4
    Bourns PEC11R-4220K-S0024
    dtoverlay=rotary-encoder,pin_a=17,pin_b=18,relative_axis=1

The kernel performs all GPIO decoding. This program simply reads
EV_REL events from the input subsystem.
"""

from evdev import InputDevice, list_devices, ecodes


def find_rotary_encoder():
    """Locate the Linux rotary encoder input device."""

    for path in list_devices():
        dev = InputDevice(path)
        if dev.name.startswith("rotary@"):
            return dev

    raise RuntimeError("No rotary encoder input device found.")


def main():

    encoder = find_rotary_encoder()

    print(f"Using device : {encoder.path}")
    print(f"Device name  : {encoder.name}")
    print("Rotate the encoder (Ctrl+C to quit)\n")

    position = 0

    try:
        for event in encoder.read_loop():

            if event.type != ecodes.EV_REL:
                continue

            if event.code != ecodes.REL_X:
                continue

            delta = event.value

            #
            # Your encoder currently reports:
            #
            #   clockwise = -1
            #   counter-clockwise = +1
            #
            # Uncomment the next line if you prefer:
            #
            # delta = -delta
            #

            position += delta

            direction = "CW " if delta > 0 else "CCW"

            print(
                f"Direction: {direction}"
                f"   Delta: {delta:+d}"
                f"   Position: {position}"
            )

    except KeyboardInterrupt:
        print("\nFinished.")


if __name__ == "__main__":
    main()

