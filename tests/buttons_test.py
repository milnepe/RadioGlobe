import asyncio
import sys
import unittest
from unittest.mock import MagicMock

# AsyncButton.__init__ calls real RPi.GPIO functions, and RPi.GPIO itself
# refuses to import off a Raspberry Pi - stub it before importing
# radioglobe.buttons so this test can run on any machine.
sys.modules.setdefault("RPi", MagicMock())
sys.modules.setdefault("RPi.GPIO", MagicMock())

from radioglobe.buttons import AsyncButtonManager, ButtonDefinition  # noqa: E402


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

        loop = asyncio.get_running_loop()
        definitions = [
            ButtonDefinition("Bad", 1, bad_short, None, None),
            ButtonDefinition("Good", 2, good_short, None, None),
        ]
        manager = AsyncButtonManager(definitions, loop)

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

        loop = asyncio.get_running_loop()
        definitions = [
            ButtonDefinition("Bad", 1, bad_short, None, None),
            ButtonDefinition("Good", 2, good_short, None, None),
        ]
        manager = AsyncButtonManager(definitions, loop)

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

        loop = asyncio.get_running_loop()
        definitions = [ButtonDefinition("Bad", 1, bad_short, None, None)]
        manager = AsyncButtonManager(definitions, loop)

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
