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

# Edit to suit your audio settings. Button-triggered volume step/on/off
# levels live in buttons.py instead (_VOLUME_STEP/_VOLUME_ON_LEVEL/
# _VOLUME_OFF_LEVEL) - fixed by this board's 4-button UX, not tunable here.
DEFAULT_VOLUME = 50

# Display hold durations (seconds)
BRIEF_DISPLAY_DURATION = 0.5   # volume level / final shutdown display hold
MESSAGE_DISPLAY_DURATION = 2   # startup splash, calibrating, shutdown message hold

# Stream health check grace period (seconds)
STREAM_CHECK_INTERVAL = 3

# LED flash duration (seconds) shared by two unrelated App-level events
# (city latch in _encoder_loop, stream error in _monitor_stream) - genuine
# app-behavior tuning, not owned by one hardware module. Button-press and
# dial-turn feedback durations live in buttons.py/dial.py instead
# (_LED_FLASH_SHORT/_LED_FLASH_DIAL) since each has exactly one owner.
LED_FLASH_LONG = 0.5    # city latch / stream error indication

# State persistence
STATE_CACHE_PATH = "~/cache/radioglobe.json"

# Logging
LOG_LEVEL = "DEBUG"
