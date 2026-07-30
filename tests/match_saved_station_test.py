import unittest
from radioglobe.database import match_saved_station


class TestMatchSavedStation(unittest.TestCase):
    def setUp(self):
        self.stations = [
            ("Radyo Lk", "https://radyo.yayin.com.tr:4006/;"),
            ("Mek Fm 95.5", "http://sunucu2.radyolarburada.com:8000/;stream.mp3"),
        ]

    def test_saved_name_found(self):
        station, jog_idx = match_saved_station("Mek Fm 95.5", self.stations)
        self.assertEqual(station, self.stations[1])
        self.assertEqual(jog_idx, 1)

    def test_saved_name_not_found_falls_back_to_first(self):
        station, jog_idx = match_saved_station("Unknown Station", self.stations)
        self.assertEqual(station, self.stations[0])
        self.assertEqual(jog_idx, 0)

    def test_no_saved_name_falls_back_to_first(self):
        station, jog_idx = match_saved_station(None, self.stations)
        self.assertEqual(station, self.stations[0])
        self.assertEqual(jog_idx, 0)

    def test_empty_stations_list(self):
        station, jog_idx = match_saved_station("Anything", [])
        self.assertIsNone(station)
        self.assertEqual(jog_idx, 0)


if __name__ == "__main__":
    unittest.main()
