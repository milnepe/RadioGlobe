import asyncio
import RPi.GPIO as GPIO


class AsyncButton:
    def __init__(self, name, gpio_pin, loop):
        self.name = name
        self.pin = gpio_pin
        self.loop = loop
        self.held_time = -1
        self.latched_time = -1

        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.add_event_detect(self.pin, GPIO.FALLING, callback=self._handle_press, bouncetime=150)

    def _handle_press(self, channel):
        self.loop.call_soon_threadsafe(asyncio.create_task, self._check_hold())

    async def _check_hold(self):
        await asyncio.sleep(0.1)  # Debounce
        if GPIO.input(self.pin) == GPIO.LOW:
            self.held_time = 0
        else:
            self.latched_time = 0

    async def update(self):
        if self.held_time >= 0:
            if GPIO.input(self.pin) == GPIO.HIGH:
                self.latched_time = self.held_time
                self.held_time = -1
            else:
                self.held_time += 1
                self.latched_time += 1

    def get_time_held(self):
        return_val = self.latched_time
        if self.held_time == -1:
            self.latched_time = -1
        return return_val

    def clear(self):
        self.held_time = -1
        self.latched_time = -1


class AsyncButtonManager:
    def __init__(self, name_and_pin_tuples, loop):
        self.buttons = [AsyncButton(name, pin, loop) for name, pin in name_and_pin_tuples]

    async def poll_buttons(self, event_queue):
        while True:
            for button in self.buttons:
                await button.update()
                time_held = button.get_time_held()
                if time_held != -1:
                    event_queue.append((button.name, time_held))
            await asyncio.sleep(1)

    def clear(self, button_name):
        for button in self.buttons:
            if button.name == button_name:
                button.clear()
                break



async def main():
    button_manager = AsyncButtonManager([
        ("Jog_push", 27),
        ("Top", 5),
        ("Mid", 6),
        ("Low", 12),
        ("Shutdown", 26)
    ])

    button_events = []

    asyncio.create_task(button_manager.poll_buttons(button_events))

    while True:
        while button_events:
            print(button_events.pop(0))
        await asyncio.sleep(0.1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        GPIO.cleanup()
