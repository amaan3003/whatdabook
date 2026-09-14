import os
from contextlib import closing
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

import db
from bot_stats import get_stats, record_activity, stats_cmd


class StatsTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir='.')
        self.path_patch = patch.object(db, 'DATABASE_PATH', str(Path(self.tmp.name) / 'users.db'))
        self.path_patch.start()
        # Create an empty database so migration never copies the real local database.
        Path(db.DATABASE_PATH).touch()
        db.init_db()

    def tearDown(self):
        self.path_patch.stop()
        self.tmp.cleanup()

    def test_unique_users_and_request_counts(self):
        record_activity(1, 'One', photo=True)
        record_activity(1, 'One', recommendation=True)
        record_activity(2, 'Two')
        self.assertEqual(get_stats(), dict(total=2, new=2, today=2, week=2, photos=1, recommendations=1))
        db.init_db()
        self.assertEqual(get_stats()['photos'], 1)

    def test_old_activity_is_excluded(self):
        record_activity(1, 'One')
        with closing(db._connect()) as connection, connection:
            connection.execute("UPDATE daily_activity SET day = date('now', '-7 days')")
        self.assertEqual(get_stats()['week'], 0)
        self.assertEqual(get_stats()['today'], 0)

    async def test_admin_access_fails_closed_and_requires_private_chat(self):
        update = SimpleNamespace(effective_user=SimpleNamespace(id=42),
                                 effective_chat=SimpleNamespace(type='private'),
                                 effective_message=SimpleNamespace(reply_text=AsyncMock()))
        for admin, chat, allowed in [('', 'private', False), ('99', 'private', False),
                                     ('42', 'group', False), ('42', 'private', True)]:
            update.effective_chat.type = chat
            with patch.dict(os.environ, {'ADMIN_TELEGRAM_ID': admin}):
                await stats_cmd(update, None)
            response = update.effective_message.reply_text.call_args.args[0]
            self.assertEqual('Total saved users:' in response, allowed)
