import asyncio
import spidev

ENCODER_RESOLUTION = 1024  # 10 bits for each axis, so 1024 positions per axis


class Positional_Encoders:

    def __init__(self, latitude_offset=0, longitude_offset=0):
        self.latch_stickiness = None
        self.latitude = 0
        self.longitude = 0
        self.latitude_offset = latitude_offset
        self.longitude_offset = longitude_offset

        # Enable SPI
        self.spi = spidev.SpiDev()

    def zero(self):
        self.latitude_offset = (ENCODER_RESOLUTION // 2) - self.latitude
        self.longitude_offset = (ENCODER_RESOLUTION // 2) - self.longitude
        return [self.latitude_offset, self.longitude_offset]

    def get_readings(self) -> tuple:
        return (self.latitude + self.latitude_offset) % ENCODER_RESOLUTION, \
               (self.longitude + self.longitude_offset) % ENCODER_RESOLUTION

    def latch(self, latitude: int, longitude: int, stickiness: int):
        self.latch_stickiness = stickiness
        self.latitude = (latitude - self.latitude_offset) % ENCODER_RESOLUTION
        self.longitude = (longitude - self.longitude_offset) % ENCODER_RESOLUTION

    def is_latched(self):
        return self.latch_stickiness is not None

    def check_parity(self, reading: int):
        reading_without_parity_bit = reading >> 1
        parity_bit = reading & 0b1

        computed_parity = 0
        while reading_without_parity_bit:
            computed_parity ^= (reading_without_parity_bit & 0b1)
            reading_without_parity_bit >>= 1

        return parity_bit == computed_parity

    def read_spi(self):
        BUS = 0
        readings = []

        for device in [0, 1]:
            self.spi.open(BUS, device)
            self.spi.max_speed_hz = 5000
            self.spi.mode = 1
            reading = self.spi.readbytes(2)
            self.spi.close()

            raw_reading = (reading[0] << 8) | reading[1]

            if self.check_parity(raw_reading):
                readings.append(raw_reading >> 6)
            else:
                return None

        return readings

    async def run(self):
        print("Starting positional encoders...")
        while True:
            readings = self.read_spi()
            if readings:
                readings[0] = ENCODER_RESOLUTION - readings[0]  # invert latitude
                if self.latch_stickiness is None:
                    self.latitude = readings[0]
                    self.longitude = readings[1]
                else:
                    lat_difference = abs(self.latitude - readings[0]) % ENCODER_RESOLUTION
                    lon_difference = abs(self.longitude - readings[1]) % ENCODER_RESOLUTION

                    if lat_difference > self.latch_stickiness or lon_difference > self.latch_stickiness:
                        self.latch_stickiness = None
                        continue
            await asyncio.sleep(0.2)
