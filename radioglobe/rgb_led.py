import asyncio
import logging
import RPi.GPIO as GPIO  # type: ignore

from .radio_config import PIN_LED_R, PIN_LED_G, PIN_LED_B


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

    def start(self):
        pass  # GPIO pins are configured at construction time

    async def stop(self):
        """Turn the LED off."""
        self.off()

    def cleanup(self):
        """Turn the LED off and release GPIO resources (for standalone use)."""
        self.off()
        GPIO.cleanup()


async def led_task(led: RGBLed, led_running: asyncio.Event, color: str, duration: float):
    if led_running.is_set():
        logging.debug("LED task already running, skipping.")
        return
    led_running.set()
    try:
        logging.debug(f"LED ON ({color}) for {duration}s")
        led.set_color(color)
        await asyncio.sleep(duration)
        led.off()
        logging.debug("LED OFF")
    finally:
        led_running.clear()
