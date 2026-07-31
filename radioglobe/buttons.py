import asyncio
import time
import inspect
import logging
from typing import Callable, NamedTuple, Optional

import RPi.GPIO as GPIO  # type: ignore


class ButtonDefinition(NamedTuple):
    name: str
    pin: int
    short_cb: Optional[Callable] = None
    long_cb: Optional[Callable] = None
    press_cb: Optional[Callable] = None


class AsyncButton:
    def __init__(self, name, gpio_pin, loop, long_press_threshold=1.0, press_cb=None):
        self.name = name
        self.pin = gpio_pin
        self.loop = loop
        self.long_press_threshold = long_press_threshold

        self._pressed = False
        self._press_start = None
        self._event_ready = None  # "short" or "long"
        self.press_cb = press_cb  # callback for press-down

        GPIO.setup(self.pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.add_event_detect(self.pin, GPIO.FALLING, callback=self._handle_press, bouncetime=50)

    def _handle_press(self, channel):
        self.loop.call_soon_threadsafe(lambda: asyncio.create_task(self._check_hold()))

    async def _check_hold(self):
        await asyncio.sleep(0.05)  # debounce
        if not self._pressed and GPIO.input(self.pin) == GPIO.LOW:
            self._pressed = True
            self._press_start = time.monotonic()

            # 🔔 Fire press-down callback immediately
            if self.press_cb:
                if inspect.iscoroutinefunction(self.press_cb):
                    await self.press_cb()
                else:
                    self.press_cb()

            # Wait for release
            while GPIO.input(self.pin) == GPIO.LOW:
                await asyncio.sleep(0.05)

            held_time = time.monotonic() - self._press_start
            self._pressed = False
            self._press_start = None

            if held_time >= self.long_press_threshold:
                self._event_ready = "long"
            else:
                self._event_ready = "short"

    def get_event(self):
        if self._event_ready:
            result = self._event_ready
            self._event_ready = None
            return result
        return None

    def clear(self):
        self._pressed = False
        self._press_start = None
        self._event_ready = None


class AsyncButtonManager:
    def __init__(self, button_definitions, loop, long_press_threshold=1.0):
        self.buttons = []
        self.event_queue = asyncio.Queue()

        # Required before any AsyncButton's GPIO.setup() call below. Not
        # every caller constructs an App first (e.g. the standalone
        # integration scripts under tests/integration/), so this class
        # guarantees its own precondition rather than assuming some other
        # part of the app already set it - setmode is idempotent, so this
        # is harmless even when a caller (like App) also calls it.
        GPIO.setmode(GPIO.BCM)

        for definition in button_definitions:
            btn = AsyncButton(
                definition.name, definition.pin, loop, long_press_threshold, definition.press_cb
            )
            self.buttons.append(btn)
            setattr(btn, "short_cb", definition.short_cb)
            setattr(btn, "long_cb", definition.long_cb)

    async def start(self):
        asyncio.create_task(self._poll_buttons())

    async def _poll_buttons(self):
        while True:
            for button in self.buttons:
                event_type = button.get_event()
                if event_type:
                    await self.event_queue.put((button.name, event_type))
            await asyncio.sleep(0.05)

    async def handle_events(self):
        """Continuously process events with the appropriate handler.

        A handler that raises must not kill this loop - it's the single
        consumer for every button's events, so an uncaught exception here
        would silently stop short/long dispatch for all buttons, not just
        the one whose handler failed.
        """
        while True:
            name, event_type = await self.event_queue.get()
            for btn in self.buttons:
                if btn.name == name:
                    handler = getattr(btn, f"{event_type}_cb", None)
                    if handler:
                        try:
                            if inspect.iscoroutinefunction(handler):
                                await handler()
                            else:
                                handler()
                        except Exception:
                            logging.exception(f"Button handler failed: {btn.name} {event_type}")

    def get_event_nowait(self):
        try:
            return self.event_queue.get_nowait()
        except asyncio.QueueEmpty:
            return None
