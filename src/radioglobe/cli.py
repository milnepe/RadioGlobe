import asyncio
import logging
import logging.handlers

from radioglobe.hal.factory import build_hardware
from radioglobe.main import App
from radioglobe.radio_config import LOG_LEVEL


def main() -> None:
    level = getattr(logging, LOG_LEVEL.upper(), logging.INFO)
    try:
        # systemd-journald speaks syslog on /dev/log and maps the syslog
        # priority (which SysLogHandler derives from the Python level) into
        # the journal's own PRIORITY field, so `journalctl -p <level>` can
        # filter meaningfully - no extra dependency needed. journald owns
        # the timestamp, so it's left out of the format here.
        handler = logging.handlers.SysLogHandler(address="/dev/log")
        handler.setFormatter(logging.Formatter("radioglobe: %(levelname)s %(message)s"))
        logging.basicConfig(handlers=[handler], level=level)
    except OSError:
        # /dev/log not available (e.g. off-Pi dev, non-systemd host).
        logging.basicConfig(
            format="%(asctime)s %(levelname)s: %(message)s",
            datefmt="%H:%M:%S",
            level=level,
        )

    logging.info("Starting RadioGlobe...")

    asyncio.run(App(*build_hardware()).run())


if __name__ == "__main__":
    main()
