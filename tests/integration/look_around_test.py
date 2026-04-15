"""
look_around integration test: prints the current encoder position and the
surrounding search area each time the reticule moves significantly.

NOTE: Set the reticule to the origin (equator / prime meridian) before running.

Usage:
    python tests/integration/look_around_test.py
    python tests/integration/look_around_test.py --fuzziness 3 --stickiness 2
"""

import asyncio
import argparse
import pytest

pytest.importorskip("spidev", reason="Requires SPI hardware")

from radioglobe import database
from radioglobe.positional_encoders import PositionalEncoders


async def main(fuzziness: int, stickiness: int):
    print("Starting up encoders...")
    encoders = PositionalEncoders()
    encoders.start()

    # Wait for the first real SPI read before zeroing
    await encoders.updated.wait()
    encoders.updated.clear()

    encoders.zero()
    origin = encoders.get_readings()
    print(f"Origin: {origin} (expect (512, 512) at equator/prime meridian)")

    offsets = database.build_look_around_offsets(fuzziness)
    print(f"Fuzziness: {fuzziness} — {len(offsets)} surrounding coords")
    print(f"Stickiness: {stickiness} — move >{stickiness} units to trigger update\n")

    # Latch at origin so updated only fires on significant movement
    encoders.latch(*origin, stickiness)

    while True:
        await encoders.updated.wait()
        encoders.updated.clear()
        coords = encoders.get_readings()
        encoders.latch(*coords, stickiness)
        search_area = database.look_around(coords, offsets)
        print(f"Coords: {coords}  Search area: {search_area}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RadioGlobe look_around diagnostic")
    parser.add_argument("--fuzziness", type=int, default=5, help="Search area fuzziness (default: 5)")
    parser.add_argument("--stickiness", type=int, default=2, help="Minimum movement to trigger update (default: 2)")
    args = parser.parse_args()
    asyncio.run(main(args.fuzziness, args.stickiness))
