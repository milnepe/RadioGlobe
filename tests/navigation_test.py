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
        self.nav.state.jog_idx = 0
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
        self.nav.state.jog_idx = 0
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


class TestNavigatorSwitchMode(unittest.TestCase):
    def test_station_to_city_recomputes_jog_idx(self):
        nav = make_navigator()
        nav.state.mode = MODE_STATION
        nav.state.cities = ["London,GB", "Paris,FR"]
        nav.state.city = "Paris,FR"
        nav.switch_mode()
        self.assertEqual(nav.state.mode, MODE_CITY)
        self.assertEqual(nav.state.jog_idx, 1)

    def test_falls_back_to_zero_if_current_not_in_items(self):
        nav = make_navigator()
        nav.state.mode = MODE_STATION
        nav.state.cities = ["London,GB"]
        nav.state.city = "NotInList,XX"
        nav.switch_mode()
        self.assertEqual(nav.state.jog_idx, 0)


class TestNavigatorRemoveFailedStation(unittest.TestCase):
    def test_removes_current_and_advances(self):
        nav = make_navigator()
        nav.state.stations = [("A", "urlA"), ("B", "urlB")]
        nav.state.jog_idx = 0
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


if __name__ == "__main__":
    unittest.main()
