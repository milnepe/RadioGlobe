#! /usr/bin/python3
import re
import time
import threading
import subprocess
import logging

from streaming import Streamer, set_volume
import database
# from display import Display
from grove_display import Display
from positional_encoders import *
from ui_manager import UI_Manager
from rgb_led import RGB_LED
from scheduler import Scheduler

logging.basicConfig(level=logging.DEBUG)

# Inject test encoder co-ordinates for station index 1 "Shkodra, AL"
ENCODER_LATITUDE = 632
ENCODER_LATITUDE_OFFSET = 1024
ENCODER_LONGITUDE = 567
ENCODER_LONGITUDE_OFFSET = 1024
ENCODER_RESOLUTION = 1024

AUDIO_SERVICE = "pulse"
VOLUME_INCREMENT = 5

state = "start"
volume_display = False
volume = 95
jog = 0
last_jog = 0
state_entry = True
ui_manager = UI_Manager()


# This is used to increase the size of the area searched around the coords
# For example, fuzziness 2, latitude 50 and longitude 0 will result in a
# search square 48,1022 to 52,2 (with encoder resolution 1024)
def Look_Around(latitude: int, longitude: int, fuzziness: int):
    # Offset fuzziness, so 0 means only the given coords
    fuzziness += 1

    search_coords = []

    # Work out how big the perimeter is for each layer out from the origin
    ODD_NUMBERS = [((i * 2) + 1) for i in range(0, fuzziness)]

    # With each 'layer' of fuzziness we need a starting point.
    # 70% of people are right-eye dominant and the globe is likely to
    # be below the user, so go down and left first then scan
    # horizontally, moving up
    for layer in range(0, fuzziness):
        for y in range(0, ODD_NUMBERS[layer]):
            for x in range(0, ODD_NUMBERS[layer]):
                coord_x = (latitude + x - (ODD_NUMBERS[layer] // 2)) % ENCODER_RESOLUTION
                coord_y = (longitude + y - (ODD_NUMBERS[layer] // 2)) % ENCODER_RESOLUTION
                if [coord_x, coord_y] not in search_coords:
                    search_coords.append([coord_x, coord_y])

    return search_coords


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
    global volume
    global volume_display
    global jog
    global ui_manager
    global encoders_thread
    global rgb_led

    ui_events = []
    ui_manager.update(ui_events)

    for event in ui_events:
        if event[0] == "Jog":
            # Next station
            if event[1] == 1:
                jog += 1
            # Previous station
            elif event[1] == -1:
                jog -= 1
            logging.debug(f'Joggling: {jog}')

        elif event[0] == "Volume":
            if event[1] == 1:
                volume += VOLUME_INCREMENT
                volume = set_volume(volume)
                volume_display = True
                scheduler.attach_timer(Clear_Volume_Display, 3)
                rgb_led.set_static("BLUE", timeout_sec=0.5,
                                   restore_previous_on_timeout=True)
                print(("Volume up: {}%").format(volume))

        elif event[1] == -1:
            if state == "shutdown_confirm":
                Back_To_Tuning()
            else:
                volume -= VOLUME_INCREMENT
                volume = set_volume(volume)
                volume_display = True
                scheduler.attach_timer(Clear_Volume_Display, 3)
                rgb_led.set_static("BLUE", timeout_sec=0.5,
                                   restore_previous_on_timeout=True)
                print(("Volume down: {}%").format(volume))

        elif event[0] == "Random":
            print("Toggle jog mode - not implemented")

        elif event[0] == "Shutdown":
            state = "shutdown_confirm"
            state_entry = True

        elif event[0] == "Calibrate":
            # Zero the positional encoders
            offsets = encoders_thread.zero()
            database.Save_Calibration(offsets[0], offsets[1])
            rgb_led.set_static("GREEN", timeout_sec=0.5,
                               restore_previous_on_timeout=True)
            print("Calibrated")
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


# PROGRAM START
database.Load_Map()
encoder_offsets = database.Load_Calibration()

# Positional encoders - used to select latitude and longitude
# encoders_thread = Positional_Encoders(2, "Encoders", encoder_offsets[0], encoder_offsets[1])
# encoders_thread.start()

display_thread = Display(3, "Display")
display_thread.start()

rgb_led = RGB_LED(20, "RGB_LED")
rgb_led.start()

scheduler = Scheduler(50, "SCHEDULER")
scheduler.start()

set_volume(volume)
previous_state = None

# jog = 0
# last_jog = 0

while True:
    # Displays a start-up message
    # Transitions to Tuning
    if state == "start":
        logging.debug(f'State: {state}')
        lines = ["Radio Globe", "Made for DesignSpark",
                 "by Jude Pullen and", "Donald Robson, 2020"]
        display_thread.message(lines)
        time.sleep(3)
        state = "tuning"

    # Tuning generates a search area around the cross-hair set by the
    # size of the fuzziness value. Search area is a list of encoder
    # co-ordinates. Each co-ordinate is matched against the location
    # database until the first match is found. A list of stations for
    # that location is generated for the player
    # Transitions to play
    elif state == "tuning":
        logging.debug(f'State: {state}')

        latitude = ENCODER_LATITUDE
        latitude_offset = ENCODER_LATITUDE_OFFSET
        longitude = ENCODER_LONGITUDE
        longitude_offset = ENCODER_LONGITUDE_OFFSET
        logging.debug(f'Encoder Lat, Lon idx: {latitude}, {longitude}')
        # coordinates = encoders_thread.get_readings()
        coordinates = [(latitude + latitude_offset) % ENCODER_RESOLUTION,
                       (longitude + longitude_offset) % ENCODER_RESOLUTION]
        search_area = Look_Around(coordinates[0], coordinates[1], fuzziness=3)
        logging.debug(f'Search area: {search_area}')
        stations_list = []
        url_list = []
        last_jog = jog = 0

        # Check the search area.  Saving the first location name encountered
        # and all radio stations in the area, in order encountered
        for ref in search_area:
            logging.debug(f'Encoder Lat, Lon idx: {ref[0]}, {ref[1]}')
            index = database.index_map[ref[0]][ref[1]]
            logging.debug(f'Index: {index}')

            if index != 0xFFFF:
                # encoders_thread.latch(coordinates[0], coordinates[1], stickiness=3)
                location = database.Get_Location_By_Index(index)
                # Set first location found for player
                if location:
                    logging.debug(f'Location found: {location}')
                    for station in database.stations_data[location]["urls"]:
                        # De-dup lists
                        if station["name"] not in stations_list:
                            stations_list.append(station["name"])
                        if station["url"] not in url_list:
                            url_list.append(station["url"])
                    state = "play"
                    break

        # List out stations in search area
        logging.debug(f'Station list: {stations_list}')

        # Provide 'helper' coordinates
        # latitude = round((360 * coordinates[0] / ENCODER_RESOLUTION - 180), 2)
        # longitude = round((360 * coordinates[1] / ENCODER_RESOLUTION - 180), 2)

        if volume_display:
            volume_disp = volume
        else:
            volume_disp = 0

        logging.debug(f'Updating display, Lat: {latitude}, Lon: {longitude}')
        display_thread.update(latitude, longitude,
                              "Tuning...", volume_disp, "", False)

    # Plays the station for the current location and updates display
    elif state == "play":
        logging.debug(f'State: {state}')
        rgb_led.set_static("RED", timeout_sec=3.0)
        streamer = None

        # Get display coordinates - from file, so there's no jumping about
        latitude = database.stations_data[location]["coords"]["n"]
        longitude = database.stations_data[location]["coords"]["e"]
        logging.debug(f'Co-ordinates: Lat: {latitude}, Long: {longitude}')

        # Play the top station
        logging.debug(f'Playing URL: {url_list[jog]}')
        streamer = Streamer(AUDIO_SERVICE, url_list[jog])
        streamer.play()

        state = "updating"

    # Updating display with current station
    elif state == "updating":
        logging.debug(f'State: {state}')
        # Add arrows to the display if there is more than one station here
        if len(stations_list) > 1:
            display_thread.update(latitude, longitude, location,
                                  volume_disp, stations_list[jog], True)
        elif len(stations_list) == 1:
            display_thread.update(latitude, longitude, location,
                                  volume_disp, stations_list[jog], False)
        state = "playing"

    # Playing just waits for UI events and dispatches next state
    elif state == "playing":
        # If the jog dial is used, stop the stream and restart with the new url
        if jog != last_jog:
            state = "joggling"

        # Exit back to tuning state if latch has 'come unstuck'
        # elif not encoders_thread.is_latched():
            # streamer.stop()
            # state = "tuning"
            # logging.debug(f'going back to {state} state')
            # state_entry = true

        # Idle operation - just keep display updated
        else:
            if volume_display:
                volume_disp = volume
            else:
                volume_disp = 0

    # Joggling cycles round the stations list for the current location
    elif state == "joggling":
        logging.debug(f'State: {state}')
        # Restrict the jog dial value to the bounds of stations_list
        jog %= len(stations_list)
        last_jog = jog
        streamer.stop()
        state = "play"

    elif state == "shutdown_confirm":
        if state_entry:
            state_entry = False
            display_thread.clear()
            time.sleep(0.1)
            display_thread.message(line_1="Really shut down?",
                                   line_2="<- Press mid button ",
                                   line_3="to confirm or",
                                   line_4="<- bottom to cancel.")

            # Auto-cancel in 5s
            scheduler.attach_timer(Back_To_Tuning, 5)

    elif state == "shutdown":
        if state_entry:
            state_entry = False
            display_thread.clear()
            time.sleep(0.1)
            display_thread.message(line_1="Shutting down...",
                                   line_2="Please wait 10 sec",
                                   line_3="before disconnecting",
                                   line_4="power.")
            subprocess.run(["sudo", "poweroff"])

    else:
        # Just in case!
        state = "tuning"

    Process_UI_Events()

    # Avoid unnecessarily high polling
    # time.sleep(3)

    # Clean up threads
    # encoders_thread.join()
