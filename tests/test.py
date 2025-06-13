import asyncio
import rgb_led_async
import time


# background coroutine task
async def scheduler():
    while True:
        start_t = time.monotonic()
        await asyncio.sleep(0.5)
        print(f"Scheduler task ran for {time.monotonic() - start_t:.1f}")


async def led_init():
    print("Testing LEDs...")
    led = rgb_led_async.RGB_LED()
    led.set_static("RED")
    await asyncio.sleep(1)
    led.set_static("GREEN")
    await asyncio.sleep(1)
    led.set_static("BLUE")
    await asyncio.sleep(1)
    led.set_static("OFF")
    return led


def blink_led(led, colour, duration):
    print("Led ON")
    led.set_static(colour)
    time.sleep(duration)
    led.set_static("OFF")
    print("Led OFF")


async def first_thing(led):
    print("Starting the first thing...")
    await asyncio.sleep(2)
    print("Finished first thing...")


async def second_thing():
    print("Starting second thing...")
    await asyncio.sleep(2)
    print("Finished second thing...")

async def blinker(led, colour, duration):
        blink = asyncio.to_thread(blink_led, led, "RED", 0.5)
        await blink
        
async def main():
    # Create led instance
    led = await led_init()

    # Startup scheduler task - runs without blocking
    asyncio.create_task(scheduler())

    # Start main loop
    while True:
        first_task = asyncio.create_task(first_thing(led))
        # await blinker(led, "RED", 0.5)
        blink = asyncio.to_thread(blink_led, led, "RED", 0.2)
        await blink
        await first_task

        second_task = asyncio.create_task(second_thing())
        blink = asyncio.to_thread(blink_led, led, "BLUE", 0.2)
        await blink
        await second_task


if __name__ == "__main__":
    asyncio.run(main())
