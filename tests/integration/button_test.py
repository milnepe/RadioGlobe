"""
Hardware button test — run on the Pi to confirm short/long press detection.

Usage (from the radioglobe/ directory):
    python ../tests/integration/button_test.py top
    python ../tests/integration/button_test.py mid
    python ../tests/integration/button_test.py bottom

Press the named button; the terminal will print SHORT or LONG for each
press. Ctrl-C to exit.
"""

import asyncio
import argparse
import sys
import time
import logging
import pytest

GPIO = pytest.importorskip("RPi.GPIO", reason="Requires Raspberry Pi hardware")

from radioglobe.buttons import AsyncButtonManager
from radioglobe.radio_config import PIN_BTN_TOP, PIN_BTN_MID, PIN_BTN_BOTTOM

BUTTONS = {
    "top":    PIN_BTN_TOP,
    "mid":    PIN_BTN_MID,
    "bottom": PIN_BTN_BOTTOM,
}


def parse_args():
    parser = argparse.ArgumentParser(description="RadioGlobe button hardware test")
    parser.add_argument(
        "button",
        choices=list(BUTTONS.keys()),
        help="Which button to test",
    )
    parser.add_argument(
        "--long-threshold",
        type=float,
        default=1.0,
        metavar="SECONDS",
        help="Hold time (s) that counts as a long press (default: 1.0)",
    )
    return parser.parse_args()


async def main():
    args = parse_args()
    pin = BUTTONS[args.button]

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

    loop = asyncio.get_running_loop()

    button_definitions = [
        (args.button, pin, on_short, on_long, on_press),
    ]

    manager = AsyncButtonManager(
        button_definitions, loop, long_press_threshold=args.long_threshold
    )
    await manager.start()

    print(f"Testing '{args.button}' button on GPIO {pin}")
    print(f"Long-press threshold: {args.long_threshold}s")
    print("Press the button — Ctrl-C to quit\n")

    try:
        await manager.handle_events()
    except KeyboardInterrupt:
        pass
    finally:
        GPIO.cleanup()
        total = press_count["short"] + press_count["long"]
        print(f"\nDone. {total} press(es): {press_count['short']} short, {press_count['long']} long.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    asyncio.run(main())
