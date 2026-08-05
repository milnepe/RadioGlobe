import asyncio
import pytest

pytest.importorskip("evdev", reason="Requires python-evdev (pip install evdev)")

from radioglobe.dial import Dial

try:
    Dial._find_rotary_device()
except RuntimeError:
    pytest.skip("No rotary-encoder input device found — requires the dial overlay loaded", allow_module_level=True)


async def main():
    jog = Dial()
    jog.start()

    print("[INFO] Starting dial monitor...")
    try:
        while True:
            direction = await jog.queue.get()
            print(
                f"[DIRECTION] Detected turn: {'Clockwise' if direction == 1 else 'Counter-clockwise'}"
            )
    except KeyboardInterrupt:
        pass
    finally:
        await jog.stop()
        print("[INFO] Stopped.")


if __name__ == "__main__":
    asyncio.run(main())
