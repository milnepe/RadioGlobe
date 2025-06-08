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
    print(f"Origin: {origin.lat}, {origin.lon}")
    print(f"Origin: {origin}")

    greenwich = Coordinate(0.0001, 0.0001)
    print(f"Greenwich: {greenwich.lat}, {greenwich.lon}")
    print(f"Greenwich: {greenwich}")

    if result := origin == greenwich:  # result is None if false
        print(f"Origin equals Greenwich: {result}")
    else:
        print("False")

    kolkata = Coordinate(22.54, 88.34)
    print(f"Kolkata: {kolkata.lat}, {kolkata.lon}")
    print(f"Kalkata: {kolkata}")

    print("""Akron,US-OH": {
                "coords": {
                            "n": 41.0798,
                            "e": -81.5219""")

    akron = Coordinate(41.0798, -81.5219)
    print(f"Akron: {akron.lat}, {akron.lon}")
    print(f"Akron: {akron}")

    print(""""Den Haag,NL": {
        "coords": {
          "n": 52.08,
          "e": 4.27
        }""")
    den_haag = Coordinate(52.08, 4.27)
    print(f"Den Haag: {den_haag.lat}, {den_haag.lon}")
    print(den_haag)
