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


if __name__ == "__main__":
    unittest.main()
