"""
Test harness for async cvlc streamer
"""

import asyncio
import time
import database
from rgb_led_async import led_init, blink_led

# from coordinates import Coordinate
from radio_config import STATIONS_JSON
from positional_encoders_async import Positional_Encoders
from streaming.streaming_cvlc import StreamerCVLC


async def reader(encoders: Positional_Encoders):
    print("Starting reader...")
    while True:
        # Get a new pair of readings
        encoders.update()
        # Don't poll too quickly to allow for next reading
        await asyncio.sleep(0.2)  # 200 ms


async def get_cities(lat, lon, city_map, fuzziness=2) -> list:
    # Get the search area for the current position
    search_area = database.look_around((lat, lon), fuzziness=fuzziness)
    # print(f"Search area for ({lat}, {lon}): {search_area}")
    # Get any cities found for this location
    cities = database.get_found_cities(search_area, city_map)
    # await asyncio.sleep(0)
    return cities


async def main():
    """
    Returns the cities found when the reticule is moved
    NOTE: Start with the reticule set to the origin
    TODO: Convert cities found into a list of stations
    """
    # Override settings file
    STICKINESS = 2
    FUZZINESS = 5
    POLLING_SEC = 1
    AUDIO_SERVICE = "pulse"

    # Create led instance
    led = await led_init()

    # Initialise encoders
    print("Starting up encoders...")
    encoders = Positional_Encoders()
    # Note the globe should be set to the origin when starting main
    encoders.update()
    encoders.zero()
    # NOTE: Should return (512, 512) for origin
    initial_readings = encoders.get_readings()

    # Initialise a streamer
    # streamer = None

    # Start by setting the latch so we can see when it unlatches
    # This overrides the setting in the config
    # encoders.latch(*initial_readings, STICKINESS)
    print(initial_readings)
    # time.sleep(2)

    print("Loading stations data...")
    stations = database.Load_Stations(STATIONS_JSON)
    # print(stations)
    print("Building city map...")
    cities = database.build_map(stations)
    # print(cities)

    # # encoder_offsets = database.Load_Calibration()

    # Start reading the encoders continuosly in background
    asyncio.create_task(reader(encoders))

    # Display the encoder values periodically
    city_list = []
    station_info = None
    url = None
    streamer_task = None
    streamer = None
    while True:
        start_t = time.monotonic()
        readings = encoders.get_readings()
        city_list = await get_cities(*readings, cities, FUZZINESS)
        # Skip this bit if it's latched
        if not encoders.is_latched():
            # If we find a some cities in the area, latch on to the first one in the list
            if city_list:
                encoders.latch(*readings, STICKINESS)
                # Async blink in another thread so we don't block
                blink = asyncio.to_thread(blink_led, led, "RED", 0.5)
                await blink
                # Get first city in list then lookup first station for that city
                first_city = city_list[0]
                # station_info = database.get_first_station(first_city, stations)
                # Get all the stations info for the city we found
                station_info = database.get_station_urls(first_city, stations)
                print(f"Found: {city_list[0]} Station: {station_info}")
                # Get first atation url in list
                name, url = station_info[0]
                print(f"First station: {name}, URL: {url} Latched: {encoders.is_latched()}")
                # Check if the streamer is already playing, if so stop it
                if streamer_task and streamer:
                    streamer.stop()
                    # Wait for thread to finish cleanly
                    await streamer_task

                # Now start a new streamer in its own thread
                streamer = StreamerCVLC(AUDIO_SERVICE, url)
                streamer_task = asyncio.create_task(asyncio.to_thread(streamer.play))

        await asyncio.sleep(POLLING_SEC)
        elapst_t = time.monotonic() - start_t
        # print(f"Coords: {readings} Latched: {encoders.is_latched()} t={elapst_t:.1f}")


if __name__ == "__main__":
    asyncio.run(main())
