import asyncio
import RPi.GPIO as GPIO


class AsyncDialWithButton:
    def __init__(self):
        self.direction = 0
        self.button_pressed = False
        self._stop_event = asyncio.Event()
        self._task = None
        self._button_task = None
        self._last_rotation = 0

        GPIO.setmode(GPIO.BCM)
        GPIO.setup([17, 18, 27], GPIO.IN, pull_up_down=GPIO.PUD_UP)

    def get_direction(self):
        """Returns the direction of last rotation: -1 (CCW), 1 (CW), or 0 (no new turn)."""
        return_val = self.direction
        self.direction = 0
        return return_val

    def get_button(self):
        """Returns True if button was pressed since last check, otherwise False."""
        was_pressed = self.button_pressed
        self.button_pressed = False
        return was_pressed

    async def _wait_for_edge(self, pin, edge=GPIO.FALLING):
        """Waits asynchronously for a GPIO edge event."""
        return await asyncio.to_thread(GPIO.wait_for_edge, pin, edge)

    async def run_encoder(self):
        while not self._stop_event.is_set():
            try:
                await self._wait_for_edge(17, GPIO.FALLING)
            except Exception as e:
                print(f"Encoder error: {e}")
                break

            if self._stop_event.is_set():
                break

            now = asyncio.get_event_loop().time()
            if now - self._last_rotation > 0.05:  # 50ms debounce
                self.direction = 1 if GPIO.input(18) == 0 else -1
                self._last_rotation = now

    async def run_button(self):
        while not self._stop_event.is_set():
            try:
                await self._wait_for_edge(27, GPIO.FALLING)
            except Exception as e:
                print(f"Button error: {e}")
                break

            if self._stop_event.is_set():
                break

            await asyncio.sleep(0.05)  # Debounce delay
            if GPIO.input(27) == 0:
                self.button_pressed = True

                while GPIO.input(27) == 0 and not self._stop_event.is_set():
                    await asyncio.sleep(0.01)

    def start(self):
        """Starts the encoder and button monitoring tasks."""
        if self._task or self._button_task:
            return  # Already started

        if self._stop_event.is_set():
            self._stop_event = asyncio.Event()

        self._task = asyncio.create_task(self.run_encoder())
        self._button_task = asyncio.create_task(self.run_button())

    async def stop(self):
        """Stops the monitoring tasks and cleans up GPIO."""
        self._stop_event.set()
        if self._task:
            await self._task
            self._task = None
        if self._button_task:
            await self._button_task
            self._button_task = None
        GPIO.cleanup()

    async def __aenter__(self):
        self.start()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.stop()
