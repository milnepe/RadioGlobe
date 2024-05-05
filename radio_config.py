"""Global settings"""
import logging

format = "%(asctime)s: %(message)s"
logging.basicConfig(format=format, level=logging.INFO, datefmt="%H:%M:%S")
logging.getLogger().setLevel(logging.DEBUG)

# Edit these to suit your audio settings
AUDIO_DEVICE = "UE BOOM 2"
# AUDIO_DEVICE = "Built-in Audio Analog Stereo"
VOLUME_INCREMENT = 1

STATIONS_JSON = "stations.json"

DATADIR = "data"
STATIONS_MAP = "data/map.dat"
CHECKSUMS_JSON = "data/checksums.json"
OFFSETS_JSON = "data/offsets.json"

# Higher values of fuzziness increases the search area.
# May include more than one city may be included if they are located close together.
FUZZINESS = 2

# Affects ability to latch on to cities
STICKINESS = 3
