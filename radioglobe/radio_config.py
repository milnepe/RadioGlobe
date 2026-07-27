"""Global settings"""

STATIONS_JSON = "stations/stations.json"

ENCODER_RESOLUTION = 1024

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
LED_FLASH_SHORT = 0.2   # button press feedback
LED_FLASH_LONG = 0.5    # city latch / stream error indication
LED_FLASH_DIAL = 0.1    # dial turn feedback (brief since frequent)

# GPIO pin assignments (BCM numbering)
PIN_DIAL_CLOCK = 17
PIN_DIAL_DIR   = 18
PIN_BTN_JOG    = 27
PIN_BTN_TOP    = 5
PIN_BTN_MID    = 6
PIN_BTN_BOTTOM = 12
PIN_LED_R      = 22
PIN_LED_G      = 23
PIN_LED_B      = 24

# I2C
I2C_LCD_ADDR   = 0x27

# State persistence
STATE_CACHE_PATH = "~/cache/radioglobe.json"

# Logging
LOG_LEVEL = "DEBUG"
