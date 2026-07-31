"""
Hardware button reliability test - run on the Pi to check whether any
presses are silently dropped or get the button stuck at the AsyncButton
layer (see the "stuck _pressed flag" note in buttons.py).

Runs two independent counters on the same pin concurrently:
  - a raw poll of GPIO.input(), sampled every --poll-interval seconds,
    counting LOW-to-HIGH (release) transitions directly - a ground
    truth that holds no state across presses, so it can't get stuck
    the way AsyncButton._check_hold() can
  - AsyncButtonManager's own short+long press count, exactly as the
    real app would see it

If the two counts ever diverge, a press reached the GPIO pin but was
never registered by AsyncButton. Polling every 10ms can't distinguish
sub-10ms glitches from a real press, so treat this as a real-world
reliability check rather than a cycle-accurate one - for a human
pressing a physical button it's more than fast enough.

This only tests the "stuck on one button" failure mode. The other
failure mode discussed alongside this fix - an exception in one
button's handler silently killing dispatch for every button - doesn't
need real hardware to verify and is covered by tests/buttons_test.py
instead.

Usage (from the radioglobe/ directory):
    python ../tests/integration/button_reliability_test.py mid
    python ../tests/integration/button_reliability_test.py mid --presses 30

Press the named button repeatedly (short or long, doesn't matter) until
the target count is reached, or Ctrl-C to stop early and see a summary
of what's been seen so far.
"""

import asyncio
import argparse
import time
import logging
import pytest

GPIO = pytest.importorskip("RPi.GPIO", reason="Requires Raspberry Pi hardware")

from radioglobe.buttons import (
    AsyncButtonManager, ButtonDefinition,
    TOP_BUTTON, MID_BUTTON, BOTTOM_BUTTON,
)

BUTTONS = {
    "top":    TOP_BUTTON.pin,
    "mid":    MID_BUTTON.pin,
    "bottom": BOTTOM_BUTTON.pin,
}


def parse_args():
    parser = argparse.ArgumentParser(description="RadioGlobe button reliability test")
    parser.add_argument("button", choices=list(BUTTONS.keys()), help="Which button to test")
    parser.add_argument(
        "--presses", type=int, default=20, metavar="N",
        help="Stop once this many raw presses are seen (default: 20)",
    )
    parser.add_argument(
        "--poll-interval", type=float, default=0.01, metavar="SECONDS",
        help="Raw GPIO poll interval in seconds (default: 0.01)",
    )
    return parser.parse_args()


async def raw_press_counter(pin, interval, count_state):
    """Ground-truth press counter, independent of AsyncButton's own state."""
    was_low = False
    while True:
        level = GPIO.input(pin)
        if level == GPIO.LOW and not was_low:
            was_low = True
        elif level == GPIO.HIGH and was_low:
            was_low = False
            count_state["raw"] += 1
            ts = time.strftime("%H:%M:%S")
            print(
                f"[{ts}] raw press #{count_state['raw']} "
                f"(AsyncButton has registered {count_state['async']})"
            )
        await asyncio.sleep(interval)


async def main():
    args = parse_args()
    pin = BUTTONS[args.button]
    count_state = {"raw": 0, "async": 0}

    async def on_short():
        count_state["async"] += 1

    async def on_long():
        count_state["async"] += 1

    loop = asyncio.get_running_loop()
    button_definitions = [ButtonDefinition(args.button, pin, on_short, on_long, None)]
    manager = AsyncButtonManager(button_definitions, loop)
    await manager.start()

    print(f"Testing '{args.button}' button on GPIO {pin} for reliability")
    print(f"Press it (short or long, doesn't matter) {args.presses} times.")
    print("Ctrl-C to stop early and see a summary.\n")

    events_task = asyncio.create_task(manager.handle_events())
    raw_task = asyncio.create_task(raw_press_counter(pin, args.poll_interval, count_state))

    try:
        while count_state["raw"] < args.presses:
            await asyncio.sleep(0.1)
        # AsyncButton's own pipeline lags the raw poll by up to ~100ms (its
        # own 50ms release-poll, then _poll_buttons()'s separate 50ms
        # cycle) - give it a moment to catch up on the last press before
        # comparing counts, so a real lag doesn't get reported as a false
        # "missed press" that's really just this script's own timing.
        settle_deadline = time.monotonic() + 1.0
        while count_state["async"] < count_state["raw"] and time.monotonic() < settle_deadline:
            await asyncio.sleep(0.05)
    except KeyboardInterrupt:
        pass
    finally:
        events_task.cancel()
        raw_task.cancel()
        await manager.stop()

    raw, seen = count_state["raw"], count_state["async"]
    missed = raw - seen
    print(f"\nDone. Raw presses detected: {raw}. AsyncButton registered: {seen}.")
    if missed > 0:
        print(
            f"FAIL: {missed} press(es) reached the GPIO pin but were never registered "
            f"by AsyncButton - likely a stuck _pressed flag (see buttons.py)."
        )
    elif missed < 0:
        print(
            "Unexpected: AsyncButton registered more presses than were seen at the raw "
            "GPIO level - investigate, this shouldn't be possible."
        )
    else:
        print("PASS: every press that reached the pin was registered.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    asyncio.run(main())
