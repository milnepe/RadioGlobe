import asyncio
import database

# from coordinates import Coordinate
from radio_config import STATIONS_JSON

from apositional_encoders import Positional_Encoders, monitor_encoders


async def some_process(lat, lon, fuzziness=5):
    print("Starting some process...")
    # search_area = database.look_around((lat, lon), fuzziness=fuzziness)
    await asyncio.sleep(1)  # Simulate some work
    # return search_area


# Example consumer coroutine
async def main():
    # STICKINESS = 3  # Example stickiness value, adjust as needed
    print("Initializing positional encoders...")
    reader = Positional_Encoders()

    # stations_data = database.Load_Stations(STATIONS_JSON)
    # city_map = database.build_map(stations_data)
    # print(city_map)
    # # encoder_offsets = database.Load_Calibration()

    try:
        async for lat, lon in monitor_encoders(reader):
            print(f"Lat: {lat}, Lon: {lon}")
            area = await some_process(lat, lon)
            # print(f"Search area: {area}")
            # location_name, latitude, longitude, stations_list, url_list = (
            # database.get_found_stations(area, city_map, stations_data)
            # )
        # if location_name != "":
        #     reader.latch(latitude, longitude, stickiness=STICKINESS)
        #     print("Latched...")
    except Exception as e:
        print(f"An error occurred: {e}")


if __name__ == "__main__":
    asyncio.run(main())
