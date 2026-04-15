import asyncio
import pytest

pytest.importorskip("RPi.GPIO", reason="Requires Raspberry Pi hardware")

from radioglobe.dial import AsyncDial


async def main():
    jog = AsyncDial()
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
