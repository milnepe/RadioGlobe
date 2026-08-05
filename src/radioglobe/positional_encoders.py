import asyncio
import logging
from typing import Optional

import spidev  # type: ignore

from .database import _ENCODER_RESOLUTION


class PositionalEncoders:
    def __init__(self, latitude_offset: int = 0, longitude_offset: int = 0) -> None:
        self.latch_stickiness = None
        self.latitude = 0
        self.longitude = 0
        self.latitude_offset = latitude_offset
        self.longitude_offset = longitude_offset
        self.updated = asyncio.Event()
        self.spi = None

        # Used to safely stop the task
        self._task = None

    def zero(self) -> list:
        self.latitude_offset = (_ENCODER_RESOLUTION // 2) - self.latitude
        self.longitude_offset = (_ENCODER_RESOLUTION // 2) - self.longitude
        return [self.latitude_offset, self.longitude_offset]

    def reset_latch(self) -> None:
        """Unlock the stickiness so the main loop can re-latch to a new position."""
        self.latch_stickiness = None

    def get_readings(self) -> tuple:
        return (self.latitude + self.latitude_offset) % _ENCODER_RESOLUTION, (
            self.longitude + self.longitude_offset
        ) % _ENCODER_RESOLUTION

    def latch(self, latitude: int, longitude: int, stickiness: int) -> None:
        self.latch_stickiness = stickiness
        self.latitude = (latitude - self.latitude_offset) % _ENCODER_RESOLUTION
        self.longitude = (longitude - self.longitude_offset) % _ENCODER_RESOLUTION

    def is_latched(self) -> bool:
        return self.latch_stickiness is not None

    def get_calibration(self) -> dict:
        """Return the current position/calibration as plain data for persistence."""
        return {
            "lat": self.latitude,
            "lon": self.longitude,
            "lat_offset": self.latitude_offset,
            "lon_offset": self.longitude_offset,
        }

    def restore_calibration(self, state: dict) -> None:
        """Restore position/calibration from a dict produced by get_calibration().

        Also marks the encoders as latched, since a restored position always
        represents a previously-latched city.
        """
        self.latitude = state.get("lat")
        self.longitude = state.get("lon")
        self.latitude_offset = state.get("lat_offset")
        self.longitude_offset = state.get("lon_offset")
        self.latch_stickiness = True

    def check_parity(self, reading: int) -> bool:
        reading_without_parity_bit = reading >> 1
        parity_bit = reading & 0b1

        computed_parity = 0
        while reading_without_parity_bit:
            computed_parity ^= reading_without_parity_bit & 0b1
            reading_without_parity_bit >>= 1

        return parity_bit == computed_parity

    def read_spi(self) -> Optional[list]:
        BUS = 0
        readings = []

        for device in [0, 1]:
            self.spi.open(BUS, device)
            self.spi.max_speed_hz = 1000000
            self.spi.mode = 1
            reading = self.spi.readbytes(2)
            self.spi.close()

            raw_reading = reading[0] << 8 | reading[1]

            if self.check_parity(raw_reading):
                readings.append(raw_reading >> 6)
            else:
                logging.debug(f"SPI parity check failed for encoder {device} (raw={raw_reading:#06x})")
                return None

        return readings

    # Number of consecutive out-of-band readings required before unlatching.
    # Filters single-sample sensor noise (the EMS22A50 datasheet specifies
    # ~0.12 deg RMS output transition noise) from genuine sustained movement,
    # without having to raise STICKINESS itself.
    UNLATCH_CONFIRM_THRESHOLD = 2

    async def run_encoder(self) -> None:
        unlatch_confirm_count = 0
        while self._task:
            readings = self.read_spi()

            if readings:
                readings[0] = _ENCODER_RESOLUTION - readings[0]

                if self.latch_stickiness is None:
                    self.latitude = readings[0]
                    self.longitude = readings[1]
                    self.updated.set()
                else:
                    lat_difference = abs(self.latitude - readings[0]) % _ENCODER_RESOLUTION
                    lon_difference = abs(self.longitude - readings[1]) % _ENCODER_RESOLUTION

                    if (
                        lat_difference > self.latch_stickiness
                        or lon_difference > self.latch_stickiness
                    ):
                        unlatch_confirm_count += 1
                        if unlatch_confirm_count >= self.UNLATCH_CONFIRM_THRESHOLD:
                            self.latch_stickiness = None
                            self.updated.set()
                            unlatch_confirm_count = 0
                            continue
                    else:
                        unlatch_confirm_count = 0

            await asyncio.sleep(0.05)

    def start(self) -> None:
        self.spi = spidev.SpiDev()
        self._task = asyncio.create_task(self.run_encoder())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
