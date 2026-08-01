import unittest
from radioglobe.app_state import AppState


class TestAppStateIsComplete(unittest.TestCase):
    def test_neither_set(self):
        self.assertFalse(AppState().is_complete())

    def test_city_only(self):
        self.assertFalse(AppState(city="London,GB").is_complete())

    def test_station_only(self):
        self.assertFalse(AppState(station=("Name", "url")).is_complete())

    def test_both_set(self):
        self.assertTrue(AppState(city="London,GB", station=("Name", "url")).is_complete())


class TestAppStateSelectStation(unittest.TestCase):
    def setUp(self):
        self.stations = [
            ("Radyo Lk", "https://radyo.yayin.com.tr:4006/;"),
            ("Mek Fm 95.5", "http://sunucu2.radyolarburada.com:8000/;stream.mp3"),
        ]

    def test_selects_first_station(self):
        state = AppState()
        result = state.select_station(self.stations)
        self.assertTrue(result)
        self.assertEqual(state.station, self.stations[0])
        self.assertEqual(state.stations, self.stations)

    def test_empty_list_clears_station(self):
        state = AppState(station=("Old", "url"))
        result = state.select_station([])
        self.assertFalse(result)
        self.assertIsNone(state.station)
        self.assertEqual(state.stations, [])

    def test_resets_station_idx(self):
        state = AppState(station_idx=5)
        state.select_station(self.stations)
        self.assertEqual(state.station_idx, 0)


if __name__ == "__main__":
    unittest.main()
