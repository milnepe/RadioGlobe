import asyncio
import time
import database

# from coordinates import Coordinate
from radio_config import STATIONS_JSON
from positional_encoders_async import Positional_Encoders


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
    STICKINESS = 1
    FUZZINESS = 5
    POLLING_SEC = 0.5

    # Initialise encoders
    print("Starting up encoders...")
    encoders = Positional_Encoders()
    # Note the globe should be set to the origin when starting main
    encoders.update()
    encoders.zero()
    # NOTE: Should return (512, 512) for origin
    initial_readings = encoders.get_readings()

    # Start by setting the latch so we can see when it unlatches
    # This overrides the setting in the config
    encoders.latch(*initial_readings, STICKINESS)
    print(initial_readings)
    # time.sleep(2)

    print("Loading stations data...")
    stations = database.Load_Stations(STATIONS_JSON)
    print("Building city map...")
    cities = database.build_map(stations)
    print(cities)

    # # encoder_offsets = database.Load_Calibration()

    # Start reading the encoders continuosly in background
    asyncio.create_task(reader(encoders))

    # Display the encoder values periodically
    while True:
        start_t = time.monotonic()
        readings = encoders.get_readings()
        city_list = await get_cities(*readings, cities, FUZZINESS)
        # If we find a some cities in the area, latch on to the first one
        # in the list
        if city_list:
            encoders.latch(*readings)
            print(f"Found: {city_list[0]}")
        await asyncio.sleep(POLLING_SEC)
        elapst_t = time.monotonic() - start_t
        print(f"Coords: {readings} Latched: {encoders.is_latched()} t={elapst_t:.1f}")


if __name__ == "__main__":
    asyncio.run(main())
