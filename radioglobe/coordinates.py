import logging

ROUNDING = 2


class Coordinate:
    """Global Coordinate
    Lat / Long equality to ROUNDING decimals"""

    def __init__(self, lat=0.0, lon=0.0):
        self.lat = lat
        self.lon = lon

    def __eq__(self, other):
        if not isinstance(other, Coordinate):
            return NotImplemented
        return round(self.lat, ROUNDING) == round(other.lat, ROUNDING) and round(
            self.lon, ROUNDING
        ) == round(other.lon, ROUNDING)

    def __repr__(self):
        return f"Coordinate({self.lat}, {self.lon})"

    def __str__(self):
        ns = "NS"[self.lat < 0]
        ew = "EW"[self.lon < 0]
        return f"{abs(self.lat):.2f}{ns}, {abs(self.lon):.2f}{ew}"


if __name__ == "__main__":
    origin = Coordinate()
    logging.debug(f"Origin: {origin.lat}, {origin.lon}")
    logging.debug(f"Origin: {origin}")

    greenwich = Coordinate(0.0001, 0.0001)
    logging.debug(f"Greenwich: {greenwich.lat}, {greenwich.lon}")
    logging.debug(f"Greenwich: {greenwich}")

    if result := origin == greenwich:  # result is None if false
        logging.debug(f"Origin equals Greenwich: {result}")
    else:
        logging.debug("False")

    kolkata = Coordinate(22.54, 88.34)
    logging.debug(f"Kolkata: {kolkata.lat}, {kolkata.lon}")
    logging.debug(f"Kalkata: {kolkata}")

    logging.debug("""Akron,US-OH": {
                "coords": {
                            "n": 41.0798,
                            "e": -81.5219""")

    akron = Coordinate(41.0798, -81.5219)
    logging.debug(f"Akron: {akron.lat}, {akron.lon}")
    logging.debug(f"Akron: {akron}")

    logging.debug(""""Den Haag,NL": {
        "coords": {
          "n": 52.08,
          "e": 4.27
        }""")
    den_haag = Coordinate(52.08, 4.27)
    logging.debug(f"Den Haag: {den_haag.lat}, {den_haag.lon}")
    logging.debug(den_haag)
