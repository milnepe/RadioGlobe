import asyncio
import logging

import RPi.GPIO as GPIO  # type: ignore

PIN17 = 17
PIN18 = 18


class AsyncDial:
    def __init__(self):
        self.direction = 0
        self._stop_event = asyncio.Event()
        self._task = None
        GPIO.setmode(GPIO.BCM)
        GPIO.setup([PIN17, PIN18], GPIO.IN, pull_up_down=GPIO.PUD_UP)

    def get_direction(self):
        return_val = self.direction
        self.direction = 0
        # change sign
        return return_val * -1

    async def _wait_for_edge(self, pin, edge=GPIO.FALLING):
        return await asyncio.to_thread(GPIO.wait_for_edge, pin, edge)

    async def run_encoder(self):
        while not self._stop_event.is_set():
            await self._wait_for_edge(PIN17, GPIO.FALLING)
            if self._stop_event.is_set():
                break

            new_direction = GPIO.input(PIN18)
            if not new_direction:
                new_direction = -1
                # new_direction = 1
            self.direction = new_direction

            await asyncio.sleep(0.3)  # Debounce

    def start(self):
        self._task = asyncio.create_task(self.run_encoder())

    async def stop(self):
        self._stop_event.set()
        if self._task:
            await self._task
        GPIO.cleanup()


async def main():
    dial = AsyncDial()
    dial.start()

    try:
        logging.debug("Listening for dial input. Press Ctrl+C to stop.")
        while True:
            await asyncio.sleep(0.1)
            direction = dial.get_direction()
            if direction != 0:
                logging.debug(f"Direction: {'Left' if direction == 1 else 'Right'}")
    except KeyboardInterrupt:
        logging.debug("\nStopping dial...")
    finally:
        await dial.stop()
        logging.debug("Cleaned up and exited.")


if __name__ == "__main__":
    asyncio.run(main())
