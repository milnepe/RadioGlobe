import asyncio
import unittest

from radioglobe.buttons import ButtonDefinition
from radioglobe.hal.fake import (
    FakeAudioPlayer,
    FakeButtonManager,
    FakeDial,
    FakeDisplay,
    FakePositionalEncoders,
    FakeRGBLed,
)


class TestFakeDial(unittest.IsolatedAsyncioTestCase):
    async def test_push_turn_populates_queue(self):
        dial = FakeDial()
        dial.push_turn(1)
        dial.push_turn(-1)
        self.assertEqual(await dial.queue.get(), 1)
        self.assertEqual(await dial.queue.get(), -1)

    async def test_start_stop_toggle_flags(self):
        dial = FakeDial()
        dial.start()
        self.assertTrue(dial.started)
        await dial.stop()
        self.assertTrue(dial.stopped)


class TestFakePositionalEncoders(unittest.IsolatedAsyncioTestCase):
    async def test_set_position_sets_updated_event(self):
        encoders = FakePositionalEncoders()
        self.assertFalse(encoders.updated.is_set())
        encoders.set_position(512, 512)
        self.assertTrue(encoders.updated.is_set())
        self.assertEqual(encoders.get_readings(), (512, 512))

    def test_latch_and_calibration_round_trip(self):
        encoders = FakePositionalEncoders()
        self.assertFalse(encoders.is_latched())
        encoders.latch(100, 200, stickiness=2)
        self.assertTrue(encoders.is_latched())
        state = encoders.get_calibration()
        restored = FakePositionalEncoders()
        restored.restore_calibration(state)
        self.assertEqual(restored.get_readings(), encoders.get_readings())
        self.assertTrue(restored.is_latched())

    async def test_start_stop_toggle_flags(self):
        encoders = FakePositionalEncoders()
        encoders.start()
        self.assertTrue(encoders.started)
        await encoders.stop()
        self.assertTrue(encoders.stopped)


class TestFakeButtonManager(unittest.IsolatedAsyncioTestCase):
    async def test_inject_event_dispatches_to_matching_callback(self):
        calls = []

        async def short_cb():
            calls.append("short")

        definitions = [ButtonDefinition("Top", 5, short_cb, None, None)]
        manager = FakeButtonManager(definitions)

        task = asyncio.create_task(manager.handle_events())
        await manager.inject_event("Top", "short")
        await asyncio.sleep(0.01)

        self.assertEqual(calls, ["short"])
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task

    async def test_start_stop_toggle_flags(self):
        manager = FakeButtonManager([])
        manager.start()
        self.assertTrue(manager.started)
        await manager.stop()
        self.assertTrue(manager.stopped)


class TestFakeRGBLed(unittest.IsolatedAsyncioTestCase):
    async def test_flash_records_color_and_ends_off(self):
        led = FakeRGBLed()
        await led.flash("blue", 0.0)
        self.assertIn(("flash", "blue", 0.0), led.calls)
        self.assertEqual(led.current_color, "off")


class TestFakeDisplay(unittest.TestCase):
    def test_message_updates_buffer_and_changed_event(self):
        display = FakeDisplay()
        display.message(line_1="a", line_2="b")
        self.assertEqual(display.buffer, ["a", "b", "", ""])
        self.assertTrue(display.changed.is_set())

    def test_show_station_and_update_are_recorded(self):
        display = FakeDisplay()
        display.show_station(None, "London,GB", "BBC")
        display.update(None, "London,GB", 50, "BBC", arrows=True)
        self.assertEqual(display.calls[0][0], "show_station")
        self.assertEqual(display.calls[1][0], "update")


class TestFakeAudioPlayer(unittest.IsolatedAsyncioTestCase):
    def test_play_records_url_and_clears_error(self):
        player = FakeAudioPlayer()
        player.set_error(True)
        player.play("http://example.com/stream")
        self.assertEqual(player.current_url, "http://example.com/stream")
        self.assertEqual(player.played, ["http://example.com/stream"])
        self.assertFalse(player.is_error())

    def test_change_volume_clamps(self):
        player = FakeAudioPlayer()
        player.volume = 95
        self.assertEqual(player.change_volume(10), 100)
        self.assertEqual(player.change_volume(-1000), 10)

    async def test_stop_counts_calls(self):
        player = FakeAudioPlayer()
        await player.stop()
        await player.stop()
        self.assertEqual(player.stopped_calls, 2)


if __name__ == "__main__":
    unittest.main()
