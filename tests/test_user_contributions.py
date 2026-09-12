import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

import db
from export_contributed_ratings import anonymize_ratings


class UserContributionTests(unittest.TestCase):
    def setUp(self):
        self.original_database_path = db.DATABASE_PATH
        self.temp_directory = tempfile.TemporaryDirectory(dir=".")
        db.DATABASE_PATH = str(Path(self.temp_directory.name) / "test_users.db")
        db.init_db()

    def tearDown(self):
        db.DATABASE_PATH = self.original_database_path
        self.temp_directory.cleanup()

    def test_user_must_opt_in_and_opt_out_removes_ratings(self):
        db.save_user(101, "Reader")
        rated_books = [
            {"book_title": "Dune", "rating": 5},
            {"book_title": "The Hobbit", "rating": 4},
        ]

        self.assertFalse(db.has_training_consent(101))
        self.assertEqual(db.replace_contributed_ratings(101, rated_books), 0)
        self.assertEqual(db.get_contributed_ratings(), [])

        db.set_training_consent(101, True)
        self.assertEqual(db.replace_contributed_ratings(101, rated_books), 2)
        self.assertEqual(len(db.get_contributed_ratings()), 2)

        db.set_training_consent(101, False)
        self.assertFalse(db.has_training_consent(101))
        self.assertEqual(db.get_contributed_ratings(), [])

    def test_relinking_replaces_old_contributed_ratings(self):
        db.save_user(101, "Reader")
        db.set_training_consent(101, True)
        db.replace_contributed_ratings(
            101,
            [{"book_title": "Dune", "rating": 4}],
        )

        saved_count = db.replace_contributed_ratings(
            101,
            [
                {"book_title": "Dune", "rating": 5},
                {"book_title": "Foundation", "rating": 4},
            ],
        )

        self.assertEqual(saved_count, 2)
        self.assertEqual(
            db.get_contributed_ratings(),
            [(101, "Dune", 5), (101, "Foundation", 4)],
        )

    def test_collection_summary_counts_users_without_listing_identities(self):
        db.save_user(101, "Reader One")
        db.save_goodreads(101, {"books": []})
        db.save_user(202, "Reader Two")
        db.set_training_consent(101, True)
        db.replace_contributed_ratings(
            101,
            [{"book_title": "Dune", "rating": 5}],
        )

        self.assertEqual(
            db.get_collection_summary(),
            {
                "users": 2,
                "goodreads_users": 1,
                "contributing_users": 1,
                "contributed_ratings": 1,
            },
        )

    def test_anonymized_export_excludes_telegram_ids(self):
        exported = anonymize_ratings(
            [
                (987654321, "Dune", 5),
                (987654321, "Foundation", 4),
                (123456789, "The Hobbit", 5),
            ]
        )

        self.assertEqual(exported[0]["user_id"], "bot_user_000001")
        self.assertEqual(exported[1]["user_id"], "bot_user_000001")
        self.assertEqual(exported[2]["user_id"], "bot_user_000002")
        self.assertNotIn("987654321", json.dumps(exported))


class ExistingDatabaseMigrationTests(unittest.TestCase):
    def setUp(self):
        self.original_database_path = db.DATABASE_PATH
        self.temp_directory = tempfile.TemporaryDirectory(dir=".")
        db.DATABASE_PATH = str(Path(self.temp_directory.name) / "old_users.db")

    def tearDown(self):
        db.DATABASE_PATH = self.original_database_path
        self.temp_directory.cleanup()

    def test_init_db_preserves_original_user_data(self):
        connection = sqlite3.connect(db.DATABASE_PATH)
        connection.execute(
            """
            CREATE TABLE users (
                telegram_id INTEGER PRIMARY KEY,
                name TEXT,
                goodreads_data TEXT
            )
            """
        )
        connection.execute(
            "INSERT INTO users VALUES (?, ?, ?)",
            (101, "Existing Reader", '{"books": []}'),
        )
        connection.commit()
        connection.close()

        db.init_db()

        self.assertEqual(db.get_user(101), ("Existing Reader", '{"books": []}'))
        self.assertFalse(db.has_training_consent(101))


if __name__ == "__main__":
    unittest.main()
