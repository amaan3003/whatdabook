import asyncio
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

import requests

from bot_runtime import guard_user_flow, request_id, run_in_worker, timed_stage


def fake_update(user_id=1):
    message = SimpleNamespace(reply_text=AsyncMock())
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=user_id), effective_message=message,
        message=message, callback_query=None,
    )


class FlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_slow_user_does_not_block_other_user_and_duplicate_is_rejected(self):
        started, release = asyncio.Event(), asyncio.Event()
        first, second = fake_update(1), fake_update(2)
        first_context = SimpleNamespace(user_data={})
        second_context = SimpleNamespace(user_data={})
        completed = []

        @guard_user_flow
        async def handler(update, context):
            if update.effective_user.id == 1:
                started.set()
                await release.wait()
            completed.append(update.effective_user.id)

        task = asyncio.create_task(handler(first, first_context))
        try:
            await asyncio.wait_for(started.wait(), 2)
            await handler(first, first_context)
            first.message.reply_text.assert_awaited_once()
            await handler(second, second_context)
            self.assertEqual(completed, [2])
            release.set()
            await asyncio.wait_for(task, 2)
            self.assertEqual(completed, [2, 1])
            self.assertNotIn("_processing_update", first_context.user_data)
        finally:
            release.set()
            await task

    async def test_busy_callback_is_answered_without_changing_conversation(self):
        update = fake_update()
        update.callback_query = SimpleNamespace(answer=AsyncMock())
        context = SimpleNamespace(user_data={"_processing_update": True, "awaiting_goodreads_link": True})
        handler = AsyncMock()
        await guard_user_flow(handler)(update, context)
        handler.assert_not_awaited()
        update.callback_query.answer.assert_awaited_once()
        self.assertTrue(context.user_data["awaiting_goodreads_link"])

    async def test_error_and_cancellation_release_user_and_reset_log_context(self):
        for failure in (ValueError("private data"), asyncio.CancelledError()):
            context = SimpleNamespace(user_data={})
            handler = guard_user_flow(AsyncMock(side_effect=failure))
            with self.assertRaises(type(failure)):
                await handler(fake_update(), context)
            self.assertNotIn("_processing_update", context.user_data)
            self.assertEqual(request_id.get(), "none")
            next_handler = AsyncMock()
            await guard_user_flow(next_handler)(fake_update(), context)
            next_handler.assert_awaited_once()

    async def test_worker_propagates_request_id(self):
        ids = []

        @guard_user_flow
        async def handler(update, context):
            ids.append(request_id.get())
            ids.append(await run_in_worker("test_worker", request_id.get))

        with self.assertLogs("whatdabook", level="INFO") as captured:
            await handler(fake_update(), SimpleNamespace(user_data={}))
        self.assertEqual(ids[0], ids[1])
        self.assertNotEqual(ids[0], "none")
        self.assertTrue(all(f"request={ids[0]}" in line for line in captured.output))


class TimingTests(unittest.TestCase):
    def test_records_duration_on_success(self):
        with self.assertLogs("whatdabook", level="INFO") as captured:
            with patch("bot_runtime.perf_counter", side_effect=[10, 11.25]):
                with timed_stage("ocr"):
                    pass
        self.assertIn("duration_ms=1250 outcome=ok", captured.output[-1])

    def test_error_records_safe_type_and_http_status_without_exception_text(self):
        response = requests.Response()
        response.status_code = 429
        secret = "fake-secret-and-private-goodreads-data"
        with self.assertLogs("whatdabook", level="INFO") as captured:
            with self.assertRaises(RuntimeError):
                with timed_stage("llm_summary"):
                    try:
                        raise requests.HTTPError(secret, response=response)
                    except requests.HTTPError as error:
                        raise RuntimeError(secret) from error
        output = "\n".join(captured.output)
        self.assertIn("outcome=error", output)
        self.assertIn("cause=HTTPError http_status=429", output)
        self.assertNotIn(secret, output)
