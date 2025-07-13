import unittest
from radioglobe.database import get_stations_by_city


class TestGetStationsByCity(unittest.TestCase):
    def setUp(self):
        self.sample_stations = {
            "Mersin,TU": {
                "coords": {"n": 36.8121, "e": 34.6415},
                "urls": [
                    {"name": "Radyo Lk", "url": "https://radyo.yayin.com.tr:4006/;"},
                    {
                        "name": "Mek Fm 95.5",
                        "url": "http://sunucu2.radyolarburada.com:8000/;stream.mp3",
                    },
                ],
            },
            "EmptyCity,TU": {"coords": {"n": 0, "e": 0}, "urls": []},
            "NoUrlsCity,TU": {
                "coords": {"n": 1, "e": 1}
                # no "urls" key
            },
        }

    def test_existing_city_with_stations(self):
        expected = [
            ("Radyo Lk", "https://radyo.yayin.com.tr:4006/;"),
            ("Mek Fm 95.5", "http://sunucu2.radyolarburada.com:8000/;stream.mp3"),
        ]
        result = get_stations_by_city(self.sample_stations, "Mersin,TU")
        self.assertEqual(result, expected)

    def test_existing_city_with_empty_urls(self):
        result = get_stations_by_city(self.sample_stations, "EmptyCity,TU")
        self.assertEqual(result, [])

    def test_existing_city_without_urls_key(self):
        result = get_stations_by_city(self.sample_stations, "NoUrlsCity,TU")
        self.assertEqual(result, [])

    def test_city_not_in_data(self):
        result = get_stations_by_city(self.sample_stations, "UnknownCity,TU")
        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()
