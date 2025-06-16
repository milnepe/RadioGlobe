import asyncio
import RPi.GPIO as GPIO
import logging
import time


logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

ENCODER_DEBOUNCE_MS = 2
BUTTON_DEBOUNCE_MS = 50


class Jog_Encoder:
    def __init__(self, pin_a, pin_b, button_pin=None, queue=None, loop=None):
        self.pin_a = pin_a
        self.pin_b = pin_b
        self.button_pin = button_pin
        self.queue = queue
        self.loop = loop  # Store the event loop passed from main thread
        if self.loop is None:
            raise ValueError("An asyncio event loop must be provided to the Encoder.")

        self.value = 0
        self.direction = None

        self._last_pin_a_state = None
        self._last_pin_b_state = None
        self._last_button_state = None

        self._last_a_edge_time = 0
        self._last_b_edge_time = 0
        self._last_button_edge_time = 0

        # Setup GPIO
        GPIO.setmode(GPIO.BCM)

        GPIO.setup(self.pin_a, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(self.pin_b, GPIO.IN, pull_up_down=GPIO.PUD_UP)

        GPIO.add_event_detect(
            self.pin_a,
            GPIO.BOTH,
            callback=self._encoder_gpio_callback,
            bouncetime=ENCODER_DEBOUNCE_MS,
        )
        GPIO.add_event_detect(
            self.pin_b,
            GPIO.BOTH,
            callback=self._encoder_gpio_callback,
            bouncetime=ENCODER_DEBOUNCE_MS,
        )

        if self.button_pin:
            GPIO.setup(self.button_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            GPIO.add_event_detect(
                self.button_pin,
                GPIO.FALLING,
                callback=self._button_gpio_callback,
                bouncetime=BUTTON_DEBOUNCE_MS,
            )
            logging.info(f"Encoder button initialized on pin {button_pin} (falling edge detect).")

        self._last_pin_a_state = GPIO.input(self.pin_a)
        self._last_pin_b_state = GPIO.input(self.pin_b)
        if self.button_pin:
            self._last_button_state = GPIO.input(self.button_pin)

        logging.info(f"Encoder initialized on pins A:{pin_a}, B:{pin_b}.")

    def _encoder_gpio_callback(self, channel):
        current_time = time.time() * 1000

        if channel == self.pin_a:
            if current_time - self._last_a_edge_time < ENCODER_DEBOUNCE_MS:
                return
            self._last_a_edge_time = current_time
        elif channel == self.pin_b:
            if current_time - self._last_b_edge_time < ENCODER_DEBOUNCE_MS:
                return
            self._last_b_edge_time = current_time

        pin_a_state = GPIO.input(self.pin_a)
        pin_b_state = GPIO.input(self.pin_b)

        if pin_a_state == self._last_pin_a_state and pin_b_state == self._last_pin_b_state:
            return

        # Quadrature decoding logic
        # ... (same logic as before) ...
        if channel == self.pin_a:
            if pin_a_state != self._last_pin_a_state:
                if pin_a_state == GPIO.HIGH:
                    if pin_b_state == GPIO.LOW:
                        self.value -= 1
                        self.direction = "counter-clockwise"
                    else:
                        self.value += 1
                        self.direction = "clockwise"
                else:
                    if pin_b_state == GPIO.HIGH:
                        self.value -= 1
                        self.direction = "counter-clockwise"
                    else:
                        self.value += 1
                        self.direction = "clockwise"
        elif channel == self.pin_b:
            if pin_b_state != self._last_pin_b_state:
                if pin_b_state == GPIO.HIGH:
                    if pin_a_state == GPIO.HIGH:
                        self.value -= 1
                        self.direction = "counter-clockwise"
                    else:
                        self.value += 1
                        self.direction = "clockwise"
                else:
                    if pin_a_state == GPIO.LOW:
                        self.value -= 1
                        self.direction = "counter-clockwise"
                    else:
                        self.value += 1
                        self.direction = "clockwise"

        self._last_pin_a_state = pin_a_state
        self._last_pin_b_state = pin_b_state

        if (
            self.direction and self.queue and self.loop.is_running()
        ):  # Check if loop is running before scheduling
            try:
                self.loop.call_soon_threadsafe(
                    self.queue.put_nowait, ("encoder_turn", self.pin_a, self.direction, self.value)
                )
                logging.debug(f"Encoder event put in queue: {self.direction}, value {self.value}")
            except RuntimeError as e:
                # This could still happen if the loop closes right after is_running() check
                logging.warning(
                    f"Failed to put encoder event in queue (loop might be closing): {e}"
                )
            except asyncio.QueueFull:
                logging.warning("Encoder event queue is full, skipping event.")

    def _button_gpio_callback(self, channel):
        current_time = time.time() * 1000
        if current_time - self._last_button_edge_time < BUTTON_DEBOUNCE_MS:
            return
        self._last_button_edge_time = current_time

        if GPIO.input(channel) == GPIO.LOW:
            logging.info(f"Encoder button on channel {channel} pressed!")
            if self.queue and self.loop.is_running():  # Check if loop is running
                try:
                    self.loop.call_soon_threadsafe(
                        self.queue.put_nowait, ("button_press", channel, "encoder_button")
                    )
                    logging.debug(f"Button event put in queue: encoder_button on {channel}")
                except RuntimeError as e:
                    logging.warning(
                        f"Failed to put button event in queue (loop might be closing): {e}"
                    )
                except asyncio.QueueFull:
                    logging.warning("Button event queue is full, skipping event.")

    async def monitor(self):
        logging.info(f"Encoder {self.pin_a}/{self.pin_b} monitoring active via RPi.GPIO callbacks.")
        while True:
            await asyncio.sleep(60)
