"""
Test reading the encoders as a background task asynchronously
"""

import asyncio
import pytest

pytest.importorskip("spidev", reason="Requires SPI hardware")

from radioglobe.positional_encoders import PositionalEncoders


async def main():
    # Initialise encoders
    ps = PositionalEncoders()

    # Start reading in background and wait for the first real SPI value
    # before zeroing — zeroing on uninitialised defaults gives wrong offsets
    ps.start()
    await ps.updated.wait()
    ps.updated.clear()

    # Note the globe should be set to the origin when starting
    ps.zero()
    initial_readings = ps.get_readings()

    # Latch immediately so we can see when it unlatches on first movement
    ps.latch(*initial_readings, 1)
    print(initial_readings)

    # Display the encoder values on each update
    while True:
        await ps.updated.wait()
        ps.updated.clear()
        readings = ps.get_readings()
        print(f"Coords: {readings} Latched: {ps.is_latched()}")


if __name__ == "__main__":
    asyncio.run(main())
