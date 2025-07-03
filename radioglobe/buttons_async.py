import asyncio
import RPi.GPIO as GPIO  # type: ignore
import time
import inspect


class AsyncButton:
    def __init__(self, name, gpio_pin, loop, long_press_threshold=1.0):
        self.name = name
        self.pin = gpio_pin
        self.loop = loop
        self.long_press_threshold = long_press_threshold

        self._pressed = False
        self._press_start = None
        self._event_ready = None  # "short" or "long"

        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.add_event_detect(self.pin, GPIO.FALLING, callback=self._handle_press, bouncetime=50)

    def _handle_press(self, channel):
        self.loop.call_soon_threadsafe(lambda: asyncio.create_task(self._check_hold()))

    async def _check_hold(self):
        await asyncio.sleep(0.05)  # debounce
        if not self._pressed and GPIO.input(self.pin) == GPIO.LOW:
            self._pressed = True
            self._press_start = time.monotonic()

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

        for name, pin, short_cb, long_cb in button_definitions:
            btn = AsyncButton(name, pin, loop, long_press_threshold)
            self.buttons.append(btn)
            setattr(btn, "short_cb", short_cb)
            setattr(btn, "long_cb", long_cb)

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
        """Continuously process events with the appropriate handler."""
        while True:
            name, event_type = await self.event_queue.get()
            for btn in self.buttons:
                if btn.name == name:
                    handler = getattr(btn, f"{event_type}_cb", None)
                    if handler:
                        if inspect.iscoroutinefunction(handler):
                            await handler()
                        else:
                            handler()

    def get_event_nowait(self):
        try:
            return self.event_queue.get_nowait()
        except asyncio.QueueEmpty:
            return None


async def main():
    # Async-compatible handlers

    async def handle_short_jog():
        print("🚶 Jog button short press: jog step")
        await asyncio.sleep(0.1)  # simulate async work

    async def handle_long_jog():
        print("🏃 Jog button long press: start continuous jog")
        await asyncio.sleep(0.2)

    async def handle_short_shutdown():
        print("🧯 Shutdown short press: ignored")
        await asyncio.sleep(0.05)

    async def handle_long_shutdown():
        print("🛑 Shutdown long press: shutting down system!")

    await asyncio.sleep(0.5)
    loop = asyncio.get_running_loop()

    button_definitions = [
        ("Jog", 27, handle_short_jog, handle_long_jog),
        ("Shutdown", 26, handle_short_shutdown, handle_long_shutdown),
    ]

    button_manager = AsyncButtonManager(button_definitions, loop)
    await button_manager.start()
    asyncio.create_task(button_manager.handle_events())

    try:
        while True:
            # Your normal tasks (dial, encoders, etc)
            await asyncio.sleep(0.1)

    except KeyboardInterrupt:
        print("👋 Exiting...")
    finally:
        GPIO.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
