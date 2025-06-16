import asyncio
import RPi.GPIO as GPIO
import logging
import signal
import database

from radio_config import STATIONS_JSON

from jog_encoder import Jog_Encoder
from streaming.python_vlc_streaming import Streamer

# --- Globals ---
state = "city_found"
stations_list = None

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


# --- Remaining example usage (main function and dummy classes) as before ---
async def handle_encoder_event(event_data, display, audio_player):
    global state
    encoder_id, direction, value = event_data[1], event_data[2], event_data[3]
    if state == "city_found" and value in range(0, len(stations_list)):
        name, url = stations_list[value]
        logging.info(
            f"Encoder {encoder_id} turned {direction}, new value: {value} Next Station: {name} {url}"
        )
        state = "playing"
        audio_player.play(url)
    elif state == "playing" and value in range(0, len(stations_list)):
        name, url = stations_list[value]
        logging.info(
            f"Encoder {encoder_id} turned {direction}, new value: {value} Next Station: {name} {url}"
        )
        state = "city_found"
        audio_player.stop()
    # else:
    #     logging.info(f"Encoder {encoder_id} turned {direction}, new value: {value} Previous Station")
    # await display.update_display(f"Enc{encoder_id}: {value} {direction}")
    # if value % 10 == 0:
    #     await audio_player.play_sound("click.wav")


async def handle_button_event(event_data, display, audio_player):
    button_pin, button_name = event_data[1], event_data[2]
    logging.info(f"Button '{button_name}' (Pin {button_pin}) pressed!")
    await display.update_display(f"Btn {button_name} pressed!")
    await audio_player.play_sound("beep.wav")


async def event_processor(event_queue, display, audio_player):
    logging.info("Event processor started...")
    while True:
        event_type, *data = await event_queue.get()
        if event_type == "encoder_turn":
            await handle_encoder_event(("encoder_turn", *data), display, audio_player)
        # elif event_type == "button_press":
        #     await handle_button_event(("button_press", *data), display, audio_player)
        event_queue.task_done()


class Display:
    def __init__(self):
        logging.info("Display initialized.")

    async def update_display(self, message):
        logging.info(f"Display update: {message}")
        await asyncio.sleep(0.01)


class AudioPlayer:
    def __init__(self):
        logging.info("Audio Player initialized.")

    async def play_sound(self, sound_file):
        logging.info(f"Playing sound: {sound_file}")
        await asyncio.sleep(0.05)


async def main():
    global stations_list
    logging.info("Starting hardware monitoring system...")

    city = "Perth,AU"

    event_queue = asyncio.Queue()
    display = Display()
    audio_player = Streamer()

    print("Loading stations data...")
    stations = database.Load_Stations(STATIONS_JSON)
    # print(stations)
    print("Building city map...")
    map = database.build_map(stations)
    print(map)
    stations_list = database.get_stations_info(city, stations)
    print(f"Stations info\n {stations_list}")

    # Get the running event loop *here*, in the main thread
    # This must be called after asyncio.run() has started the loop
    current_loop = asyncio.get_running_loop()

    # Pass the loop to the Encoder instance
    encoder1 = Jog_Encoder(pin_a=17, pin_b=18, button_pin=27, queue=event_queue, loop=current_loop)

    monitor_tasks = [
        asyncio.create_task(encoder1.monitor()),
    ]

    processor_task = asyncio.create_task(event_processor(event_queue, display, audio_player))

    stop_event = asyncio.Event()

    def signal_handler():
        logging.info("Shutdown signal received.")
        stop_event.set()

    loop = asyncio.get_running_loop()

    loop.add_signal_handler(signal.SIGINT, signal_handler)
    loop.add_signal_handler(signal.SIGTERM, signal_handler)

    try:
        await stop_event.wait()
    except asyncio.CancelledError:
        logging.info("Main task cancelled.")
    finally:
        logging.info("Shutting down tasks...")
        for task in monitor_tasks:
            task.cancel()
        processor_task.cancel()

        await asyncio.gather(*monitor_tasks, processor_task, return_exceptions=True)

        try:
            await asyncio.wait_for(event_queue.join(), timeout=5.0)
            logging.info("All queue items processed.")
        except asyncio.TimeoutError:
            logging.warning("Timeout waiting for event queue to empty.")

        GPIO.cleanup()
        logging.info("System gracefully shut down and GPIO cleaned up.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Application exited by KeyboardInterrupt (Ctrl+C).")
    except Exception as e:
        logging.error(f"An unhandled error occurred in asyncio.run(): {e}")
