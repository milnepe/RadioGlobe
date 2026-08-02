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
