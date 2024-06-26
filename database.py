import json
import os.path
import logging
from radio_config import DATADIR, STATIONS_JSON, ENCODER_RESOLUTION, OFFSETS_JSON


os.makedirs(DATADIR, exist_ok=True)


def Load_Stations(stations_json: str) -> dict:
    """Return dictionary of stations from stations file"""
    stations_dict = {}
    try:
        with open(stations_json, "r", encoding="utf8") as stations_file:
            stations_dict = json.load(stations_file)
        logging.info(f"Loaded stations from {stations_json}")
    except FileNotFoundError:
        logging.info(f"{stations_json} not found")

    return stations_dict


def build_map(stations_data: dict) -> dict:
    """Map each encoder location to list of cities (Stations DB key) for that location.
    Each location can have one or more cites eg:
    {(609, 178): ['Riverside,US-CA', 'San Bernardino,US-CA'], ...}"""
    cities_index = {}
    for location in stations_data:
        # Turn the coordinates into indexes for the map.  We need to shift all the numbers to make everything positive
        latitude = round((stations_data[location]["coords"]["n"] + 180) * ENCODER_RESOLUTION / 360)
        longitude = round((stations_data[location]["coords"]["e"] + 180) * ENCODER_RESOLUTION / 360)
        logging.debug(f"{location}, {latitude}, {longitude}")

        location_list = []
        city_coords = (latitude, longitude)
        if city_coords not in cities_index:
            location_list.append(location)
            cities_index[city_coords] = location_list
        else:
            cities_index[city_coords].append(location)

    return cities_index


def look_around(origin: tuple, fuzziness: int) -> list:
    """Returns a search area list of lat, long pairs arround for the origin coords.
    Fuzziness increases the area surrounding the origin.

    For example:
    fuzziness 2 returns the surrounding 9 locations,
    fuzziness 3 returns the surrounding 25 locations"""

    search_area = []
    latitude, longitude = origin

    # Work out how big the perimeter is for each layer out from the origin
    ODD_NUMBERS = [((i * 2) + 1) for i in range(0, fuzziness)]

    # With each 'layer' of fuzziness we need a starting point.  70% of people are right-eye dominant and
    # the globe is likely to be below the user, so go down and left first then scan horizontally, moving up
    for layer in range(0, fuzziness):
        for y in range(0, ODD_NUMBERS[layer]):
            for x in range(0, ODD_NUMBERS[layer]):
                coord_x = (latitude + x - (ODD_NUMBERS[layer] // 2)) % ENCODER_RESOLUTION
                coord_y = (longitude + y - (ODD_NUMBERS[layer] // 2)) % ENCODER_RESOLUTION
                exp_coords = (coord_x, coord_y)
                if exp_coords not in search_area:
                    search_area.append(exp_coords)

    logging.debug(f"Search area: {search_area}")
    return search_area


def get_found_stations(search_area: list, city_map: dict, stations_data: dict) -> tuple:
    """Get station info found within search area
    Can return more than one locations worth of urls depending on fuzziness"""
    location = ""
    location_name = ""
    stations_list = []
    url_list = []
    # Check the search area.  Saving the first location name encountered
    # and all radio stations in the area, in order encountered
    for coords in search_area:
        coords_lat, coords_long = coords
        if coords in city_map:
            cities = city_map[coords]
            logging.debug(f"Ref: {coords}, {cities}")
            for city in cities:
                logging.debug(f"City: {city}")

                if location_name == "":
                    location_name = city

                for station in stations_data[city]["urls"]:
                    station_name = station["name"]
                    if station_name not in stations_list:
                        stations_list.append(station_name)
                        url_list.append(station["url"])

        # Provide 'helper' coordinates
        latitude = round((360 * coords_lat / ENCODER_RESOLUTION - 180), 2)
        longitude = round((360 * coords_long / ENCODER_RESOLUTION - 180), 2)

    logging.debug(f"Found stations: {location_name}, {latitude}, {longitude}, {stations_list}")
    return location_name, latitude, longitude, stations_list, url_list


def Save_Calibration(latitude: int, longitude: int):
    offsets = [latitude, longitude]
    with open(OFFSETS_JSON, "w") as offsets_file:
        offsets_file.write(json.dumps(offsets))
        logging.debug(f"{OFFSETS_JSON} saved...")


def Load_Calibration():
    try:
        with open(OFFSETS_JSON, "r") as offsets_file:
            offsets = json.load(offsets_file)
    except Exception:
        offsets = [0, 0]

    logging.debug(f"Setting offsets to: {offsets}")

    return offsets


if __name__ == "__main__":
    format = "%(asctime)s: %(message)s"
    logging.basicConfig(format=format, level=logging.INFO, datefmt="%H:%M:%S")
    logging.getLogger().setLevel(logging.DEBUG)

    stations_data = Load_Stations(STATIONS_JSON)
    city_map = build_map(stations_data)
    for k, v in city_map.items():
        if len(v) > 1:
            logging.debug(f"{k}, {v}")

    search_area = look_around((609, 178), 2)

    result = get_found_stations(search_area, city_map, stations_data)
