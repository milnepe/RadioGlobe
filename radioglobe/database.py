import json
import logging

from .coordinates import Coordinate

_ENCODER_RESOLUTION = 1024


def load_stations(stations_json: str) -> dict:
    """
    Return a dictionary of stations from stations file
    """
    stations_dict = {}
    try:
        with open(stations_json, "r", encoding="utf8") as stations_file:
            stations_dict = json.load(stations_file)
        logging.info(f"Loaded stations from {stations_json}")
    except FileNotFoundError:
        logging.info(f"{stations_json} not found")

    return stations_dict


def build_cities_index(stations_data: dict) -> dict:
    """
    Builds an index of cities for each grid square of the globe
    Each index can have one or more cites eg:
    {(609, 178): ['Riverside,US-CA', 'San Bernardino,US-CA'], ...}
    """
    cities_index = {}
    for location in stations_data:
        # Turn the coordinates into indexes for the map.  We need to shift all the numbers to make everything positive
        latitude = round((stations_data[location]["coords"]["n"] + 180) * _ENCODER_RESOLUTION / 360)
        longitude = round((stations_data[location]["coords"]["e"] + 180) * _ENCODER_RESOLUTION / 360)
        # logging.debug(f"{location}, {latitude}, {longitude}")

        city_coords = (latitude, longitude)
        cities_index.setdefault(city_coords, []).append(location)

    logging.info("Built cities index...")
    return cities_index


def build_look_around_offsets(fuzziness: int) -> list[tuple[int, int]]:
    """Pre-compute the (dx, dy) offsets for a given fuzziness.

    The offset pattern is fixed for a given fuzziness value, so this only
    needs to be called once at startup. Pass the result to look_around.

    For example:
    fuzziness 2 returns 9 unique offsets,
    fuzziness 3 returns 25 unique offsets"""

    offsets: list[tuple[int, int]] = []
    ODD_NUMBERS = [(i * 2 + 1) for i in range(fuzziness)]

    for layer in range(fuzziness):
        for y in range(ODD_NUMBERS[layer]):
            for x in range(ODD_NUMBERS[layer]):
                dx = x - ODD_NUMBERS[layer] // 2
                dy = y - ODD_NUMBERS[layer] // 2
                if (dx, dy) not in offsets:
                    offsets.append((dx, dy))

    logging.info(f"Built look-around offsets: fuzziness={fuzziness}, {len(offsets)} offsets")
    return offsets


def look_around(origin: tuple, offsets: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Returns the search area around origin by applying pre-computed offsets.

    Build offsets once at startup with build_look_around_offsets(fuzziness)."""

    latitude, longitude = origin
    return [
        ((latitude + dx) % _ENCODER_RESOLUTION, (longitude + dy) % _ENCODER_RESOLUTION)
        for dx, dy in offsets
    ]


def find_cities_near(origin: tuple, offsets: list[tuple[int, int]], cities_index: dict) -> list:
    """Return all cities within the search area around origin, ordered closest-first.

    Combines look_around and city index lookup into a single pass, avoiding the
    intermediate list of grid coordinates. Proximity order is preserved because
    offsets are built innermost-first by build_look_around_offsets."""
    lat, lon = origin
    seen: set = set()
    cities = []
    for dx, dy in offsets:
        coord = ((lat + dx) % _ENCODER_RESOLUTION, (lon + dy) % _ENCODER_RESOLUTION)
        if coord in cities_index:
            for city in cities_index[coord]:
                if city not in seen:
                    seen.add(city)
                    cities.append(city)
    return cities


def get_stations_by_city(stations: dict, city_country: str) -> list:
    """Return all the stations for the given city"""
    station_info = stations.get(city_country)
    if not station_info or "urls" not in station_info:
        return []

    return [(entry["name"], entry["url"]) for entry in station_info["urls"]]


def get_coords_by_city(stations: dict, city: str) -> Coordinate:
    """Return a Coordinate for the given city string.

    Raises KeyError if the city isn't present in the stations data —
    callers that can encounter a stale/removed city (e.g. from a cached
    state file) must catch this explicitly rather than relying on a
    silent fallback.
    """
    entry = stations.get(city)
    if entry is None:
        raise KeyError(f"City not found in stations data: {city!r}")
    return Coordinate(entry["coords"]["n"], entry["coords"]["e"])


def match_saved_station(saved_name, stations: list) -> tuple:
    """Find the saved station by name in the refreshed stations list.

    Falls back to the first station (or None) if the saved name is no
    longer present, e.g. after a stations.json update.
    """
    match = next((s for s in stations if s[0] == saved_name), None)
    if match:
        return match, stations.index(match)
    return (stations[0] if stations else None), 0


def get_found_cities(search_area: list, city_map: dict) -> list:
    """
    Get station info found within search area
    Can return more than one locations worth of urls depending on fuzziness
    """
    cities = []
    # Check the search area.  Saving the first location name encountered
    # and all radio stations in the area, in order encountered
    for coords in search_area:
        if coords in city_map:
            for city in city_map[coords]:
                # logging.debug(f"Coords: {coords}, City: {city}")
                if city not in cities:
                    cities.append(city)
    # logging.debug(f"Cities found: {cities}")
    return cities


def get_stations_info(city, stations) -> list[tuple | None]:
    """
    Return a list of station name, url pairs for a given city,country
    """
    for key in stations:
        if city.lower() == key.lower():  # Exact match, case-insensitive
            urls = stations[key].get("urls", [])
            return [
                (entry["name"], entry["url"])
                for entry in urls
                if "name" in entry and "url" in entry
            ]
    return []  # No match found
