"""
Hardware button test — run on the Pi to confirm short/long press detection
via the real production path (buttons.create_button_manager()), reading the
button through the kernel gpio-keys driver instead of RPi.GPIO.

Usage (from the radioglobe/ directory):
    python ../tests/integration/button_test.py jog
    python ../tests/integration/button_test.py top
    python ../tests/integration/button_test.py mid
    python ../tests/integration/button_test.py bottom

Press the named button; the terminal will print SHORT or LONG for each
press. Ctrl-C to exit.
"""

import asyncio
import argparse
import time
import logging
import pytest

pytest.importorskip("evdev", reason="Requires the gpio-keys kernel driver + evdev")

from radioglobe.buttons import ButtonCallbacks, create_button_manager  # noqa: E402

BUTTONS = ["jog", "top", "mid", "bottom"]


def parse_args():
    parser = argparse.ArgumentParser(description="RadioGlobe button hardware test")
    parser.add_argument("button", choices=BUTTONS, help="Which button to test")
    return parser.parse_args()


async def main():
    args = parse_args()

    press_count = {"short": 0, "long": 0}

    async def on_short():
        press_count["short"] += 1
        ts = time.strftime("%H:%M:%S")
        print(f"[{ts}] SHORT press  (total short={press_count['short']})")

    async def on_long():
        press_count["long"] += 1
        ts = time.strftime("%H:%M:%S")
        print(f"[{ts}] LONG  press  (total long={press_count['long']})")

    async def on_press():
        ts = time.strftime("%H:%M:%S")
        print(f"[{ts}] ... button down (waiting for release)")

    callbacks = ButtonCallbacks(short_cb=on_short, long_cb=on_long, press_cb=on_press)
    manager = create_button_manager(**{args.button: callbacks})
    manager.start()

    print(f"Testing '{args.button}' button via the kernel gpio-keys driver")
    print("Press the button — Ctrl-C to quit\n")

    try:
        await manager.handle_events()
    except KeyboardInterrupt:
        pass
    finally:
        await manager.stop()
        total = press_count["short"] + press_count["long"]
        print(f"\nDone. {total} press(es): {press_count['short']} short, {press_count['long']} long.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    asyncio.run(main())
