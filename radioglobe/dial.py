import asyncio
import logging

import evdev
from evdev import ecodes

from .radio_config import DIAL_DEBOUNCE_S

_POLARITY = 1  # flip to -1 if on-device verification shows inverted direction


class AsyncDial:
    def __init__(self):
        self.queue: asyncio.Queue[int] = asyncio.Queue()
        self._device = self._find_rotary_device()
        self._loop = None
        self._pending_sum = 0
        self._debounce_handle: asyncio.TimerHandle | None = None

    @staticmethod
    def _find_rotary_device() -> evdev.InputDevice:
        for path in evdev.list_devices():
            dev = evdev.InputDevice(path)
            caps = dev.capabilities()
            has_rel_x = ecodes.EV_REL in caps and ecodes.REL_X in caps[ecodes.EV_REL]
            has_keys = ecodes.EV_KEY in caps
            if has_rel_x and not has_keys:
                if "rotary" not in dev.name.lower():
                    logging.warning(f"Matched rotary encoder by capability, unexpected name: {dev.name!r}")
                return dev
        raise RuntimeError(
            "No rotary-encoder input device found — check "
            "'dtoverlay=rotary-encoder,...' in /boot/firmware/config.txt and reboot"
        )

    def _on_readable(self):
        for event in self._device.read():
            if event.type == ecodes.EV_REL and event.code == ecodes.REL_X:
                self._pending_sum += event.value
                if self._debounce_handle is not None:
                    self._debounce_handle.cancel()
                self._debounce_handle = self._loop.call_later(DIAL_DEBOUNCE_S, self._flush)

    def _flush(self):
        self._debounce_handle = None
        if self._pending_sum > 0:
            self.queue.put_nowait(_POLARITY * 1)
        elif self._pending_sum < 0:
            self.queue.put_nowait(_POLARITY * -1)
        self._pending_sum = 0

    def start(self):
        self._loop = asyncio.get_running_loop()
        self._loop.add_reader(self._device.fd, self._on_readable)

    async def stop(self):
        if self._debounce_handle is not None:
            self._debounce_handle.cancel()
            self._debounce_handle = None
        if self._loop is not None:
            self._loop.remove_reader(self._device.fd)
        self._device.close()
