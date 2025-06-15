"""
Test reading the encoders as a background task asynchronously
"""

import asyncio
import time
from positional_encoders_async import Positional_Encoders


async def reader(encoders: Positional_Encoders):
    print("Starting reader...")
    while True:
        # Get a new pair of readings
        encoders.update()
        # Don't poll too quickly to allow for next reading
        await asyncio.sleep(0.2)  # 200 ms


async def main():
    # Initialise encoders
    ps = Positional_Encoders()
    # Note the globe should be set to the origin when starting main
    ps.zero()
    ps.update()
    initial_readings = ps.get_readings()

    # Start by setting the latch so we can see when it unlatches
    ps.latch(*initial_readings, 1)
    print(initial_readings)
    time.sleep(2)

    # Start reading the encoders continuosly in background
    asyncio.create_task(reader(ps))

    # Display the encoder values periodically
    while True:
        start_t = time.monotonic()
        readings = ps.get_readings()
        await asyncio.sleep(2)
        elapst_t = time.monotonic() - start_t
        print(f"Coords: {readings} Latched: {ps.is_latched()} t={elapst_t:.1f}")


if __name__ == "__main__":
    asyncio.run(main())
