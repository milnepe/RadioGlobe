import asyncio
import subprocess
import logging
import os
import json

import RPi.GPIO as GPIO  # type: ignore

from audio_async import AudioPlayer
from dial_async import AsyncDial
from positional_encoders_async import PositionalEncoders

from rgb_led_async import RGBLed
from rgb_led_async import led_task

from database import load_stations
from database import build_cities_index
from database import look_around
from database import get_stations_by_city

from buttons_async import AsyncButtonManager

from coordinates import Coordinate
from display_async import Display


class App:
    def __init__(self):
        self.dial = AsyncDial()
        self.audio_player = AudioPlayer()
        self.audio_player.change_volume_level(50)
        self.encoders = PositionalEncoders()
        self.display = Display()
        self.stations = None
        self.station = None
        self.station_idx = None
        self.cities = None
        self.city = None
        self.city_idx = None
        self.jog_idx = 0
        self.mode = "station"
        self.stations_info = load_stations("stations.json")
        self.cities_info = build_cities_index(self.stations_info)

    def save_state(self, cache="~/cache/radioglobe.json"):
        def safe(obj):
            if isinstance(obj, tuple):
                return list(obj)
            return obj

        logging.debug(f"STATIONS: {self.stations}")
        state = {
            "stations": self.stations,
            "station": self.station,
            "station_idx": self.station_idx,
            "cities": self.cities,
            "city": self.city,
            "city_idx": self.city_idx,
            "jog_idx": self.jog_idx,
            "mode": self.mode,
            "lat": self.encoders.latitude,
            "lon": self.encoders.longitude,
            "lat_offset": self.encoders.latitude_offset,
            "lon_offset": self.encoders.longitude_offset,
            "latch": True,
        }

        path = os.path.expanduser(cache)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(state, f)

    def load_state(self):
        path = os.path.expanduser("~/cache/radioglobe.json")
        if not os.path.exists(path):
            return
        with open(path, "r") as f:
            state = json.load(f)

        self.stations = state.get("stations")
        self.station = tuple(state["station"]) if state.get("station") else None
        self.station_idx = state.get("station_idx")
        self.cities = tuple(state["cities"]) if state.get("cities") else None
        self.city = state.get("city")
        self.city_idx = state.get("city_idx")
        self.jog_idx = state.get("jog_idx")
        self.mode = state.get("mode")
        self.encoders.latitude = state.get("lat")
        self.encoders.longitude = state.get("lon")
        self.encoders.latitude_offset = state.get("lat_offset")
        self.encoders.longitude_offset = state.get("lon_offset")
        self.encoders.latch_stickiness = True

    def next_station(self, direction):
        """Navigate to the next or previous station."""
        if not self.stations:
            logging.debug("⚠️ No stations available.")
            return
        self.jog_idx = (self.jog_idx + direction) % len(self.stations)
        logging.debug(f"jog:{self.jog_idx} {self.stations}")
        self.station = self.stations[self.jog_idx]
        logging.debug(f"📻 Tuning to: jog:{self.jog_idx} {self.station}")

    def next_city(self, direction):
        """Navigate to the next or previous city."""
        if not self.cities:
            logging.debug("⚠️ No cities available.")
            return
        self.jog_idx = (self.jog_idx + direction) % len(self.cities)
        self.city = self.cities[self.jog_idx]
        self.stations = get_stations_by_city(self.stations_info, self.city)
        logging.debug(f"📻 Changed city: jog:{self.jog_idx} {self.city} {self.stations}")

    def switch_mode(self):
        """Toggle between application modes."""
        self.mode = "city" if self.mode == "station" else "station"
        logging.debug(
            f"🌀 Mode switched to: {self.mode} jog:{self.jog_idx} {self.city} {self.station}"
        )
        # Future mode-based behavior can go here

    async def run(self):
        """Main app loop."""
        STICKINESS = 10
        FUZZINESS = 3

        # Load any saved state
        self.load_state()

        self.dial.start()
        self.encoders.start()
        self.display.start()

        led = RGBLed()
        led_running = asyncio.Event()

        async def find_all_cities(coords, cities):
            """Returns all cities that match with coords"""
            return [cities[coord] for coord in coords if coord in cities]

        def get_coords_by_city(city):
            """Lat / lon helper"""
            lat = self.stations_info[city]["coords"]["n"]
            lon = self.stations_info[city]["coords"]["e"]
            return Coordinate(lat, lon)

        # Button stuff
        async def update_volume(delta):
            """Volume change and display helper"""
            volume = self.audio_player.change_volume(delta)
            coords = get_coords_by_city(self.city)
            self.display.update(coords, self.city, volume, self.station[0], False)
            await asyncio.sleep(0.5)
            self.display.update(coords, self.city, 0, self.station[0], False)

        async def update_volume_level(level):
            """Volume level and display helper"""
            volume = self.audio_player.change_volume_level(level)
            coords = get_coords_by_city(self.city)
            self.display.update(coords, self.city, volume, self.station[0], False)
            await asyncio.sleep(0.5)
            self.display.update(coords, self.city, 0, self.station[0], False)

        async def handle_short_jog():
            self.switch_mode()
            if self.mode == "station":
                result = self.stations
            else:
                result = self.cities
            logging.debug(f"🖲️ Jog button short press! Change mode jog: {self.jog_idx} {result}")
            asyncio.create_task(led_task(led, led_running, "green", 0.2))

        async def handle_long_jog():
            logging.debug("🖲️ Jog button long press: None")
            await asyncio.sleep(0.2)

        async def on_sound_press():
            asyncio.create_task(led_task(led, led_running, "blue", 0.2))  # LED flashes on press

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

        async def on_mid_press():
            asyncio.create_task(led_task(led, led_running, "green", 0.2))  # LED flashes on press

        async def handle_short_mid():
            logging.debug("🖲️ Mid button mid short press! Calibrating.")
            self.encoders.zero()
            logging.debug(
                f"Encoder offsets set to: {self.encoders.latitude}, {self.encoders.longitude} {self.encoders.latitude_offset}, {self.encoders.longitude_offset}"
            )
            self.display.update(Coordinate(0, 0), "Calibrated", 0, "", False)
            await asyncio.sleep(0.5)

        async def handle_long_mid():
            logging.debug("🔴 Shutdown initiated! Powering off...")
            # Save app state
            self.save_state()
            logging.debug("Saved state...")
            self.display.update("", "Shutdown", 0, "", False)
            await asyncio.sleep(2)  # Delay before shutdown for visibility
            subprocess.run(["sudo", "poweroff"])

        loop = asyncio.get_running_loop()

        button_definitions = [
            ("Jog", 27, handle_short_jog, None),
            ("Top", 5, handle_short_top, handle_long_top, on_sound_press),
            ("Mid", 6, handle_short_mid, handle_long_mid, on_mid_press),  # 👈 press_cb added
            ("Bottom", 12, handle_short_bottom, handle_long_bottom, on_sound_press),
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
            await asyncio.sleep(2)

            try:
                self.load_state()
            except Exception:
                logging.debug("Config not found...")
            logging.debug(
                f"State: {self.encoders.latitude_offset} {self.encoders.longitude_offset} {self.mode} {self.city} {self.station} {self.encoders.is_latched()}"
            )

            # The latch is set if there was saved state - this triggers playing the saved station
            if self.encoders.is_latched():
                coords = get_coords_by_city(self.city)
                self.display.update(coords, self.city, 0, self.station[0], False)
                self.audio_player.play(self.city, self.station)
                logging.debug(
                    f"Playing saved station: {self.station} {self.city} {self.cities} {self.stations}"
                )
            else:
                self.display.update((0, 0), "CALIBRATE", 0, "", False)

            while True:
                await asyncio.sleep(0.1)

                coords = self.encoders.get_readings()
                # logging.debug(coords)
                # Get a list of coordinates that surround the current coordinates
                # The size of the look arround zone is determined by the FUZZINESS value
                zone = look_around(coords, FUZZINESS)
                # Get any cities that match in the look arround zone
                self.cities = await find_all_cities(zone, self.cities_info)
                # logging.debug(f"Latch: {self.encoders.is_latched()} cities: {self.cities}")
                if not self.encoders.is_latched() and self.cities:
                    logging.debug(f"latch: {self.encoders.is_latched()} Cities: {self.cities}")
                    # Flash LED to signal match
                    if not led_running.is_set():
                        asyncio.create_task(led_task(led, led_running, "green", 0.5))

                    # Set the latch to hold onto any matched cities until the reticule moves again
                    # Sensitivity is determined by the STICKINESS value
                    self.encoders.latch(*coords, stickiness=STICKINESS)
                    # Reset indexes to 0
                    self.jog_idx = self.city_idx = 0
                    logging.debug(
                        f"Matching cities: current:{self.jog_idx} city:{self.city_idx} stick:{STICKINESS} fuzz:{FUZZINESS} {self.cities} {self.encoders.is_latched()}"
                    )
                    # Get first city in cities list
                    self.city = self.cities[self.city_idx]
                    # Get list of stations (name, url) for first city
                    self.stations = get_stations_by_city(self.stations_info, self.city)
                    # Get the first station (name, url) in the stations list
                    self.jog_idx = self.station_idx = 0
                    self.station = self.stations[self.station_idx]
                    logging.debug(
                        f"📻 Tuning to: current:{self.jog_idx} city:{self.city_idx} stat:{self.station_idx} {self.city} {self.station}\n{self.stations}"
                    )
                    coords = get_coords_by_city(self.city)
                    self.display.update(coords, self.city, 0, self.station[0], False)
                    # Play first cities' first station
                    self.audio_player.play(self.city, self.station)

                # Modal selection of stations and city using dial
                direction = self.dial.get_direction()
                if direction != 0:
                    asyncio.create_task(led_task(led, led_running, "blue", 0.1))
                    logging.debug(
                        f"↪️ Dial turned: {'right' if direction > 0 else 'left'} dir:{direction}"
                    )
                    if self.mode == "station":
                        self.next_station(direction)
                    elif self.mode == "city":
                        self.next_city(direction)
                        # Get first station for next city
                        self.station = get_stations_by_city(self.stations_info, self.city)[0]

                    coords = get_coords_by_city(self.city)
                    self.display.update(coords, self.city, 0, self.station[0], False)
                    self.audio_player.play(self.city, self.station)

        except KeyboardInterrupt:
            logging.debug("👋 Exiting on keyboard interrupt...")
        finally:
            self.audio_player.stop()
            await self.dial.stop()
            await self.encoders.stop()
            GPIO.cleanup()


if __name__ == "__main__":
    logging.basicConfig()
    logging.getLogger().setLevel(logging.DEBUG)

    logging.info("Starting RadioGlobe...")

    asyncio.run(App().run())
