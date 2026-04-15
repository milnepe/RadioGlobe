import asyncio

import RPi.GPIO as GPIO  # type: ignore

from .radio_config import PIN_DIAL_CLOCK, PIN_DIAL_DIR


class AsyncDial:
    def __init__(self):
        self.queue: asyncio.Queue[int] = asyncio.Queue()
        self._stop_event = asyncio.Event()
        self._task = None
        GPIO.setmode(GPIO.BCM)
        GPIO.setup([PIN_DIAL_CLOCK, PIN_DIAL_DIR], GPIO.IN, pull_up_down=GPIO.PUD_UP)

    async def _wait_for_edge(self, pin, edge=GPIO.FALLING):
        return await asyncio.to_thread(GPIO.wait_for_edge, pin, edge)

    async def run_encoder(self):
        while not self._stop_event.is_set():
            await self._wait_for_edge(PIN_DIAL_CLOCK, GPIO.FALLING)
            if self._stop_event.is_set():
                break

            new_direction = GPIO.input(PIN_DIAL_DIR)
            if not new_direction:
                new_direction = -1
            await self.queue.put(new_direction * -1)

            await asyncio.sleep(0.3)  # Debounce

    def start(self):
        self._task = asyncio.create_task(self.run_encoder())

    async def stop(self):
        self._stop_event.set()
        if self._task:
            await self._task
        GPIO.cleanup()
