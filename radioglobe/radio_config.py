"""Global settings"""

STATIONS_JSON = "stations/stations.json"

ENCODER_RESOLUTION = 1024

# Higher values of fuzziness increases the search area.
# May include more than one city may be included if they are located close together.
FUZZINESS = 2

# Affects ability to latch on to cities
STICKINESS = 1

# Edit these to suit your audio settings
VOLUME_STEP = 10

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
LOG_LEVEL = "INFO"
