import asyncio
import logging

from radioglobe.main import App
from radioglobe.radio_config import LOG_LEVEL


def main() -> None:
    logging.basicConfig(
        format="%(asctime)s: %(message)s",
        datefmt="%H:%M:%S",
        level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    )

    logging.info("Starting RadioGlobe...")

    asyncio.run(App().run())


if __name__ == "__main__":
    main()
