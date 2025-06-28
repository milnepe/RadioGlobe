import asyncio
import vlc

from dial_button_async import AsyncDialWithButton
from positional_encoders_async import PositionalEncoders
from database import load_stations
from database import build_cities_index
from database import look_around
from database import get_first_station_info


# stations = [
#     ("WKSU Public Radio", "http://stream.wksu.org/wksu1.mp3.128"),
#     ("WCPN Public Radio", "http://audio1.ideastream.org/wcpn128.mp3"),
# ]


async def find_all_cities(points, cities):
    """
    Returns all cities that match with points
    """
    return [cities[pt] for pt in points if pt in cities]


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
        # self.stations = stations
        self.stations = None
        self.current_index = 0
        self.mode = "normal"

    def next_station(self, direction):
        """Navigate to the next or previous station."""
        self.current_index = (self.current_index + direction) % len(self.stations)
        name, url = self.stations[self.current_index]
        print(f"📻 Tuning to: {name}")
        self.audio_player.play(url)

    def switch_mode(self):
        """Toggle between application modes."""
        self.mode = "alt" if self.mode == "normal" else "normal"
        print(f"🌀 Mode switched to: {self.mode}")
        # Future mode-based behavior can go here

    async def run(self):
        """Main app loop."""
        STICKINESS = 10
        FUZZINESS = 3

        # Load the stations information into memory
        # stations_info = load_stations("perth-stations-test.json")
        stations_info = load_stations("stations.json")
        print(stations_info)

        cities_idx = build_cities_index(stations_info)
        print(cities_idx)

        # self.dial.start()

        task = asyncio.create_task(self.encoders.run())

        # name, url = self.stations[self.current_index]
        # print(f"📻 Starting with: {name}")
        # self.audio_player.play(url)

        try:
            await asyncio.sleep(0.5)
            coords_lat, coords_long = self.encoders.get_readings()
            print(f"Current Coordinates: Latitude {coords_lat}, Longitude {coords_long}")

            self.encoders.zero()
            print(
                f"Encoder offsets set to: {self.encoders.latitude_offset}, {self.encoders.longitude_offset}"
            )

            while True:
                await asyncio.sleep(0.1)

                coord = self.encoders.get_readings()
                # Get a list of coordinates that are close to the current coordinates
                # The size of the area is determined by the FUZZINESS value
                coords = look_around(coord, FUZZINESS)
                # Get any cities that match with the look around coords
                matches = await find_all_cities(coords, cities_idx)
                if not self.encoders.is_latched():
                    print(coord)
                    # Set the latch to hold onto any matched cities until the reticule moves again
                    # Sensitivity is determined by the STICKINESS value
                    if matches:
                        self.encoders.latch(*coord, stickiness=STICKINESS)
                        city = matches[0]  # First match
                        print(f"Matching cities: {matches} {self.encoders.is_latched()}")
                        name, url = get_first_station_info(stations_info, city)
                        print(f"📻 Tuning to: {name}")
                        self.audio_player.play(url)

                # direction = self.dial.get_direction()
                # if direction != 0:
                #     print(f"↪️ Dial turned: {'left' if direction > 0 else 'right'}")
                #     self.next_station(direction)

                # if self.dial.get_button():
                #     print("🖲️ Button pressed!")
                #     self.switch_mode()

        except KeyboardInterrupt:
            print("👋 Exiting on keyboard interrupt...")
        finally:
            self.audio_player.stop()
            await self.dial.stop()


if __name__ == "__main__":
    asyncio.run(App().run())
