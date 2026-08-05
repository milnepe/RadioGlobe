import asyncio
import logging

import evdev
from evdev import ecodes

_POLARITY = 1  # flip to -1 if on-device verification shows inverted direction


class Dial:
    def __init__(self) -> None:
        self.queue: asyncio.Queue[int] = asyncio.Queue()
        self._device = None
        self._loop = None

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

    def _on_readable(self) -> None:
        for event in self._device.read():
            if event.type == ecodes.EV_REL and event.code == ecodes.REL_X:
                if event.value > 0:
                    self.queue.put_nowait(_POLARITY * 1)
                elif event.value < 0:
                    self.queue.put_nowait(_POLARITY * -1)

    def start(self) -> None:
        """Locate and open the rotary-encoder device."""
        self._device = self._find_rotary_device()
        self._loop = asyncio.get_running_loop()
        self._loop.add_reader(self._device.fd, self._on_readable)

    async def stop(self) -> None:
        if self._loop is not None and self._device is not None:
            self._loop.remove_reader(self._device.fd)
        if self._device is not None:
            self._device.close()
