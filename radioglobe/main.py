import asyncio
import vlc

from dial_button_async import AsyncDialWithButton

from positional_encoders_async import PositionalEncoders

from rgb_led_async import RGBLed
from rgb_led_async import led_task

from database import load_stations
from database import build_cities_index
from database import look_around
from database import get_first_station_info
from database import get_all_station_info


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

    def stop(self):
        """Stop playback if something is playing."""
        if self.player.is_playing():
            self.player.stop()


class App:
    def __init__(self):
        self.dial = AsyncDialWithButton()
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

        led = RGBLed()
        led_running = asyncio.Event()
        # worker_task = asyncio.create_task(worker(led, led_running))

        asyncio.create_task(self.encoders.run())

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
                    print(coords)

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
                        print(f"📻 Tuning to: {name}")
                        self.audio_player.play(url)

                        # Get the rest of the stations for current city
                        self.stations = get_all_station_info(stations_info, self.cities[0])

                # Select stations using dial
                direction = self.dial.get_direction()
                if direction != 0:
                    asyncio.create_task(led_task(led, led_running, "blue", 0.1))
                    print(f"↪️ Dial turned: {'left' if direction > 0 else 'right'}")
                    if self.mode == "station":
                        self.next_station(direction)
                    elif self.mode == "city":
                        self.next_city(direction)

                if self.dial.get_button():
                    asyncio.create_task(led_task(led, led_running, "red", 0.2))
                    print("🖲️ Button pressed!")
                    self.switch_mode()

        except KeyboardInterrupt:
            print("👋 Exiting on keyboard interrupt...")
        finally:
            self.audio_player.stop()
            await self.dial.stop()


if __name__ == "__main__":
    asyncio.run(App().run())
