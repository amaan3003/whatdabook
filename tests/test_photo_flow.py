from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

import main
from bot_runtime import guard_user_flow
from rate_limiter import SlidingWindowRateLimiter
from test_bot_runtime import fake_update


class PhotoFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_eighth_photo_rejected_before_processing_and_other_user_allowed(self):
        limiter = SlidingWindowRateLimiter(7, 60)
        update, context = fake_update(), SimpleNamespace(user_data={})
        with patch.object(main, "photo_rate_limiter", limiter), patch.object(
            main, "process_photo", new_callable=AsyncMock
        ) as process:
            handler = guard_user_flow(main.handle_photo)
            for _ in range(8):
                await handler(update, context)
            self.assertEqual(process.await_count, 7)
            self.assertIn("7 photos per minute", update.message.reply_text.call_args.args[0])
            await handler(fake_update(2), SimpleNamespace(user_data={}))
            self.assertEqual(process.await_count, 8)

    async def test_failed_photo_releases_both_processing_flags(self):
        context = SimpleNamespace(user_data={})
        with patch.object(main, "photo_rate_limiter", SlidingWindowRateLimiter(7, 60)), patch.object(
            main, "process_photo", new_callable=AsyncMock, side_effect=RuntimeError("test")
        ):
            with self.assertRaises(RuntimeError):
                await guard_user_flow(main.handle_photo)(fake_update(), context)
        self.assertNotIn("photo_processing", context.user_data)
        self.assertNotIn("_processing_update", context.user_data)

    async def test_ocr_failure_offers_title_entry_and_removes_download(self):
        update = fake_update()
        status = SimpleNamespace(edit_text=AsyncMock())
        update.message.reply_text.return_value = status
        file = SimpleNamespace(download_to_drive=AsyncMock())
        update.message.photo = [SimpleNamespace(get_file=AsyncMock(return_value=file))]
        with patch.object(main, "ocr", side_effect=RuntimeError("OCR unavailable")), patch.object(
            main, "build_book_report", new_callable=AsyncMock
        ) as report:
            await main.process_photo(update, SimpleNamespace(user_data={}))
        report.assert_not_awaited()
        self.assertIn("type the book title", status.edit_text.call_args.args[0])
        download_path = file.download_to_drive.call_args.args[0]
        self.assertFalse(download_path.exists())


class StartupAndOCRTests(unittest.TestCase):
    def test_all_conversation_handlers_are_guarded_and_concurrency_is_bounded(self):
        with patch.dict("os.environ", {"TELEGRAM_TOKEN": "123456:TEST_ONLY"}):
            app = main.create_application()
        self.assertEqual(app.concurrent_updates, 8)
        self.assertEqual(len(app.handlers[0]), 10)
        for handler in app.handlers[0]:
            self.assertTrue(hasattr(handler.callback, "__wrapped__"))

    def test_ocr_uses_timeout_and_closes_client(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cover.jpg"
            path.write_bytes(b"test-image")
            with patch.object(main.vision, "ImageAnnotatorClient") as constructor:
                client = constructor.return_value.__enter__.return_value
                client.text_detection.return_value = SimpleNamespace(
                    error=SimpleNamespace(message=""),
                    text_annotations=[SimpleNamespace(description="Dune")],
                )
                self.assertEqual(main.ocr(path), "Dune")
                self.assertEqual(client.text_detection.call_args.kwargs["timeout"], 20)
                self.assertIsNone(client.text_detection.call_args.kwargs["retry"])
                constructor.return_value.__exit__.assert_called_once()
