"""Global settings"""
import os

# Allow overriding the stations file via env var for testing and deployment.
# Prefer an explicit RADIOGLOBE_STATIONS path, then the system install path
# (/opt/radioglobe/stations/stations.json), and finally the repo-relative
# default 'stations/stations.json'.
DEFAULT_STATIONS = "stations/stations.json"
SYSTEM_STATIONS = "/opt/radioglobe/stations/stations.json"

STATIONS_JSON = os.environ.get("RADIOGLOBE_STATIONS") or (
    SYSTEM_STATIONS if os.path.exists(SYSTEM_STATIONS) else DEFAULT_STATIONS
)

# Higher values of fuzziness increases the search area.
# May include more than one city may be included if they are located close together.
FUZZINESS = 3

# Affects ability to latch on to cities
STICKINESS = 2

# Edit these to suit your audio settings
VOLUME_STEP = 10
DEFAULT_VOLUME = 50
VOLUME_ON_LEVEL = 80
VOLUME_OFF_LEVEL = 0

# Display hold durations (seconds)
BRIEF_DISPLAY_DURATION = 0.5   # volume level / final shutdown display hold
MESSAGE_DISPLAY_DURATION = 2   # startup splash, calibrating, shutdown message hold

# Stream health check grace period (seconds)
STREAM_CHECK_INTERVAL = 3

# LED flash durations (seconds)
LED_FLASH_SHORT = 0.2   # button press feedback (brief since frequent)
LED_FLASH_LONG = 0.5    # city latch / stream error indication
LED_FLASH_DIAL = 0.1    # dial turn feedback (brief since frequent)

# State persistence
STATE_CACHE_PATH = "~/cache/radioglobe.json"

# Logging - override without a redeploy via RADIOGLOBE_LOG_LEVEL=DEBUG + restart
LOG_LEVEL = os.environ.get("RADIOGLOBE_LOG_LEVEL", "INFO")
