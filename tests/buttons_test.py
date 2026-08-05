import asyncio
import sys
import unittest
from unittest.mock import MagicMock

# buttons.py imports evdev at module scope - stub it before importing
# radioglobe.buttons so this test can run on any machine. Device discovery
# itself is deferred to Button.start()/ButtonManager.start(),
# which these tests never call (they drive handle_events() directly via
# the event_queue), so the stub only needs to satisfy the import.
sys.modules.setdefault("evdev", MagicMock())

from radioglobe.buttons import ButtonDefinition, ButtonManager  # noqa: E402


class TestHandleEventsResilience(unittest.IsolatedAsyncioTestCase):
    """handle_events() is the single consumer for every button's events -
    a handler that raises must not kill it, or every other button stops
    responding too (see buttons.py:handle_events docstring)."""

    async def test_exception_in_async_handler_does_not_block_other_buttons(self):
        calls = []

        async def bad_short():
            calls.append("bad")
            raise RuntimeError("boom")

        async def good_short():
            calls.append("good")

        definitions = [
            ButtonDefinition("Bad", 1, bad_short, None, None),
            ButtonDefinition("Good", 2, good_short, None, None),
        ]
        manager = ButtonManager(definitions)

        task = asyncio.create_task(manager.handle_events())
        await manager.event_queue.put(("Bad", "short"))
        await manager.event_queue.put(("Good", "short"))
        await asyncio.sleep(0.05)

        self.assertEqual(calls, ["bad", "good"])
        self.assertFalse(task.done())  # loop is still alive, waiting for the next event

        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task

    async def test_exception_in_sync_handler_does_not_block_other_buttons(self):
        calls = []

        def bad_short():
            calls.append("bad")
            raise ValueError("boom")

        def good_short():
            calls.append("good")

        definitions = [
            ButtonDefinition("Bad", 1, bad_short, None, None),
            ButtonDefinition("Good", 2, good_short, None, None),
        ]
        manager = ButtonManager(definitions)

        task = asyncio.create_task(manager.handle_events())
        await manager.event_queue.put(("Bad", "short"))
        await manager.event_queue.put(("Good", "short"))
        await asyncio.sleep(0.05)

        self.assertEqual(calls, ["bad", "good"])
        self.assertFalse(task.done())

        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task

    async def test_handler_exception_is_logged(self):
        async def bad_short():
            raise RuntimeError("boom")

        definitions = [ButtonDefinition("Bad", 1, bad_short, None, None)]
        manager = ButtonManager(definitions)

        task = asyncio.create_task(manager.handle_events())
        with self.assertLogs(level="ERROR") as logs:
            await manager.event_queue.put(("Bad", "short"))
            await asyncio.sleep(0.05)

        self.assertTrue(any("Bad" in record.getMessage() for record in logs.records))

        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task


if __name__ == "__main__":
    unittest.main()
