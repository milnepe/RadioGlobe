import asyncio
import RPi.GPIO as GPIO  # type: ignore


class AsyncDialWithButton:
    def __init__(self, on_button_press=None):
        self.direction = 0
        self.button_pressed = False
        self._stop_event = asyncio.Event()
        self._task = None
        self._button_task = None
        self.on_button_press = on_button_press  # 👈 callback on press

        GPIO.setmode(GPIO.BCM)
        GPIO.setup([17, 18, 27], GPIO.IN, pull_up_down=GPIO.PUD_UP)

    def get_direction(self):
        return_val = self.direction
        self.direction = 0
        return return_val

    def get_button(self):
        was_pressed = self.button_pressed
        self.button_pressed = False
        return was_pressed

    async def _wait_for_edge(self, pin, edge=GPIO.FALLING):
        return await asyncio.to_thread(GPIO.wait_for_edge, pin, edge)

    async def run_encoder(self):
        while not self._stop_event.is_set():
            await self._wait_for_edge(17, GPIO.FALLING)
            if self._stop_event.is_set():
                break

            new_direction = GPIO.input(18)
            if not new_direction:
                new_direction = -1
            self.direction = new_direction

            await asyncio.sleep(0.3)  # Debounce

    async def run_button(self):
        while not self._stop_event.is_set():
            await self._wait_for_edge(27, GPIO.FALLING)
            if self._stop_event.is_set():
                break

            # Debounce
            await asyncio.sleep(0.01)
            if GPIO.input(27) == 0:
                if self.on_button_press:
                    asyncio.create_task(self.on_button_press())  # 🔔 flash LED etc.
                self.button_pressed = True

                while GPIO.input(27) == 0 and not self._stop_event.is_set():
                    await asyncio.sleep(0.01)

    def start(self):
        self._task = asyncio.create_task(self.run_encoder())
        self._button_task = asyncio.create_task(self.run_button())

    async def stop(self):
        self._stop_event.set()
        if self._task:
            await self._task
        if self._button_task:
            await self._button_task
        GPIO.cleanup()
