import time
import threading
import RPi.GPIO as GPIO


class Dial(threading.Thread):
    def __init__(self, threadID, name):
        super().__init__()
        self.threadID = threadID
        self.name = name
        self._stop_event = threading.Event()

        GPIO.setmode(GPIO.BCM)
        GPIO.setup([17, 18], direction=GPIO.IN, pull_up_down=GPIO.PUD_UP)
        self.direction = 0

    def stop(self):
        self._stop_event.set()

    def stopped(self):
        return self._stop_event.is_set()

    def get_direction(self):
        return_val = self.direction
        self.direction = 0
        return return_val

    def run(self):
        while not self.stopped():
            GPIO.wait_for_edge(17, GPIO.FALLING, timeout=500)
            if self.stopped():
                break
            new_direction = GPIO.input(18)
            if not new_direction:
                new_direction = -1
            self.direction = new_direction
            time.sleep(0.3)  # Debounce

    def __del__(self):
        GPIO.cleanup()
