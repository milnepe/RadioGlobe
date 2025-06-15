import asyncio
import signal

# import sys
import logging
# from functools import partial

# --- Hardware Abstraction (Placeholders) ---
# You would replace these with actual imports and hardware setup
# For example, if using gpiozero:
# from gpiozero import Button, RotaryEncoder
# from gpiozero.exc import BadPinFactory
from adial import Jog_Encoder

# Basic logging setup
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


# --- Event Handlers (Business Logic) ---


# async def handle_encoder_event(event_data, display, audio_player):
async def handle_encoder_event(event_data):
    encoder_id, direction, value = event_data[1], event_data[2], event_data[3]
    logging.info(f"Encoder {encoder_id} turned {direction}, new value: {value}")
    # await display.update_display(f"Enc{encoder_id}: {value} {direction}")
    logging.info("Handler updated display...")
    if value % 10 == 0:
        # await audio_player.play_sound("click.wav")
        logging.info("Handler played something...")


# async def handle_button_event(event_data, display, audio_player):
#     button_pin, button_name = event_data[1], event_data[2]
#     logging.info(f"Button '{button_name}' (Pin {button_pin}) pressed!")
#     await display.update_display(f"Btn {button_name} pressed!")
#     await audio_player.play_sound("beep.wav")


# --- Main Application Logic ---


# async def event_processor(event_queue, display, audio_player):
async def event_processor(event_queue):
    logging.info("Event processor started...")
    while True:
        event_type, *data = await event_queue.get()
        if event_type == "encoder_turn":
            # await handle_encoder_event(("encoder_turn", *data), display, audio_player)
            await handle_encoder_event(("encoder_turn", *data))
        elif event_type == "button_press":
            # await handle_button_event(("button_press", *data), display, audio_player)
            pass
        # Add more event types as needed
        event_queue.task_done()


async def main():
    logging.info("Starting hardware monitoring system...")

    # Event queue for inter-task communication
    event_queue = asyncio.Queue()

    # Initialize hardware components
    # display = Display()
    # audio_player = AudioPlayer()

    # encoders = [
    #     Jog_Encoder(pin_a=17, pin_b=18, button_pin=27, queue=event_queue),
    #     Encoder(pin_a=23, pin_b=24, button_pin=None, queue=event_queue),
    #     Encoder(pin_a=5, pin_b=6, button_pin=13, queue=event_queue),
    # ]
    encoders = [
        Jog_Encoder(pin_a=17, pin_b=18, button_pin=27, queue=event_queue),
    ]

    # buttons = [
    #     Button(pin=4, name="Menu Button", queue=event_queue),
    #     Button(pin=22, name="Select Button", queue=event_queue),
    #     Button(pin=10, name="Back Button", queue=event_queue),
    # ]

    # Create tasks for monitoring each hardware component
    monitor_tasks = []
    for encoder in encoders:
        monitor_tasks.append(asyncio.create_task(encoder.monitor()))
    # for button in buttons:
    #     monitor_tasks.append(asyncio.create_task(button.monitor()))

    # Create a task for processing events from the queue
    # processor_task = asyncio.create_task(event_processor(event_queue, display, audio_player))
    processor_task = asyncio.create_task(event_processor(event_queue))

    # Add a global shutdown handler
    stop_event = asyncio.Event()

    def signal_handler():
        logging.info("Shutdown signal received. Initiating graceful shutdown...")
        stop_event.set()

    loop = asyncio.get_running_loop()

    loop.add_signal_handler(signal.SIGINT, signal_handler)
    loop.add_signal_handler(signal.SIGTERM, signal_handler)

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
