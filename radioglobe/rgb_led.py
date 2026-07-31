import asyncio
import logging
import RPi.GPIO as GPIO  # type: ignore

from .constants import COLOUR_OFF

# GPIO pin assignments (BCM numbering)
_PIN_LED_R = 22
_PIN_LED_G = 23
_PIN_LED_B = 24


class RGBLed:
    COLOURS = {
        "red": (1, 0, 0),
        "green": (0, 1, 0),
        "blue": (0, 0, 1),
        "white": (1, 1, 1),
        "off": (0, 0, 0),
    }

    def __init__(self, red_pin=_PIN_LED_R, green_pin=_PIN_LED_G, blue_pin=_PIN_LED_B):
        # Required before the GPIO.setup() calls below. No other module sets
        # this globally (each hardware module owns its own setmode call) -
        # setmode is idempotent, so calling it here is safe even if another
        # hardware object in the same process already has.
        GPIO.setmode(GPIO.BCM)
        self.pins = {"red": red_pin, "green": green_pin, "blue": blue_pin}
        self._running = asyncio.Event()
        for pin in self.pins.values():
            GPIO.setup(pin, GPIO.OUT)
            GPIO.output(pin, GPIO.LOW)

    def set_color(self, color_name):
        color = self.COLOURS.get(color_name.lower(), (0, 0, 0))
        GPIO.output(self.pins["red"], GPIO.HIGH if color[0] else GPIO.LOW)
        GPIO.output(self.pins["green"], GPIO.HIGH if color[1] else GPIO.LOW)
        GPIO.output(self.pins["blue"], GPIO.HIGH if color[2] else GPIO.LOW)

    def off(self):
        self.set_color(COLOUR_OFF)

    def start(self):
        pass  # GPIO pins are configured at construction time

    async def stop(self):
        """Turn the LED off."""
        self.off()

    async def flash(self, color: str, duration: float):
        """Turn the LED on for duration seconds, then off.

        A no-op if a flash is already in progress, so overlapping calls
        don't cut a running flash short."""
        if self._running.is_set():
            logging.debug("LED flash already running, skipping.")
            return
        self._running.set()
        try:
            logging.debug(f"LED ON ({color}) for {duration}s")
            self.set_color(color)
            await asyncio.sleep(duration)
            self.off()
            logging.debug("LED OFF")
        finally:
            self._running.clear()
