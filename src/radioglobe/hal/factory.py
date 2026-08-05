"""Builds the real, Pi-backed hardware bundle for production use.

The concrete hardware modules are imported inside build_hardware()'s body,
not at this module's top level, so importing radioglobe.hal never triggers
evdev/spidev/RPi.GPIO/liquidcrystal_i2c/vlc imports off a Pi - only calling
build_hardware() does.
"""

from radioglobe.hal.protocols import (
    AudioPlayerProtocol,
    DialProtocol,
    DisplayProtocol,
    PositionalEncodersProtocol,
    RGBLedProtocol,
)


def build_hardware() -> tuple[
    DialProtocol,
    AudioPlayerProtocol,
    PositionalEncodersProtocol,
    DisplayProtocol,
    RGBLedProtocol,
]:
    """Construct the real hardware-backed objects App needs.

    Returned in App.__init__'s parameter order. Only ever called on a real
    Pi with the `pi` extra installed.
    """
    from radioglobe.hal.audio_async import AudioPlayer
    from radioglobe.hal.dial import Dial
    from radioglobe.hal.display import Display
    from radioglobe.hal.positional_encoders import PositionalEncoders
    from radioglobe.hal.rgb_led import RGBLed

    return Dial(), AudioPlayer(), PositionalEncoders(), Display(), RGBLed()
