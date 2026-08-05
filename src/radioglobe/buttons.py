import asyncio
import inspect
import logging
import time
from typing import Callable, NamedTuple, Optional

import evdev
from evdev import ecodes

# GPIO pin assignments (BCM numbering) - documentation only. The kernel
# gpio-keys driver claims these pins directly via install.sh's
# dtoverlay=gpio-key,... lines; nothing in this module reads them.
_PIN_BTN_JOG    = 27
_PIN_BTN_TOP    = 5
_PIN_BTN_MID    = 6
_PIN_BTN_BOTTOM = 12

# Linux "generic button" keycodes (see evdev.ecodes / input-event-codes.h),
# one per gpio-key overlay instance's keycode= param - install.sh's overlay
# lines must use these same values. Used to identify which evdev device
# belongs to which button: the overlay's label= param does NOT reliably set
# the device name (confirmed on-device - every instance shows up as
# "button@<hex-gpio>" regardless of label), so matching on the keycode each
# device reports is the only reliable way to tell 4 simultaneous button
# devices apart. See tests/integration/README.md's gpio-keys section.
_KEYCODE_BTN_JOG    = ecodes.BTN_0
_KEYCODE_BTN_TOP    = ecodes.BTN_1
_KEYCODE_BTN_MID    = ecodes.BTN_2
_KEYCODE_BTN_BOTTOM = ecodes.BTN_3


class ButtonDefinition(NamedTuple):
    name: str
    pin: int
    short_cb: Optional[Callable] = None
    long_cb: Optional[Callable] = None
    press_cb: Optional[Callable] = None
    keycode: int = 0


class ButtonCallbacks(NamedTuple):
    """ButtonDefinition minus name/pin - just the callback slots a caller wires up."""
    short_cb: Optional[Callable] = None
    long_cb: Optional[Callable] = None
    press_cb: Optional[Callable] = None


# Name+pin+keycode triples for the 4 buttons wired to this project's custom
# board - fixed by the hardware, not a choice callers make. Callers attach
# their own callbacks with e.g. TOP_BUTTON._replace(short_cb=..., ...); the
# numeric _PIN_BTN_*/_KEYCODE_BTN_* constants above are not meant to be
# imported directly.
JOG_BUTTON    = ButtonDefinition("Jog",    _PIN_BTN_JOG,    keycode=_KEYCODE_BTN_JOG)
TOP_BUTTON    = ButtonDefinition("Top",    _PIN_BTN_TOP,    keycode=_KEYCODE_BTN_TOP)
MID_BUTTON    = ButtonDefinition("Mid",    _PIN_BTN_MID,    keycode=_KEYCODE_BTN_MID)
BOTTOM_BUTTON = ButtonDefinition("Bottom", _PIN_BTN_BOTTOM, keycode=_KEYCODE_BTN_BOTTOM)


def _fire(callback):
    """Invoke a sync or async callback without blocking the caller."""
    if callback is None:
        return
    if inspect.iscoroutinefunction(callback):
        asyncio.create_task(callback())
    else:
        callback()


class AsyncButton:
    """One button read via the kernel gpio-keys driver + evdev, instead of
    RPi.GPIO edge-detection.

    Device discovery is deferred to start() rather than done in __init__,
    so constructing an AsyncButton/AsyncButtonManager (e.g. in tests) never
    touches real hardware unless start() is actually called.
    """

    def __init__(self, name, keycode, long_press_threshold=1.0,
                 short_cb=None, long_cb=None, press_cb=None):
        self.name = name
        self.keycode = keycode
        self.long_press_threshold = long_press_threshold
        self.short_cb = short_cb
        self.long_cb = long_cb
        self.press_cb = press_cb

        self._device = None
        self._loop = None
        self._event_queue = None
        self._press_start = None

    @staticmethod
    def _find_button_device(keycode) -> evdev.InputDevice:
        for path in evdev.list_devices():
            dev = evdev.InputDevice(path)
            caps = dev.capabilities()
            if keycode in caps.get(ecodes.EV_KEY, ()) and ecodes.EV_REL not in caps:
                return dev
        raise RuntimeError(
            f"No gpio-keys input device found for keycode {keycode} - check "
            "'dtoverlay=gpio-key,...' in /boot/firmware/config.txt and reboot"
        )

    def _on_readable(self):
        for event in self._device.read():
            if event.type != ecodes.EV_KEY or event.code != self.keycode:
                continue
            if event.value == 1:  # key down
                self._press_start = time.monotonic()
                _fire(self.press_cb)
            elif event.value == 0 and self._press_start is not None:  # key up
                held = time.monotonic() - self._press_start
                self._press_start = None
                kind = "long" if held >= self.long_press_threshold else "short"
                self._event_queue.put_nowait((self.name, kind))

    def start(self, event_queue: asyncio.Queue):
        self._event_queue = event_queue
        self._device = self._find_button_device(self.keycode)
        self._loop = asyncio.get_running_loop()
        self._loop.add_reader(self._device.fd, self._on_readable)

    async def stop(self):
        if self._loop is not None and self._device is not None:
            self._loop.remove_reader(self._device.fd)
        if self._device is not None:
            self._device.close()


class AsyncButtonManager:
    def __init__(self, button_definitions, long_press_threshold=1.0):
        self.event_queue: asyncio.Queue = asyncio.Queue()
        self.buttons = [
            AsyncButton(
                d.name, d.keycode, long_press_threshold,
                d.short_cb, d.long_cb, d.press_cb,
            )
            for d in button_definitions
        ]

    def start(self):
        for btn in self.buttons:
            btn.start(self.event_queue)

    async def stop(self):
        """Release every managed button's evdev device."""
        for btn in self.buttons:
            await btn.stop()

    async def handle_events(self):
        """Continuously process events with the appropriate handler.

        A handler that raises must not kill this loop - it's the single
        consumer for every button's events, so an uncaught exception here
        would silently stop short/long dispatch for all buttons, not just
        the one whose handler failed.
        """
        while True:
            name, event_type = await self.event_queue.get()
            for btn in self.buttons:
                if btn.name == name:
                    handler = getattr(btn, f"{event_type}_cb", None)
                    if handler:
                        try:
                            if inspect.iscoroutinefunction(handler):
                                await handler()
                            else:
                                handler()
                        except Exception:
                            logging.exception(f"Button handler failed: {btn.name} {event_type}")

    def get_event_nowait(self):
        try:
            return self.event_queue.get_nowait()
        except asyncio.QueueEmpty:
            return None


def create_button_manager(
    *,
    jog: ButtonCallbacks = ButtonCallbacks(),
    top: ButtonCallbacks = ButtonCallbacks(),
    mid: ButtonCallbacks = ButtonCallbacks(),
    bottom: ButtonCallbacks = ButtonCallbacks(),
) -> AsyncButtonManager:
    """Wire the given callbacks to this board's fixed 4-button layout and
    construct the manager.

    Caller still owns start()/stop() lifecycle, matching every other
    hardware object (see hal/factory.py's build_hardware()).
    """
    button_definitions = [
        JOG_BUTTON._replace(**jog._asdict()),
        TOP_BUTTON._replace(**top._asdict()),
        MID_BUTTON._replace(**mid._asdict()),
        BOTTOM_BUTTON._replace(**bottom._asdict()),
    ]
    return AsyncButtonManager(button_definitions)
