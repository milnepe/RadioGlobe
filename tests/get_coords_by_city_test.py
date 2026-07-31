import unittest
from radioglobe.coordinates import Coordinate
from radioglobe.database import get_coords_by_city


class TestGetCoordsByCity(unittest.TestCase):
    def setUp(self):
        self.sample_stations = {
            "London,GB": {"coords": {"n": 51.5074, "e": -0.1278}, "urls": []},
        }

    def test_existing_city(self):
        result = get_coords_by_city(self.sample_stations, "London,GB")
        self.assertEqual(result, Coordinate(51.5074, -0.1278))

    def test_city_not_in_data(self):
        with self.assertRaises(KeyError):
            get_coords_by_city(self.sample_stations, "UnknownCity,TU")


if __name__ == "__main__":
    unittest.main()
