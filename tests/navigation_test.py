import json
import os
import tempfile
import unittest

from radioglobe.constants import MODE_CITY, MODE_STATION
from radioglobe.coordinates import Coordinate
from radioglobe.database import build_cities_index
from radioglobe.navigation import Navigator


def make_navigator(stations_info=None):
    """Build a Navigator without touching the real (12k-entry) stations file."""
    nav = Navigator(stations_json="/nonexistent/stations.json")
    if stations_info is not None:
        nav.stations_info = stations_info
        nav.cities_info = build_cities_index(stations_info)
    return nav


class TestNavigatorConstruction(unittest.TestCase):
    def test_missing_stations_file_yields_empty_state(self):
        nav = make_navigator()
        self.assertEqual(nav.stations_info, {})
        self.assertEqual(nav.cities_info, {})
        self.assertIsNone(nav.state.city)


class TestNavigatorNextStation(unittest.TestCase):
    def setUp(self):
        self.nav = make_navigator()
        self.nav.state.stations = [("A", "urlA"), ("B", "urlB"), ("C", "urlC")]
        self.nav.state.station_idx = 0
        self.nav.state.station = self.nav.state.stations[0]

    def test_next_advances_and_wraps(self):
        self.nav.next_station(1)
        self.assertEqual(self.nav.state.station, ("B", "urlB"))
        self.nav.next_station(1)
        self.nav.next_station(1)
        self.assertEqual(self.nav.state.station, ("A", "urlA"))

    def test_previous_wraps_backward(self):
        self.nav.next_station(-1)
        self.assertEqual(self.nav.state.station, ("C", "urlC"))

    def test_no_stations_is_noop(self):
        nav = make_navigator()
        nav.next_station(1)
        self.assertIsNone(nav.state.station)


class TestNavigatorNextCity(unittest.TestCase):
    def setUp(self):
        self.nav = make_navigator()
        self.nav.state.cities = ["London,GB", "Paris,FR", "Berlin,DE"]
        self.nav.state.city_idx = 0
        self.nav.state.city = "London,GB"

    def test_next_advances_and_wraps(self):
        self.nav.next_city(1)
        self.assertEqual(self.nav.state.city, "Paris,FR")
        self.nav.next_city(1)
        self.nav.next_city(1)
        self.assertEqual(self.nav.state.city, "London,GB")

    def test_no_cities_is_noop(self):
        nav = make_navigator()
        nav.next_city(1)
        self.assertIsNone(nav.state.city)


class TestNavigatorSelectCity(unittest.TestCase):
    def setUp(self):
        self.stations = {
            "London,GB": {
                "coords": {"n": 51.5074, "e": -0.1278},
                "urls": [
                    {"name": "Station A", "url": "http://a.example/stream"},
                    {"name": "Station B", "url": "http://b.example/stream"},
                ],
            },
            "Empty City,XX": {
                "coords": {"n": 0.0, "e": 0.0},
                "urls": [],
            },
        }

    def test_no_nearby_cities_returns_false(self):
        nav = make_navigator(self.stations)
        self.assertFalse(nav.select_city())
        self.assertIsNone(nav.state.city)

    def test_latches_closest_city_and_first_station(self):
        nav = make_navigator(self.stations)
        nav.state.cities = ["London,GB"]
        self.assertTrue(nav.select_city())
        self.assertEqual(nav.state.city, "London,GB")
        self.assertEqual(nav.state.city_idx, 0)
        self.assertEqual(nav.state.station, ("Station A", "http://a.example/stream"))
        self.assertEqual(nav.state.station_idx, 0)

    def test_closest_city_with_no_stations_returns_false(self):
        nav = make_navigator(self.stations)
        nav.state.cities = ["Empty City,XX"]
        self.assertFalse(nav.select_city())
        self.assertIsNone(nav.state.station)


class TestNavigatorNextCityAndSelectStation(unittest.TestCase):
    def setUp(self):
        self.stations = {
            "London,GB": {
                "coords": {"n": 51.5074, "e": -0.1278},
                "urls": [{"name": "London FM", "url": "http://london.example/stream"}],
            },
            "Paris,FR": {
                "coords": {"n": 48.8566, "e": 2.3522},
                "urls": [{"name": "Paris FM", "url": "http://paris.example/stream"}],
            },
            "Empty City,XX": {
                "coords": {"n": 0.0, "e": 0.0},
                "urls": [],
            },
        }

    def test_advances_and_selects_new_station(self):
        nav = make_navigator(self.stations)
        nav.state.cities = ["London,GB", "Paris,FR"]
        nav.state.city_idx = 0
        nav.state.city = "London,GB"

        self.assertTrue(nav.next_city_and_select_station(1))
        self.assertEqual(nav.state.city, "Paris,FR")
        self.assertEqual(nav.state.station, ("Paris FM", "http://paris.example/stream"))

    def test_wraps_around(self):
        nav = make_navigator(self.stations)
        nav.state.cities = ["London,GB", "Paris,FR"]
        nav.state.city_idx = 0
        nav.state.city = "London,GB"

        self.assertTrue(nav.next_city_and_select_station(-1))
        self.assertEqual(nav.state.city, "Paris,FR")

    def test_new_city_with_no_stations_returns_false(self):
        nav = make_navigator(self.stations)
        nav.state.cities = ["London,GB", "Empty City,XX"]
        nav.state.city_idx = 0
        nav.state.city = "London,GB"
        nav.state.station = ("London FM", "http://london.example/stream")

        self.assertFalse(nav.next_city_and_select_station(1))
        self.assertEqual(nav.state.city, "Empty City,XX")
        self.assertIsNone(nav.state.station)


class TestNavigatorRefreshNearbyCities(unittest.TestCase):
    def test_stores_and_returns_found_cities(self):
        stations = {"London,GB": {"coords": {"n": 51.5074, "e": -0.1278}, "urls": []}}
        nav = make_navigator(stations)
        origin = next(iter(nav.cities_info.keys()))
        result = nav.refresh_nearby_cities(origin)
        self.assertEqual(result, ["London,GB"])
        self.assertEqual(nav.state.cities, ["London,GB"])


class TestNavigatorSwitchMode(unittest.TestCase):
    def test_toggles_mode_without_touching_indices(self):
        nav = make_navigator()
        nav.state.mode = MODE_STATION
        nav.state.station_idx = 3
        nav.state.city_idx = 7

        nav.switch_mode()
        self.assertEqual(nav.state.mode, MODE_CITY)
        self.assertEqual(nav.state.station_idx, 3)
        self.assertEqual(nav.state.city_idx, 7)

        nav.switch_mode()
        self.assertEqual(nav.state.mode, MODE_STATION)
        self.assertEqual(nav.state.station_idx, 3)
        self.assertEqual(nav.state.city_idx, 7)


class TestNavigatorRemoveFailedStation(unittest.TestCase):
    def test_removes_current_and_advances(self):
        nav = make_navigator()
        nav.state.stations = [("A", "urlA"), ("B", "urlB")]
        nav.state.station_idx = 0
        nav.state.station = ("A", "urlA")
        nav.remove_failed_station()
        self.assertEqual(nav.state.stations, [("B", "urlB")])
        self.assertEqual(nav.state.station, ("B", "urlB"))

    def test_clears_station_when_list_becomes_empty(self):
        nav = make_navigator()
        nav.state.stations = [("A", "urlA")]
        nav.state.station = ("A", "urlA")
        nav.remove_failed_station()
        self.assertEqual(nav.state.stations, [])
        self.assertIsNone(nav.state.station)

    def test_advances_via_station_idx_even_in_city_mode(self):
        """Regression test: remove_failed_station() must always use
        station_idx, never whatever city_idx currently holds — a stream
        failure can land while the dial is in MODE_CITY, independent of
        which mode the user is currently browsing in."""
        nav = make_navigator()
        nav.state.mode = MODE_CITY
        nav.state.city_idx = 99  # deliberately unrelated to stations list
        nav.state.stations = [("A", "urlA"), ("B", "urlB"), ("C", "urlC")]
        nav.state.station_idx = 0
        nav.state.station = ("A", "urlA")
        nav.remove_failed_station()
        self.assertEqual(nav.state.stations, [("B", "urlB"), ("C", "urlC")])
        self.assertEqual(nav.state.station, ("B", "urlB"))
        self.assertEqual(nav.state.city_idx, 99)  # untouched


class TestNavigatorCurrentCoords(unittest.TestCase):
    def test_none_when_no_city(self):
        nav = make_navigator()
        self.assertIsNone(nav.current_coords)

    def test_returns_coordinate_for_current_city(self):
        stations = {"London,GB": {"coords": {"n": 51.5074, "e": -0.1278}, "urls": []}}
        nav = make_navigator(stations)
        nav.state.city = "London,GB"
        self.assertEqual(nav.current_coords, Coordinate(51.5074, -0.1278))


class TestNavigatorFindCitiesNear(unittest.TestCase):
    def test_finds_indexed_city(self):
        stations = {"London,GB": {"coords": {"n": 51.5074, "e": -0.1278}, "urls": []}}
        nav = make_navigator(stations)
        origin = next(iter(nav.cities_info.keys()))
        self.assertIn("London,GB", nav.find_cities_near(origin))

    def test_no_match_returns_empty(self):
        nav = make_navigator()
        self.assertEqual(nav.find_cities_near((0, 0)), [])


class TestNavigatorSaveLoadState(unittest.TestCase):
    def setUp(self):
        self.stations = {
            "London,GB": {
                "coords": {"n": 51.5074, "e": -0.1278},
                "urls": [{"name": "Test FM", "url": "http://example/stream"}],
            },
        }
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.cache = os.path.join(self.tmpdir.name, "nested", "state.json")

    def test_load_state_no_file_returns_empty_dict(self):
        nav = make_navigator(self.stations)
        result = nav.load_state(self.cache)
        self.assertEqual(result, {})
        self.assertIsNone(nav.state.city)

    def test_save_creates_parent_directory_and_writes_json(self):
        nav = make_navigator(self.stations)
        nav.save_state({"lat": 512, "lon": 512, "lat_offset": 0, "lon_offset": 0}, self.cache)
        self.assertTrue(os.path.exists(self.cache))
        with open(self.cache) as f:
            written = json.load(f)
        self.assertEqual(written["lat"], 512)
        self.assertTrue(written["latch"])

    def test_save_then_load_roundtrip(self):
        saver = make_navigator(self.stations)
        saver.state.city = "London,GB"
        saver.state.city_idx = 2
        saver.state.stations = [("Test FM", "http://example/stream")]
        saver.state.station = ("Test FM", "http://example/stream")
        saver.state.station_idx = 0
        encoder_offsets = {"lat": 600, "lon": 400, "lat_offset": 10, "lon_offset": -10}
        saver.save_state(encoder_offsets, self.cache)

        loader = make_navigator(self.stations)
        result = loader.load_state(self.cache)

        self.assertEqual(result, encoder_offsets)
        self.assertEqual(loader.state.city, "London,GB")
        self.assertEqual(loader.state.station, ("Test FM", "http://example/stream"))
        self.assertEqual(loader.state.station_idx, 0)
        self.assertEqual(loader.state.city_idx, 2)

    def test_load_old_format_cache_without_split_idx_fields(self):
        """Old cache files only have a single "jog_idx" key. load_state()
        must still load cleanly, silently ignoring it and defaulting the
        new station_idx/city_idx fields to 0."""
        old_format_state = {
            "stations": [],
            "station": None,
            "cities": [],
            "city": None,
            "jog_idx": 3,
            "mode": "station",
            "lat": 1,
            "lon": 2,
            "lat_offset": 3,
            "lon_offset": 4,
            "latch": True,
        }
        os.makedirs(os.path.dirname(self.cache), exist_ok=True)
        with open(self.cache, "w") as f:
            json.dump(old_format_state, f)

        loader = make_navigator(self.stations)
        result = loader.load_state(self.cache)

        self.assertEqual(result, {"lat": 1, "lon": 2, "lat_offset": 3, "lon_offset": 4})
        self.assertEqual(loader.state.station_idx, 0)
        self.assertEqual(loader.state.city_idx, 0)

    def test_load_state_discards_stale_city_but_still_returns_encoder_offsets(self):
        saver = make_navigator(self.stations)
        saver.state.city = "London,GB"
        saver.state.station = ("Test FM", "http://example/stream")
        encoder_offsets = {"lat": 1, "lon": 2, "lat_offset": 3, "lon_offset": 4}
        saver.save_state(encoder_offsets, self.cache)

        # City no longer exists in the loader's stations data.
        loader = make_navigator({})
        result = loader.load_state(self.cache)

        self.assertEqual(result, encoder_offsets)
        self.assertIsNone(loader.state.city)
        self.assertIsNone(loader.state.station)


if __name__ == "__main__":
    unittest.main()
