import asyncio
from dial_button_async import AsyncDialWithButton


async def main():
    dial = AsyncDialWithButton()
    dial.start()

    try:
        while True:
            await asyncio.sleep(0.1)
            direction = dial.get_direction()
            if direction:
                print("Direction:", direction)

            if dial.get_button():
                print("Button pressed!")
    except KeyboardInterrupt:
        print("Stopping...")
        await dial.stop()


if __name__ == "__main__":
    asyncio.run(main())
