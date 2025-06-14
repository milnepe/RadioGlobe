import asyncio
import database

# from coordinates import Coordinate
from radio_config import STATIONS_JSON

from positional_encoders_async import Positional_Encoders, monitor_encoders


async def some_process(lat, lon, city_map, stations_data, fuzziness=2):
    print("Starting some process...")
    search_area = database.look_around((lat, lon), fuzziness=fuzziness)
    # print(f"Search area for ({lat}, {lon}): {search_area}")
    stations = database.get_found_stations(search_area, city_map, stations_data)
    # print(f"Found stations: {stations}")
    await asyncio.sleep(2)  # Simulate some work
    return stations


# Example consumer coroutine
async def main():
    # STICKINESS = 3  # Example stickiness value, adjust as needed
    print("Initializing positional encoders...")
    reader = Positional_Encoders()

    print("Loading stations data...")
    stations = database.Load_Stations(STATIONS_JSON)
    print("Building city map...")
    cities = database.build_map(stations)
    print(cities)

    # # encoder_offsets = database.Load_Calibration()

    try:
        async for lat, lon in monitor_encoders(reader):
            print(f"Lat: {lat}, Lon: {lon}")
            result = await some_process(lat, lon, cities, stations, 6)
            # if cities:
            #     break

            # if location_name != "":
            #     reader.latch(latitude, longitude, stickiness=STICKINESS)
            #     print("Latched...")
    except Exception as e:
        print(f"An error occurred: {e}")


if __name__ == "__main__":
    asyncio.run(main())
