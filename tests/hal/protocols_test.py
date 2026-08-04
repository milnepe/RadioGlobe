"""Regression guard: fakes must keep satisfying their Protocols' shape."""

import unittest

from radioglobe.hal.fake import (
    FakeAudioPlayer,
    FakeButtonManager,
    FakeDial,
    FakeDisplay,
    FakePositionalEncoders,
    FakeRGBLed,
)
from radioglobe.hal.protocols import (
    AudioPlayerProtocol,
    ButtonManagerProtocol,
    DialProtocol,
    DisplayProtocol,
    PositionalEncodersProtocol,
    RGBLedProtocol,
)


class TestFakesSatisfyProtocols(unittest.TestCase):
    def test_fake_dial_satisfies_dial_protocol(self):
        self.assertIsInstance(FakeDial(), DialProtocol)

    def test_fake_positional_encoders_satisfies_protocol(self):
        self.assertIsInstance(FakePositionalEncoders(), PositionalEncodersProtocol)

    def test_fake_button_manager_satisfies_protocol(self):
        self.assertIsInstance(FakeButtonManager([]), ButtonManagerProtocol)

    def test_fake_rgb_led_satisfies_protocol(self):
        self.assertIsInstance(FakeRGBLed(), RGBLedProtocol)

    def test_fake_display_satisfies_protocol(self):
        self.assertIsInstance(FakeDisplay(), DisplayProtocol)

    def test_fake_audio_player_satisfies_protocol(self):
        self.assertIsInstance(FakeAudioPlayer(), AudioPlayerProtocol)


if __name__ == "__main__":
    unittest.main()
