import asyncio
import signal
import sys
import logging
# from functools import partial

# --- Hardware Abstraction (Placeholders) ---
# You would replace these with actual imports and hardware setup
# For example, if using gpiozero:
# from gpiozero import Button, RotaryEncoder
# from gpiozero.exc import BadPinFactory

# Basic logging setup
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


class Encoder:
    def __init__(self, pin_a, pin_b, button_pin=None, queue=None):
        self.pin_a = pin_a
        self.pin_b = pin_b
        self.button_pin = button_pin
        self.queue = queue
        self.value = 0  # Current encoder value
        self._last_state = None  # To track encoder movement
        # In a real implementation, you'd set up GPIO input, pull-ups, and event detection.
        # For simplicity, we'll simulate events.
        logging.info(f"Encoder initialized on pins {pin_a}, {pin_b}")
        if button_pin:
            logging.info(f"Encoder button initialized on pin {button_pin}")

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


class Button:
    def __init__(self, pin, name, queue=None):
        self.pin = pin
        self.name = name
        self.queue = queue
        # In a real implementation, set up GPIO input and event detection.
        logging.info(f"Button '{name}' initialized on pin {pin}")

    async def monitor(self):
        # This is where you'd read the actual GPIO pin.
        # Use RPi.GPIO's add_event_detect with bouncetime for debouncing
        # and then loop.call_soon_threadsafe to deliver the event.
        logging.info(f"Monitoring Button '{self.name}' on pin {self.pin}...")
        while True:
            if self.queue:
                if (asyncio.get_event_loop().time() * 1000) % (
                    3000 + self.pin * 100
                ) < 50:  # Simulate button press
                    await self.queue.put(("button_press", self.pin, self.name))
                    logging.debug(f"Simulated button press: {self.name}")
            await asyncio.sleep(0.05)  # Poll frequently for simulation


class Display:
    def __init__(self):
        logging.info("Display initialized.")

    async def update_display(self, message):
        # Simulate display update (e.g., I2C communication to an LCD)
        logging.info(f"Display update: {message}")
        await asyncio.sleep(0.1)  # Simulate I/O time


class AudioPlayer:
    def __init__(self):
        logging.info("Audio Player initialized.")

    async def play_sound(self, sound_file):
        # Simulate playing an audio file
        logging.info(f"Playing sound: {sound_file}")
        await asyncio.sleep(0.5)  # Simulate audio playback time


# --- Event Handlers (Business Logic) ---


async def handle_encoder_event(event_data, display, audio_player):
    encoder_id, direction, value = event_data[1], event_data[2], event_data[3]
    logging.info(f"Encoder {encoder_id} turned {direction}, new value: {value}")
    await display.update_display(f"Enc{encoder_id}: {value} {direction}")
    if value % 10 == 0:
        await audio_player.play_sound("click.wav")


async def handle_button_event(event_data, display, audio_player):
    button_pin, button_name = event_data[1], event_data[2]
    logging.info(f"Button '{button_name}' (Pin {button_pin}) pressed!")
    await display.update_display(f"Btn {button_name} pressed!")
    await audio_player.play_sound("beep.wav")


# --- Main Application Logic ---


async def event_processor(event_queue, display, audio_player):
    logging.info("Event processor started...")
    while True:
        event_type, *data = await event_queue.get()
        if event_type == "encoder_turn":
            await handle_encoder_event(("encoder_turn", *data), display, audio_player)
        elif event_type == "button_press":
            await handle_button_event(("button_press", *data), display, audio_player)
        # Add more event types as needed
        event_queue.task_done()


async def main():
    logging.info("Starting hardware monitoring system...")

    # Event queue for inter-task communication
    event_queue = asyncio.Queue()

    # Initialize hardware components
    display = Display()
    audio_player = AudioPlayer()

    encoders = [
        Encoder(pin_a=17, pin_b=18, button_pin=27, queue=event_queue),
        Encoder(pin_a=23, pin_b=24, button_pin=None, queue=event_queue),
        Encoder(pin_a=5, pin_b=6, button_pin=13, queue=event_queue),
    ]

    buttons = [
        Button(pin=4, name="Menu Button", queue=event_queue),
        Button(pin=22, name="Select Button", queue=event_queue),
        Button(pin=10, name="Back Button", queue=event_queue),
    ]

    # Create tasks for monitoring each hardware component
    monitor_tasks = []
    for encoder in encoders:
        monitor_tasks.append(asyncio.create_task(encoder.monitor()))
    for button in buttons:
        monitor_tasks.append(asyncio.create_task(button.monitor()))

    # Create a task for processing events from the queue
    processor_task = asyncio.create_task(event_processor(event_queue, display, audio_player))

    # Add a global shutdown handler
    stop_event = asyncio.Event()

    def signal_handler():
        logging.info("Shutdown signal received. Initiating graceful shutdown...")
        stop_event.set()

    loop = asyncio.get_running_loop()
    if (
        sys.platform != "win32"
    ):  # Windows doesn't support add_signal_handler for SIGTERM/SIGINT directly
        loop.add_signal_handler(signal.SIGINT, signal_handler)
        loop.add_signal_handler(signal.SIGTERM, signal_handler)
    else:
        # On Windows, Ctrl+C generates a KeyboardInterrupt.
        # We can catch this with a try-except around asyncio.run()
        pass

    try:
        # Wait for the stop event to be set (e.g., by signal handler)
        await stop_event.wait()
    except asyncio.CancelledError:
        logging.info("Main task cancelled.")
    except KeyboardInterrupt:
        logging.info("KeyboardInterrupt received. Initiating graceful shutdown...")
    finally:
        logging.info("Shutting down tasks...")
        # Cancel all monitoring and processing tasks
        for task in monitor_tasks:
            task.cancel()
        processor_task.cancel()

        # Wait for all tasks to complete their cancellation
        await asyncio.gather(*monitor_tasks, processor_task, return_exceptions=True)

        # Wait for any remaining items in the queue to be processed
        # A timeout might be useful here to prevent indefinite waiting if a task hangs
        try:
            await asyncio.wait_for(event_queue.join(), timeout=5.0)
            logging.info("All queue items processed.")
        except asyncio.TimeoutError:
            logging.warning("Timeout waiting for event queue to empty.")

        logging.info("System gracefully shut down.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Application exited by KeyboardInterrupt.")
    except Exception as e:
        logging.error(f"An unhandled error occurred: {e}")
