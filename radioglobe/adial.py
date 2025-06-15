import asyncio
import logging
import RPi.GPIO as GPIO


class Jog_Encoder:
    def __init__(self, pin_a, pin_b, button_pin=None, queue=None):
        self.pin_a = pin_a
        self.pin_b = pin_b
        self.button_pin = button_pin
        self.queue = queue
        self.value = 0  # Current encoder value
        self._last_state = None  # To track encoder movement
        # BCM pin numbering!
        GPIO.setmode(GPIO.BCM)
        GPIO.setup([self.pin_a, self.pin_b], direction=GPIO.IN, pull_up_down=GPIO.PUD_UP)
        # self.direction = 0
        logging.info(f"Encoder initialized on pins {pin_a}, {pin_b}")
        if button_pin:
            logging.info(f"Encoder button initialized on pin {button_pin}")

    # def __del__(self):
    #     GPIO.cleanup()

    def _encoder_gpio_callback(self, channel):
        # This would be more complex, reading both encoder pins to determine direction
        # and then putting the event on the queue via call_soon_threadsafe.
        logging.info("Jog callback...")

    # async def monitor(self):
    #     logging.info(f"RPi.GPIO handling monitoring for Encoder {self.pin_a}/{self.pin_b}.")
    #     while True:
    #         await asyncio.sleep(60) # Keep task alive

    async def monitor(self):
        # This is where you'd read the actual GPIO pins.
        # For a real encoder, you'd typically use interrupts or poll frequently.
        # If using RPi.GPIO callbacks, you'd use loop.call_soon_threadsafe to put events in queue.
        # With gpiozero, you might integrate their event handling or poll more finely.
        logging.info(f"Monitoring Encoder {self.pin_a}/{self.pin_b}...")
        while True:
            # Simulate encoder turn
            if self.queue:
                if (
                    asyncio.get_event_loop().time() * 1000
                ) % 5000 < 50:  # Simulate a turn every 5 seconds
                    direction = "clockwise" if (self.value % 2 == 0) else "counter-clockwise"
                    self.value += 1
                    await self.queue.put(("encoder_turn", self.pin_a, direction, self.value))
                    logging.debug(f"Simulated encoder turn: {direction}, value: {self.value}")
                if (
                    self.button_pin and (asyncio.get_event_loop().time() * 1000) % 7000 < 50
                ):  # Simulate button press every 7 seconds
                    await self.queue.put(("button_press", self.button_pin, "encoder_button"))
                    logging.debug(f"Simulated encoder button press on {self.button_pin}")
            await asyncio.sleep(0.05)  # Poll frequently, but don't hog CPU


# In main's finally block, add GPIO cleanup:
# finally:
#     # ... (cancel tasks)
#     GPIO.cleanup() # Clean up RPi.GPIO resources
#     logging.info("System gracefully shut down and GPIO cleaned up.")
