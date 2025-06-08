import asyncio
import spidev

ENCODER_RESOLUTION = 1024  # 10 bits for each axis, so 1024 positions per axis


# Example encoder read function (replace with your encoder's read protocol)
def read_encoder(spi):
    # For example, read 2 bytes from the encoder
    # Dummy example: send 0xFFFF and get back a 16-bit position value
    resp = spi.xfer2([0xFF, 0xFF])
    value = ((resp[0] << 8) | resp[1]) & 0x3FFF  # 14-bit value
    return value


class EncoderReader:
    def __init__(self, lat_spi_bus, lat_spi_device, lon_spi_bus, lon_spi_device):
        # Setup SPI for latitude encoder
        self.lat_spi = spidev.SpiDev()
        self.lat_spi.open(lat_spi_bus, lat_spi_device)
        # self.lat_spi.max_speed_hz = 1000000  # Adjust as needed
        self.lat_spi.max_speed_hz = 5000  # Adjust as needed
        self.lat_spi.mode = 1

        # Setup SPI for longitude encoder
        self.lon_spi = spidev.SpiDev()
        self.lon_spi.open(lon_spi_bus, lon_spi_device)
        # self.lon_spi.max_speed_hz = 1000000  # Adjust as needed
        self.lon_spi.max_speed_hz = 5000  # Adjust as needed
        self.lon_spi.mode = 1

        # State
        self.last_lat = 0
        self.last_lon = 0

        # Offsets for lat/lon encoders
        self.lat_offset = 0
        self.lon_offset = 0

    def read_lat(self):
        return read_encoder(self.lat_spi)

    def read_lon(self):
        return read_encoder(self.lon_spi)

    def close(self):
        self.lat_spi.close()
        self.lon_spi.close()


async def monitor_encoders(reader: EncoderReader, poll_interval=0.2):
    """Async generator that yields (lat, lon) whenever values change."""
    reader.last_lat = (ENCODER_RESOLUTION // 2) - reader.last_lat
    reader.last_lon = (ENCODER_RESOLUTION // 2) - reader.last_lon
    yield (reader.last_lat, reader.last_lon)

    while True:
        await asyncio.sleep(poll_interval)

        lat = (reader.read_lat() + reader.lat_offset) % ENCODER_RESOLUTION
        lon = (reader.read_lon() + reader.lon_offset) % ENCODER_RESOLUTION

        if (
            lat >= reader.last_lat + 60
            or lat <= reader.last_lat - 60
            or lon >= reader.last_lon + 60
            or lon <= reader.last_lon - 60
        ):
            reader.last_lat = lat
            reader.last_lon = lon
            yield (lat, lon)
