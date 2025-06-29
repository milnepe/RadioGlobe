import asyncio
import RPi.GPIO as GPIO
import time


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
        GPIO.add_event_detect(self.pin, GPIO.FALLING, callback=self._handle_press, bouncetime=150)

    def _handle_press(self, channel):
        self.loop.call_soon_threadsafe(lambda: asyncio.create_task(self._check_hold()))

    async def _check_hold(self):
        await asyncio.sleep(0.05)  # Debounce
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
    def __init__(self, name_and_pin_tuples, loop, long_press_threshold=1.0):
        self.buttons = [
            AsyncButton(name, pin, loop, long_press_threshold) for name, pin in name_and_pin_tuples
        ]

    async def poll_buttons(self, event_queue):
        while True:
            for button in self.buttons:
                event_type = button.get_event()
                if event_type:
                    await event_queue.put((button.name, event_type))
            await asyncio.sleep(0.05)

    def clear(self, button_name):
        for button in self.buttons:
            if button.name == button_name:
                button.clear()
                break


async def main():
    loop = asyncio.get_running_loop()

    button_manager = AsyncButtonManager(
        [("Jog_push", 27), ("Top", 5), ("Mid", 6), ("Low", 12), ("Shutdown", 26)], loop
    )

    button_events = asyncio.Queue()
    asyncio.create_task(button_manager.poll_buttons(button_events))

    try:
        while True:
            name, press_type = await button_events.get()
            print(f"{name}: {press_type} press")
    finally:
        GPIO.cleanup()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        GPIO.cleanup()
