import asyncio
import vlc
import RPi.GPIO as GPIO  # type: ignore

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


async def find_all_cities(coords, cities):
    """
    Returns all cities that match with points
    """
    return [cities[coord] for coord in coords if coord in cities]


class AudioPlayer:
    def __init__(self):
        self.instance = vlc.Instance("--input-repeat=-1")
        self.player = self.instance.media_player_new()
        self.current_url = None

    def play(self, url):
        """Play a new URL stream, stopping current playback if needed."""
        if self.player.is_playing():
            self.player.stop()

        self.current_url = url
        media = self.instance.media_new(url)
        self.player.set_media(media)
        self.player.play()
        print(f"🔊 Playing: {url}")

    def change_volume(self, delta, min_volume=10, max_volume=100):
        """Adjust volume by delta, clamped between min and max."""
        current_volume = self.player.audio_get_volume()
        new_volume = max(min_volume, min(max_volume, current_volume + delta))
        self.player.audio_set_volume(new_volume)
        print(f"🔉 Volume changed: {current_volume} -> {new_volume}")

    def change_volume_level(self, level: int):
        """Set volume off."""
        current_volume = self.player.audio_get_volume()
        self.player.audio_set_volume(level)
        print(f"🔉 Volume changed: {current_volume} -> {level}")

    def stop(self):
        """Stop playback if something is playing."""
        if self.player.is_playing():
            self.player.stop()


class App:
    def __init__(self):
        self.dial = AsyncDial()
        self.audio_player = AudioPlayer()
        self.encoders = PositionalEncoders()
        self.stations = None
        self.cities = None
        self.current_index = 0
        self.mode = "station"

    def next_station(self, direction):
        """Navigate to the next or previous station."""
        if not self.stations:
            print("⚠️ No stations available.")
            return
        self.current_index = (self.current_index + direction) % len(self.stations)
        print(self.stations)
        name, url = self.stations[self.current_index]
        print(f"📻 Tuning to: {name}")
        self.audio_player.play(url)

    def next_city(self, direction):
        """Navigate to the next or previous city."""
        if not self.cities:
            print("⚠️ No cities available.")
            return
        self.current_index = (self.current_index + direction) % len(self.cities)
        print(self.cities)
        name = self.cities[self.current_index]
        print(f"📻 Changed city: {name}")

    def switch_mode(self):
        """Toggle between application modes."""
        self.mode = "city" if self.mode == "station" else "station"
        print(f"🌀 Mode switched to: {self.mode}")
        # Future mode-based behavior can go here

    async def run(self):
        """Main app loop."""
        STICKINESS = 10
        FUZZINESS = 3

        # Load the stations information into memory
        # stations_info = load_stations("perth-stations-test.json")
        stations_info = load_stations("stations.json")
        # print(stations_info)

        cities_idx = build_cities_index(stations_info)
        # print(cities_idx)

        self.dial.start()
        self.encoders.start()

        led = RGBLed()
        led_running = asyncio.Event()

        # Button stuff
        async def handle_short_jog():
            print("🖲️ Button short press!")
            self.switch_mode()
            asyncio.create_task(led_task(led, led_running, "white", 0.2))

        async def handle_long_jog():
            print("🏃 Jog button long press: start continuous jog")
            await asyncio.sleep(0.2)

        async def handle_short_shutdown():
            print("🧯 Shutdown short press: ignored")
            await asyncio.sleep(0.05)

        async def handle_long_shutdown():
            print("🛑 Shutdown long press: shutting down system!")

        async def handle_short_top():
            print("🖲️ Button short press! Increasing volume.")
            self.audio_player.change_volume(10, min_volume=10, max_volume=100)
            asyncio.create_task(led_task(led, led_running, "white", 0.2))

        async def handle_long_top():
            print("🖲️ Button long press! Set volume on")
            self.audio_player.change_volume_level(80)
            asyncio.create_task(led_task(led, led_running, "green", 0.2))

        async def handle_short_bottom():
            print("🖲️ Button short press! Lowering volume.")
            self.audio_player.change_volume(-10, min_volume=10, max_volume=100)
            asyncio.create_task(led_task(led, led_running, "white", 0.2))

        async def handle_long_bottom():
            print("🖲️ Button long press! Set volume off")
            self.audio_player.change_volume_level(0)
            asyncio.create_task(led_task(led, led_running, "red", 0.2))

        loop = asyncio.get_running_loop()

        button_definitions = [
            ("Jog", 27, handle_short_jog, handle_long_jog),
            ("Top", 5, handle_short_top, handle_long_top),
            ("Bottom", 12, handle_short_bottom, handle_long_bottom),
            ("Shutdown", 26, handle_short_shutdown, handle_long_shutdown),
        ]

        button_manager = AsyncButtonManager(button_definitions, loop)
        await button_manager.start()
        asyncio.create_task(button_manager.handle_events())

        try:
            await asyncio.sleep(0.5)
            # Get current coordinates
            coords = self.encoders.get_readings()
            print(f"Current Coordinates: Latitude {coords[0]}, Longitude {coords[1]}")

            self.encoders.zero()
            print(
                f"Encoder offsets set to: {self.encoders.latitude_offset}, {self.encoders.longitude_offset}"
            )

            while True:
                await asyncio.sleep(0.1)

                coords = self.encoders.get_readings()
                # Get a list of coordinates that surround the current coordinates
                # The size of the look arround zone is determined by the FUZZINESS value
                zone = look_around(coords, FUZZINESS)
                # Get any cities that match with in the look arround zone
                matches = await find_all_cities(zone, cities_idx)
                if not self.encoders.is_latched():
                    # print(coords)

                    if matches:
                        # Flash LED to signal match
                        if not led_running.is_set():
                            asyncio.create_task(led_task(led, led_running, "green", 0.5))

                        # Set the latch to hold onto any matched cities until the reticule moves again
                        # Sensitivity is determined by the STICKINESS value
                        self.encoders.latch(*coords, stickiness=STICKINESS)
                        self.cities = matches
                        print(f"Matching cities: {matches} {self.encoders.is_latched()}")

                        # Play first station for first matched city
                        name, url = get_first_station_info(stations_info, self.cities[0])
                        print(f"📻 Tuning to: {self.cities[0]} {name}")
                        self.audio_player.play(url)

                        # Get the rest of the stations for current city
                        self.stations = get_all_station_info(stations_info, self.cities[0])

                # Modal selection of stations of city using dial
                direction = self.dial.get_direction()
                if direction != 0:
                    asyncio.create_task(led_task(led, led_running, "blue", 0.1))
                    print(f"↪️ Dial turned: {'left' if direction > 0 else 'right'}")
                    if self.mode == "station":
                        self.next_station(direction)
                    elif self.mode == "city":
                        self.next_city(direction)

        except KeyboardInterrupt:
            print("👋 Exiting on keyboard interrupt...")
        finally:
            self.audio_player.stop()
            await self.dial.stop()
            await self.encoders.stop()
            GPIO.cleanup()


if __name__ == "__main__":
    asyncio.run(App().run())
