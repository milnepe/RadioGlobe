#! /usr/bin/python3
"""Display class for Grove 16 x 2 JHD1802 LCD module"""

import time
import threading
import logging
from grove.display.jhd1802 import JHD1802

# DISPLAY_I2C_ADDRESS = 0x27
# DISPLAY_I2C_PORT = 1
DISPLAY_COLUMNS = 16
DISPLAY_ROWS = 2


class Display (threading.Thread):
    """LCD display class with display buffers"""
    def __init__(self, threadID, name):
        threading.Thread.__init__(self)
        self.threadID = threadID
        self.name = name
        self.lcd = JHD1802()
        self.buffer = ["" for row in range(0, DISPLAY_ROWS)]
        self.changed = False

    def run(self):
        """Updates display when self.changed = True"""
        while True:
            if self.changed:
                for line_num in range(DISPLAY_ROWS):
                    self.lcd.setCursor(line_num, 0)
                    self.lcd.write(self.buffer[line_num])
                self.changed = False
            time.sleep(0.1)

    def clear(self):
        """Clear all display buffers and display itself"""
        for line_num in range(DISPLAY_ROWS):
            self.buffer[line_num] = ""
        self.lcd.clear()
        self.changed = True

    def message(self, lines: list):
        """Display message from list of items, one item per row"""
        logging.debug(f'Display lines: {lines}')
        for line in range(DISPLAY_ROWS):
            if line <= len(lines) - 1:
                self.buffer[line] = lines[line].center(DISPLAY_COLUMNS)
            else:
                self.buffer[line] = "".center(DISPLAY_COLUMNS)
        self.changed = True

    def update(self, north: float, east: float, location: str,
               volume: int, station: str, arrows: bool):
        """Update display for a location - calls message"""
        lines = []
        lines.append(location)
        if arrows:
            # Trim/pad the station name to fit arrows
            station = station[:(DISPLAY_COLUMNS - 4)]
            padding = DISPLAY_COLUMNS - 4 - len(station)
            start_padding = padding // 2
            end_padding = padding - start_padding
            while start_padding:
                station = " " + station
                start_padding -= 1
            while end_padding:
                station += " "
                end_padding -= 1
            station = "< " + station + " >"
        lines.append(station)

        if north >= 0:
            latitude = ("{:5.2f}N, ").format(north)
        else:
            latitude = ("{:5.2f}S, ").format(abs(north))
        if east >= 0:
            longitude = ("{:6.2f}E").format(east)
        else:
            longitude = ("{:6.2f}W").format(abs(east))
        print(latitude + longitude)
        lines.append(latitude + longitude)

        # Volume display
        vol_str = ""
        bar_length = (volume * DISPLAY_COLUMNS) // 100
        for i in range(bar_length):
          vol_str += "-"
        for i in range(bar_length, DISPLAY_COLUMNS):
          vol_str += " "
        lines.append(f'{vol_str}')

        self.message(lines)


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    try:
        display_thread = Display(1, "Display")
        display_thread.start()
        display_thread.clear()
        time.sleep(1)
        display_thread.message(["Hello", "World"])
        time.sleep(5)
        display_thread.message(["Tuning...."])
        time.sleep(5)
        display_thread.update(north=51.42, east=-2.59,
                              location="Bristol, United Kingdom",
                              volume=40,
                              station="BBC Radio Bristol",
                              arrows=True)
        time.sleep(5)
        display_thread.update(0, 0, "Clearing in 2s...", 0, "", False)
        time.sleep(5)
        display_thread.clear()

    except:
        exit()
