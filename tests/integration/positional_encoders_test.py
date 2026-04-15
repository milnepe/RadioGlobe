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
    # Note the globe should be set to the origin when starting main
    ps.zero()
    initial_readings = ps.get_readings()

    # Start by setting the latch so we can see when it unlatches
    ps.latch(*initial_readings, 1)
    print(initial_readings)

    # Start continuous reading in background
    ps.start()

    # Display the encoder values on each update
    while True:
        await ps.updated.wait()
        ps.updated.clear()
        readings = ps.get_readings()
        print(f"Coords: {readings} Latched: {ps.is_latched()}")


if __name__ == "__main__":
    asyncio.run(main())
