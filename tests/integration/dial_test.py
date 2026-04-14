import time
import signal
import sys

from dial_new import Dial

# Instantiate the Dial thread
jog = Dial(threadID=1, name="TestDial")


def signal_handler(sig, frame):
    print("\n[INFO] Stopping Dial thread and cleaning up GPIO.")
    try:
        del dial
    except NameError:
        pass
    sys.exit(0)


signal.signal(signal.SIGINT, signal_handler)

print("[INFO] Starting Dial thread...")
jog.start()

try:
    while True:
        direction = jog.get_direction()
        if direction != 0:
            print(
                f"[DIRECTION] Detected turn: {'Counter-clockwise' if direction == 1 else 'Clockwise'}"
            )
        time.sleep(1)
except KeyboardInterrupt:
    signal_handler(None, None)
