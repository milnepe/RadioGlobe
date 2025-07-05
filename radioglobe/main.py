import asyncio
import subprocess
import logging

import RPi.GPIO as GPIO  # type: ignore

from audio_async import AudioPlayer
from dial_async import AsyncDial
from positional_encoders_async import PositionalEncoders

from rgb_led_async import RGBLed
from rgb_led_async import led_task

from database import load_stations
from database import build_cities_index
from database import look_around
from database import get_first_station_info
from database import get_all_station_info

from buttons_async import AsyncButtonManager

from coordinates import Coordinate
from display_async import Display


class App:
    def __init__(self):
        self.dial = AsyncDial()
        self.audio_player = AudioPlayer()
        self.encoders = PositionalEncoders()
        self.display = Display()
        self.stations = None
        self.station = None
        self.cities = None
        self.city = None
        self.url = None
        self.current_index = 0
        self.mode = "station"
        self.volume = 50

    def next_station(self, direction):
        """Navigate to the next or previous station."""
        if not self.stations:
            logging.debug("⚠️ No stations available.")
            return
        self.current_index = (self.current_index + direction) % len(self.stations)
        logging.debug(self.stations)
        self.station, self.url = self.stations[self.current_index]
        logging.debug(f"📻 Tuning to: {self.station}")

    def next_city(self, direction):
        """Navigate to the next or previous city."""
        if not self.cities:
            logging.debug("⚠️ No cities available.")
            return
        self.current_index = (self.current_index + direction) % len(self.cities)
        logging.debug(self.cities)
        self.city = self.cities[self.current_index]
        logging.debug(f"📻 Changed city: {self.city}")

    def switch_mode(self):
        """Toggle between application modes."""
        self.mode = "city" if self.mode == "station" else "station"
        logging.debug(f"🌀 Mode switched to: {self.mode}")
        # Future mode-based behavior can go here

    async def run(self):
        """Main app loop."""
        STICKINESS = 10
        FUZZINESS = 3

        # Load the stations information into memory
        # stations_info = load_stations("perth-stations-test.json")
        stations_info = load_stations("stations.json")
        # logging.debug(stations_info)

        cities_idx = build_cities_index(stations_info)
        # logging.debug(cities_idx)

        self.dial.start()
        self.encoders.start()
        self.display.start()

        led = RGBLed()
        led_running = asyncio.Event()

        async def find_all_cities(coords, cities):
            """Returns all cities that match with coords"""
            return [cities[coord] for coord in coords if coord in cities]

        def get_coords():
            """Lat / lon helper"""
            lat = stations_info[self.city]["coords"]["n"]
            lon = stations_info[self.city]["coords"]["e"]
            return Coordinate(lat, lon)

        # Button stuff
        async def update_volume(delta):
            """Volume and display helper"""
            volume = self.audio_player.change_volume(delta, min_volume=10, max_volume=100)
            coords = get_coords()
            self.display.update(coords, self.city, volume, self.station, False)
            await asyncio.sleep(0.5)
            self.display.update(coords, self.city, 0, self.station, False)
            asyncio.create_task(led_task(led, led_running, "white", 0.2))

        async def update_volume_level(level):
            """Volume and display helper"""
            volume = self.audio_player.change_volume_level(level)
            coords = get_coords()
            self.display.update(coords, self.city, volume, self.station, False)
            await asyncio.sleep(0.5)
            self.display.update(coords, self.city, 0, self.station, False)
            asyncio.create_task(led_task(led, led_running, "white", 0.2))

        async def handle_short_jog():
            logging.debug("🖲️ Jog button short press! Change mode")
            self.switch_mode()
            asyncio.create_task(led_task(led, led_running, "green", 0.2))

        async def handle_long_jog():
            logging.debug("🖲️ Jog button long press: None")
            await asyncio.sleep(0.2)

        async def handle_short_top():
            logging.debug("🖲️ Top button short press! Increasing volume.")
            await update_volume(10)

        async def handle_long_top():
            logging.debug("🖲️ Top button long press! Set volume on")
            await update_volume_level(80)

        async def handle_short_bottom():
            logging.debug("🖲️ Bottom button short press! Lowering volume.")
            await update_volume(-10)

        async def handle_long_bottom():
            logging.debug("🖲️ Bottom button long press! Set volume off")
            await update_volume_level(0)

        async def handle_short_mid():
            logging.debug("🖲️ Mid button mid short press! Calibrating.")
            self.encoders.zero()
            asyncio.create_task(led_task(led, led_running, "green", 0.2))
            logging.debug(
                f"Encoder offsets set to: {self.encoders.latitude_offset}, {self.encoders.longitude_offset}"
            )
            self.display.update(Coordinate(0, 0), "Calibrated", 0, "", False)
            await asyncio.sleep(0.5)

        async def handle_long_mid():
            logging.debug("🔴 Shutdown initiated! Powering off...")
            asyncio.create_task(led_task(led, led_running, "red", 0.2))
            await asyncio.sleep(2)  # Optional delay before shutdown for visibility
            subprocess.run(["sudo", "poweroff"])

        loop = asyncio.get_running_loop()

        button_definitions = [
            ("Jog", 27, handle_short_jog, None),
            ("Top", 5, handle_short_top, handle_long_top),
            ("Mid", 6, handle_short_mid, handle_long_mid),
            ("Bottom", 12, handle_short_bottom, handle_long_bottom),
        ]

        button_manager = AsyncButtonManager(button_definitions, loop)
        await button_manager.start()
        asyncio.create_task(button_manager.handle_events())

        try:
            self.display.message(
                line_1="Radio Globe",
                line_2="Made for DesignSpark",
                line_3="Jude Pullen, Donald",
                line_4="Robson, Pete Milne",
            )
            await asyncio.sleep(5)

            lat, lon = self.encoders.get_readings()
            self.display.update(Coordinate(0, 0), "Calibrate", 0, "", False)
            await asyncio.sleep(0)
            logging.debug(f"Current Coordinates: Latitude {lat}, Longitude {lon}")

            while True:
                await asyncio.sleep(0.1)

                coords = self.encoders.get_readings()
                # Get a list of coordinates that surround the current coordinates
                # The size of the look arround zone is determined by the FUZZINESS value
                zone = look_around(coords, FUZZINESS)
                # Get any cities that match with in the look arround zone
                matches = await find_all_cities(zone, cities_idx)
                if not self.encoders.is_latched():
                    # logging.debug(coords)

                    if matches:
                        # Flash LED to signal match
                        if not led_running.is_set():
                            asyncio.create_task(led_task(led, led_running, "green", 0.5))

                        # Set the latch to hold onto any matched cities until the reticule moves again
                        # Sensitivity is determined by the STICKINESS value
                        self.encoders.latch(*coords, stickiness=STICKINESS)
                        self.cities = matches
                        logging.debug(f"Matching cities: {matches} {self.encoders.is_latched()}")

                        # Play first station for first matched city
                        self.city = self.cities[0]
                        # latitude = stations_info[self.city]["coords"]["n"]
                        # longitude = stations_info[self.city]["coords"]["e"]
                        self.station, self.url = get_first_station_info(stations_info, self.city)
                        logging.debug(f"📻 Tuning to: {self.city} {self.station}")
                        coords = get_coords()
                        self.display.update(coords, self.city, 0, self.station, False)
                        # await asyncio.sleep(0)
                        self.audio_player.play(self.url)

                        # Get the rest of the stations for current city
                        self.stations = get_all_station_info(stations_info, self.cities[0])

                # Modal selection of stations and city using dial
                direction = self.dial.get_direction()
                if direction != 0:
                    asyncio.create_task(led_task(led, led_running, "blue", 0.1))
                    logging.debug(f"↪️ Dial turned: {'left' if direction > 0 else 'right'}")
                    if self.mode == "station":
                        self.next_station(direction)
                    elif self.mode == "city":
                        self.next_city(direction)
                        self.station, self.url = get_first_station_info(stations_info, self.city)
                    coords = get_coords()
                    self.display.update(coords, self.city, 0, self.station, False)
                    self.audio_player.play(self.url)

        except KeyboardInterrupt:
            logging.debug("👋 Exiting on keyboard interrupt...")
        finally:
            self.audio_player.stop()
            await self.dial.stop()
            await self.encoders.stop()
            GPIO.cleanup()


if __name__ == "__main__":
    format = "%(asctime)s: %(message)s"
    logging.basicConfig(format=format, level=logging.INFO, datefmt="%H:%M:%S")
    logging.getLogger().setLevel(logging.DEBUG)

    logging.info("Starting RadioGlobe...")

    asyncio.run(App().run())
