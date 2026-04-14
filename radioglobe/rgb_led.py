import asyncio
import random
import logging
import RPi.GPIO as GPIO  # type: ignore

from radio_config import PIN_LED_R, PIN_LED_G, PIN_LED_B


class RGBLed:
    COLOURS = {
        "red": (1, 0, 0),
        "green": (0, 1, 0),
        "blue": (0, 0, 1),
        "white": (1, 1, 1),
        "off": (0, 0, 0),
    }

    def __init__(self, red_pin=PIN_LED_R, green_pin=PIN_LED_G, blue_pin=PIN_LED_B):
        self.pins = {"red": red_pin, "green": green_pin, "blue": blue_pin}
        GPIO.setmode(GPIO.BCM)
        for pin in self.pins.values():
            GPIO.setup(pin, GPIO.OUT)
            GPIO.output(pin, GPIO.LOW)

    def set_color(self, color_name):
        color = self.COLOURS.get(color_name.lower(), (0, 0, 0))
        GPIO.output(self.pins["red"], GPIO.HIGH if color[0] else GPIO.LOW)
        GPIO.output(self.pins["green"], GPIO.HIGH if color[1] else GPIO.LOW)
        GPIO.output(self.pins["blue"], GPIO.HIGH if color[2] else GPIO.LOW)

    def off(self):
        self.set_color("off")

    def cleanup(self):
        self.off()
        GPIO.cleanup()


async def led_task(led: RGBLed, led_running: asyncio.Event, color: str, duration: float):
    if led_running.is_set():
        logging.debug("LED task already running, skipping.")
        return
    led_running.set()
    logging.debug(f"LED ON ({color}) for {duration}s")
    led.set_color(color)
    await asyncio.sleep(duration)
    led.off()
    logging.debug("LED OFF")
    led_running.clear()


async def worker(led: RGBLed, led_running: asyncio.Event):
    colors = ["red", "green", "blue", "white"]
    while True:
        sleep_time = random.uniform(1, 2)
        await asyncio.sleep(sleep_time)
        color = random.choice(colors)
        logging.debug(f"Worker woke up — triggering LED: {color}")
        if not led_running.is_set():
            asyncio.create_task(led_task(led, led_running, color, 0.5))


async def main():
    led = RGBLed()
    led_running = asyncio.Event()
    worker_task = asyncio.create_task(worker(led, led_running))

    try:
        await asyncio.sleep(15)  # Run for 15 seconds
    finally:
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            logging.debug("Worker stopped.")
        led.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
