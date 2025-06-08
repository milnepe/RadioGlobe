import asyncio
# import spidev

from apositional_encoders import EncoderReader, monitor_encoders
# # Example encoder read function (replace with your encoder's read protocol)
# def read_encoder(spi):
#     # For example, read 2 bytes from the encoder
#     # Dummy example: send 0xFFFF and get back a 16-bit position value
#     resp = spi.xfer2([0xFF, 0xFF])
#     value = ((resp[0] << 8) | resp[1]) & 0x3FFF  # 14-bit value
#     return value

# class EncoderReader:
#     def __init__(self, lat_spi_bus, lat_spi_device, lon_spi_bus, lon_spi_device):
#         # Setup SPI for latitude encoder
#         self.lat_spi = spidev.SpiDev()
#         self.lat_spi.open(lat_spi_bus, lat_spi_device)
#         # self.lat_spi.max_speed_hz = 1000000  # Adjust as needed
#         self.lat_spi.max_speed_hz = 5000  # Adjust as needed

#         # Setup SPI for longitude encoder
#         self.lon_spi = spidev.SpiDev()
#         self.lon_spi.open(lon_spi_bus, lon_spi_device)
#         # self.lon_spi.max_speed_hz = 1000000  # Adjust as needed
#         self.lat_spi.max_speed_hz = 5000  # Adjust as needed

#         # State
#         self.last_lat = None
#         self.last_lon = None

#     def read_lat(self):
#         return read_encoder(self.lat_spi)

#     def read_lon(self):
#         return read_encoder(self.lon_spi)

#     def close(self):
#         self.lat_spi.close()
#         self.lon_spi.close()

# async def monitor_encoders(reader: EncoderReader, poll_interval=0.01):
#     """Async generator that yields (lat, lon) whenever values change."""
#     reader.last_lat = reader.read_lat()
#     reader.last_lon = reader.read_lon()
#     yield (reader.last_lat, reader.last_lon)

#     while True:
#         await asyncio.sleep(poll_interval)

#         lat = reader.read_lat()
#         lon = reader.read_lon()

#         if lat != reader.last_lat or lon != reader.last_lon:
#             reader.last_lat = lat
#             reader.last_lon = lon
#             yield (lat, lon)


# Example consumer coroutine
async def main():
    reader = EncoderReader(
        lat_spi_bus=0, lat_spi_device=0, lon_spi_bus=0, lon_spi_device=1
    )

    try:
        async for lat, lon in monitor_encoders(reader):
            print(f"Lat: {lat}, Lon: {lon}")
    finally:
        reader.close()


if __name__ == "__main__":
    asyncio.run(main())
