import time
import threading
import subprocess
import logging
import vlc
import database

from streaming.python_vlc_streaming import Streamer
from display import Display
from positional_encoders import *
from ui_manager import UI_Manager
from rgb_led import RGB_LED
from scheduler import Scheduler
from radio_config import STATIONS_JSON, FUZZINESS, STICKINESS, VOLUME_INCREMENT

state = "start"
volume_display = False
jog = 0
last_jog = 0
state_entry = True


ui_manager = UI_Manager()
streamer = Streamer()


def update_volume(streamer: Streamer, cmd: str):
    """Set Streamer volume up or down"""
    volume = streamer.get_volume()
    if cmd == "up":
        volume += VOLUME_INCREMENT
    else:  # down
        volume -= VOLUME_INCREMENT
    if volume >= 100:
        volume = 100
    elif volume <= 0:
        volume = 0
    streamer.set_volume(volume)


def Back_To_Tuning():
    global state
    global state_entry

    if state != "tuning":
        state = "tuning"
        state_entry = True


def Clear_Volume_Display():
    global volume_display

    volume_display = False


def Process_UI_Events():
    global state
    global state_entry
    global volume_display
    global jog
    global ui_manager
    global encoders_thread
    global rgb_led

    ui_events = []
    ui_manager.update(ui_events)

    for event in ui_events:
        if event[0] == "Jog":
            if event[1] == 1:
                # Next station
                jog += 1
            elif event[1] == -1:
                # Previous station
                jog -= 1

        elif event[0] == "Volume":
            if event[1] == 1:
                update_volume(streamer, "up")
                volume_display = True
                scheduler.attach_timer(Clear_Volume_Display, 3)
                rgb_led.set_static("BLUE", timeout_sec=0.5, restore_previous_on_timeout=True)
            elif event[1] == -1:
                if state == "shutdown_confirm":
                    Back_To_Tuning()
                else:
                    update_volume(streamer, "down")
                    volume_display = True
                    scheduler.attach_timer(Clear_Volume_Display, 3)
                    rgb_led.set_static("BLUE", timeout_sec=0.5, restore_previous_on_timeout=True)

        elif event[0] == "Random":
            logging.info("Toggle jog mode - not implemented")

        elif event[0] == "Shutdown":
            state = "shutdown_confirm"
            state_entry = True

        elif event[0] == "Calibrate":
            # Zero the positional encoders
            offsets = encoders_thread.zero()
            database.Save_Calibration(offsets[0], offsets[1])
            rgb_led.set_static("GREEN", timeout_sec=0.5, restore_previous_on_timeout=True)
            logging.info("Calibrated")
            display_thread.message(
                line_1="",
                line_2="Calibrated!",
                line_3="",
                line_4="")

            time.sleep(1)

        elif event[0] == "Confirm":
            if state == "shutdown_confirm":
                state = "shutdown"
                state_entry = True
            else:
                pass


format = "%(asctime)s: %(message)s"
logging.basicConfig(format=format, level=logging.INFO, datefmt="%H:%M:%S")
logging.getLogger().setLevel(logging.DEBUG)

logging.info("Starting RadioGlobe...")

stations_data = database.Load_Stations(STATIONS_JSON)
city_map = database.build_map(stations_data)
encoder_offsets = database.Load_Calibration()

# Positional encoders - used to select latitude and longitude
encoders_thread = Positional_Encoders(2, "Encoders", encoder_offsets[0], encoder_offsets[1])
encoders_thread.start()

display_thread = Display(3, "Display")
display_thread.start()

rgb_led = RGB_LED(20, "RGB_LED")
rgb_led.start()

scheduler = Scheduler(50, "SCHEDULER")
scheduler.start()

while True:
    if state == "start":
        # Entry - setup state
        if state_entry:
            state_entry = False
            logging.debug(f"State, {state}")
            display_thread.message(
                line_1="Radio Globe",
                line_2="Made for DesignSpark",
                line_3="Jude Pullen, Donald",
                line_4="Robson, Pete Milne")
            # Allow time to get network
            scheduler.attach_timer(Back_To_Tuning, 5)

    elif state == "tuning":
        logging.debug(f"State, {state}")
        # Entry - setup state
        if state_entry:
            state_entry = False
            rgb_led.set_blink("WHITE")
            display_thread.clear()

        # Normal operation
        else:
            # Look around and gather station info in the search area
            coords_lat, coords_long = encoders_thread.get_readings()
            logging.debug(f"Coordinates: {coords_lat}, {coords_long}")
            search_area = database.look_around((coords_lat, coords_long), fuzziness=FUZZINESS)
            location_name, latitude, longitude, stations_list, url_list = database.get_found_stations(search_area,
                                                                                                      city_map, stations_data)
            if location_name != "":
                encoders_thread.latch(coords_lat, coords_long, stickiness=STICKINESS)
                logging.debug("Latched...")
                # Stations found so start playing them otherwise stay tuning
                state = "playing"
                state_entry = True
            if volume_display:
                volume_disp = streamer.get_volume()
            else:
                volume_disp = 0

            display_thread.update(latitude, longitude,
                                  "Tuning...", volume_disp, "", False)

    elif state == "playing":
        # Entry - setup
        if state_entry:
            state_entry = False
            jog = 0
            last_jog = 0
            rgb_led.set_static("RED", timeout_sec=3.0)

            # Get display coordinates - from file, so there's no jumping about
            latitude = stations_data[location_name]["coords"]["n"]
            longitude = stations_data[location_name]["coords"]["e"]

            # Play the top station
            if url_list:
                logging.debug(f"Station: {stations_list[jog]}, {url_list[jog]}")
                streamer.play(url_list[jog])

        # Exit back to tuning state if latch has 'come unstuck'
        elif not encoders_thread.is_latched():
            logging.debug("Unlatching...")

            streamer.stop()
            state = "tuning"
            state_entry = True

        # If the jog dial is used, stop the stream and restart with the new URL
        elif jog != last_jog:
            # Restrict the jog dial value to the bounds of stations_list
            jog %= len(stations_list)
            last_jog = jog
            logging.debug(f"Station: {stations_list[jog]}, {url_list[jog]}")
            streamer.play(url_list[jog])

        # Idle operation - just keep display updated
        else:
            if volume_display:
                volume_disp = streamer.get_volume()
            else:
                volume_disp = 0

            # Add arrows to the display if there is more than one station here
            if len(stations_list) > 1:
                display_thread.update(latitude, longitude, location_name, volume_disp, stations_list[jog], True)
            elif len(stations_list) == 1:
                display_thread.update(latitude, longitude, location_name, volume_disp, stations_list[jog], False)

    elif state == "shutdown_confirm":
        logging.debug(f"State, {state}")
        if state_entry:
            state_entry = False
            display_thread.clear()
            time.sleep(0.1)
            display_thread.message(
                line_1="Really shut down?",
                line_2="<- Press mid button ",
                line_3="to confirm or",
                line_4="<- bottom to cancel.")

            # Auto-cancel in 5s
            scheduler.attach_timer(Back_To_Tuning, 5)

    elif state == "shutdown":
        logging.debug(f"State, {state}")
        if state_entry:
            state_entry = False
            display_thread.clear()
            time.sleep(0.1)
            display_thread.message(
                line_1="Shutting down...",
                line_2="Please wait 10 sec",
                line_3="before disconnecting",
                line_4="power.")
            subprocess.run(["sudo", "poweroff"])

    else:
        # Just in case!
        state = "tuning"

    Process_UI_Events()

    # Avoid unnecessarily high polling
    time.sleep(0.2)

# Clean up threads
encoders_thread.join()
