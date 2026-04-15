"""
look_around integration test: prints the current encoder position and the
surrounding search area for each encoder update.

NOTE: Set the reticule to the origin (equator / prime meridian) before running.

Usage:
    python tests/integration/look_around_test.py
    python tests/integration/look_around_test.py --fuzziness 3
"""

import asyncio
import argparse
import pytest

pytest.importorskip("spidev", reason="Requires SPI hardware")

from radioglobe import database
from radioglobe.positional_encoders import PositionalEncoders


async def main(fuzziness: int):
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
    print(f"Fuzziness: {fuzziness} — {len(offsets)} surrounding coords\n")

    last_coords = None
    while True:
        await encoders.updated.wait()
        encoders.updated.clear()
        coords = encoders.get_readings()
        if coords == last_coords:
            continue
        last_coords = coords
        search_area = database.look_around(coords, offsets)
        print(f"Coords: {coords}  Search area: {search_area}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RadioGlobe look_around diagnostic")
    parser.add_argument("--fuzziness", type=int, default=5, help="Search area fuzziness (default: 5)")
    args = parser.parse_args()
    asyncio.run(main(args.fuzziness))
