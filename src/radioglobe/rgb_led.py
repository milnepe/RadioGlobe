import asyncio
import logging
from pathlib import Path

_LED_SYSFS_DIR = Path("/sys/class/leds")

# GPIO pin assignments (BCM numbering) - documentation only. The kernel
# gpio-led driver claims these pins directly via install.sh's
# dtoverlay=gpio-led,... lines; nothing in this module reads them.
_PIN_LED_R = 22
_PIN_LED_G = 23
_PIN_LED_B = 24

# gpio-led overlay labels - functionally load-bearing: install.sh's
# dtoverlay=gpio-led,...,label=<name> lines must use these same values,
# since each becomes the sysfs device name directly
# (/sys/class/leds/<label>/brightness). Unlike gpio-key, gpio-led's
# label= param was confirmed on-device to set the device name reliably,
# so no keycode-style disambiguation is needed here.
_LED_LABEL_RED = "led-red"
_LED_LABEL_GREEN = "led-green"
_LED_LABEL_BLUE = "led-blue"

# LED colour vocabulary - the single source of truth for what colours this
# LED supports; COLOURS below is built from these rather than separately
# hardcoding the same string keys.
COLOUR_RED = "red"
COLOUR_GREEN = "green"
COLOUR_BLUE = "blue"
COLOUR_WHITE = "white"
COLOUR_OFF = "off"


class RGBLed:
    COLOURS = {
        COLOUR_RED: (1, 0, 0),
        COLOUR_GREEN: (0, 1, 0),
        COLOUR_BLUE: (0, 0, 1),
        COLOUR_WHITE: (1, 1, 1),
        COLOUR_OFF: (0, 0, 0),
    }

    def __init__(self, red_label=_LED_LABEL_RED, green_label=_LED_LABEL_GREEN,
                 blue_label=_LED_LABEL_BLUE):
        self.paths = {
            "red": self._resolve(red_label),
            "green": self._resolve(green_label),
            "blue": self._resolve(blue_label),
        }
        self._running = asyncio.Event()

    @staticmethod
    def _resolve(label: str) -> Path:
        path = _LED_SYSFS_DIR / label / "brightness"
        if not path.exists():
            raise RuntimeError(
                f"No gpio-led sysfs entry found for {label!r} - check "
                "'dtoverlay=gpio-led,...' in /boot/firmware/config.txt and reboot"
            )
        try:
            path.write_text("0")
        except PermissionError as e:
            raise RuntimeError(
                f"No write access to {path} - check the LED udev rule "
                "(/etc/udev/rules.d/99-radioglobe-leds.rules) is installed and "
                "'udevadm control --reload-rules' has run"
            ) from e
        return path

    def set_color(self, color_name):
        color = self.COLOURS.get(color_name.lower(), (0, 0, 0))
        for channel, value in zip(("red", "green", "blue"), color):
            self.paths[channel].write_text(str(value))

    def off(self):
        self.set_color(COLOUR_OFF)

    def start(self):
        pass  # sysfs entries already exist once the gpio-led overlay is loaded

    async def stop(self):
        """Turn the LED off. Nothing to release - the kernel driver owns the pins."""
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
