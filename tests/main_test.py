import asyncio
import sys
import unittest
from unittest.mock import MagicMock

# main.py imports radioglobe.buttons (for the JOG_BUTTON/etc. button-definition
# constants) and radioglobe.dial (for _LED_FLASH_DIAL), and buttons.py/dial.py
# themselves import RPi.GPIO/evdev at module scope - stub both before importing
# radioglobe.main so this test can run on any machine, same as
# tests/buttons_test.py already does for RPi.GPIO. radioglobe.hal (Protocols +
# fakes) needs no such stub, since it never imports radioglobe.buttons,
# radioglobe.dial, or radioglobe.main.
sys.modules.setdefault("RPi", MagicMock())
sys.modules.setdefault("RPi.GPIO", MagicMock())
sys.modules.setdefault("evdev", MagicMock())

from radioglobe.constants import MODE_STATION  # noqa: E402
from radioglobe.database import build_cities_index  # noqa: E402
from radioglobe.hal.fake import (  # noqa: E402
    FakeAudioPlayer,
    FakeDial,
    FakeDisplay,
    FakePositionalEncoders,
    FakeRGBLed,
)
from radioglobe.main import App  # noqa: E402
from radioglobe.navigation import Navigator  # noqa: E402
from radioglobe.rgb_led import COLOUR_BLUE, COLOUR_GREEN  # noqa: E402

STATIONS_INFO = {
    "TestCity,XY": {
        "coords": {"n": 0.0, "e": 0.0},
        "urls": [{"name": "Test Station", "url": "http://example.com/stream"}],
    }
}
# build_cities_index() maps n=0,e=0 to grid index (512, 512) - see
# database.py's (coord + 180) * 1024 / 360 formula.
CITY_GRID_COORDS = (512, 512)


def make_app(nav=None):
    """Build an App wired entirely to HAL fakes - no real hardware I/O."""
    if nav is None:
        nav = Navigator(stations_json="/nonexistent/stations.json")
        nav.stations_info = STATIONS_INFO
        nav.cities_info = build_cities_index(STATIONS_INFO)
    return App(
        dial=FakeDial(),
        audio_player=FakeAudioPlayer(),
        encoders=FakePositionalEncoders(),
        display=FakeDisplay(),
        led=FakeRGBLed(),
        nav=nav,
    )


class TestEncoderLoop(unittest.IsolatedAsyncioTestCase):
    async def test_latch_selects_city_and_plays_station(self):
        app = make_app()
        task = asyncio.create_task(app._encoder_loop())
        try:
            app.encoders.set_position(*CITY_GRID_COORDS)
            await asyncio.sleep(0.05)

            self.assertEqual(app.nav.state.city, "TestCity,XY")
            self.assertEqual(app.nav.state.station, ("Test Station", "http://example.com/stream"))
            self.assertTrue(app.encoders.is_latched())
            self.assertEqual(app.audio_player.played, ["http://example.com/stream"])
            self.assertTrue(any(call[0] == "show_station" for call in app.display.calls))
            self.assertTrue(any(call[:2] == ("flash", COLOUR_GREEN) for call in app.led.calls))
        finally:
            task.cancel()
            if app._stream_task:
                app._stream_task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task


class TestDialLoop(unittest.IsolatedAsyncioTestCase):
    async def test_turn_advances_station_and_flashes_blue(self):
        app = make_app()
        app.nav.state.mode = MODE_STATION
        app.nav.state.city = "TestCity,XY"
        app.nav.state.stations = [("A", "urlA"), ("B", "urlB")]
        app.nav.state.station_idx = 0
        app.nav.state.station = app.nav.state.stations[0]

        task = asyncio.create_task(app._dial_loop())
        try:
            app.dial.push_turn(1)
            await asyncio.sleep(0.05)

            self.assertEqual(app.nav.state.station, ("B", "urlB"))
            self.assertEqual(app.audio_player.played, ["urlB"])
            self.assertTrue(any(call[:2] == ("flash", COLOUR_BLUE) for call in app.led.calls))
        finally:
            task.cancel()
            if app._stream_task:
                app._stream_task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task

    async def test_turn_is_ignored_when_selection_incomplete(self):
        app = make_app()
        # nav.state starts with no city/station selected.
        task = asyncio.create_task(app._dial_loop())
        try:
            app.dial.push_turn(1)
            await asyncio.sleep(0.05)

            self.assertEqual(app.audio_player.played, [])
        finally:
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task


class TestMonitorStream(unittest.IsolatedAsyncioTestCase):
    async def test_stream_error_removes_station_and_plays_next(self):
        app = make_app()
        app.nav.state.city = "TestCity,XY"
        app.nav.state.stations = [("A", "urlA"), ("B", "urlB")]
        app.nav.state.station_idx = 0
        app.nav.state.station = app.nav.state.stations[0]
        app.audio_player.play("urlA")
        app.audio_player.set_error(True)

        # _monitor_stream() awaits STREAM_CHECK_INTERVAL internally; patch it
        # out via a near-zero override to keep the test fast.
        from radioglobe import main as main_module

        original_interval = main_module.STREAM_CHECK_INTERVAL
        main_module.STREAM_CHECK_INTERVAL = 0
        try:
            task = asyncio.create_task(app._monitor_stream("urlA"))
            await asyncio.sleep(0.05)

            self.assertEqual(app.nav.state.station, ("B", "urlB"))
            self.assertEqual(app.audio_player.played, ["urlA", "urlB"])
            self.assertTrue(any(call[0] == "flash" for call in app.led.calls))
        finally:
            main_module.STREAM_CHECK_INTERVAL = original_interval
            # The monitor finds a working station and returns on its own once
            # STREAM_CHECK_INTERVAL is 0, so the task may already be done by
            # the time we get here - cancel() is a no-op in that case.
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def test_returns_early_if_user_already_changed_station(self):
        app = make_app()
        app.audio_player.play("urlA")
        app.audio_player.current_url = "urlB"  # user moved on

        from radioglobe import main as main_module

        original_interval = main_module.STREAM_CHECK_INTERVAL
        main_module.STREAM_CHECK_INTERVAL = 0
        try:
            await app._monitor_stream("urlA")
        finally:
            main_module.STREAM_CHECK_INTERVAL = original_interval

        self.assertEqual(app.audio_player.played, ["urlA"])


class TestSaveLoadState(unittest.TestCase):
    def test_save_and_load_round_trip_encoder_calibration(self):
        import tempfile
        import os

        app = make_app()
        app.encoders.latch(100, 200, stickiness=2)
        app.nav.state.city = "TestCity,XY"
        app.nav.state.station = ("Test Station", "http://example.com/stream")

        with tempfile.TemporaryDirectory() as tmp:
            cache = os.path.join(tmp, "state.json")
            app.save_state(cache)

            restored_app = make_app()
            encoder_state = restored_app.nav.load_state(cache)
            restored_app.encoders.restore_calibration(encoder_state)

            self.assertEqual(restored_app.encoders.get_readings(), app.encoders.get_readings())
            self.assertEqual(restored_app.nav.state.city, "TestCity,XY")


if __name__ == "__main__":
    unittest.main()
