import json
import sqlite3


DATABASE_PATH = "users.db"


def _connect():
    connection = sqlite3.connect(DATABASE_PATH)
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _user_columns(connection):
    return {row[1] for row in connection.execute("PRAGMA table_info(users)")}


def init_db():
    """Create the database and add new columns without losing existing users."""
    connection = _connect()
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            telegram_id INTEGER PRIMARY KEY,
            name TEXT,
            goodreads_data TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            goodreads_updated_at TEXT,
            training_consent INTEGER NOT NULL DEFAULT 0,
            consent_updated_at TEXT
        )
        """
    )

    # Existing deployments may have the original three-column users table.
    columns = _user_columns(connection)
    if "created_at" not in columns:
        connection.execute("ALTER TABLE users ADD COLUMN created_at TEXT")
        connection.execute(
            "UPDATE users SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL"
        )
    if "goodreads_updated_at" not in columns:
        connection.execute("ALTER TABLE users ADD COLUMN goodreads_updated_at TEXT")
    if "training_consent" not in columns:
        connection.execute(
            "ALTER TABLE users ADD COLUMN training_consent INTEGER NOT NULL DEFAULT 0"
        )
    if "consent_updated_at" not in columns:
        connection.execute("ALTER TABLE users ADD COLUMN consent_updated_at TEXT")

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS contributed_ratings (
            telegram_id INTEGER NOT NULL,
            book_key TEXT NOT NULL,
            book_title TEXT NOT NULL,
            rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
            source TEXT NOT NULL DEFAULT 'goodreads',
            collected_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (telegram_id, book_key),
            FOREIGN KEY (telegram_id) REFERENCES users(telegram_id) ON DELETE CASCADE
        )
        """
    )
    connection.commit()
    connection.close()


def save_user(telegram_id, name):
    connection = _connect()
    connection.execute(
        """
        INSERT INTO users (telegram_id, name, created_at)
        VALUES (?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(telegram_id) DO UPDATE SET name = excluded.name
        """,
        (telegram_id, name),
    )
    connection.commit()
    connection.close()


def get_user(telegram_id):
    connection = _connect()
    cursor = connection.execute(
        "SELECT name, goodreads_data FROM users WHERE telegram_id = ?",
        (telegram_id,),
    )
    row = cursor.fetchone()
    connection.close()
    return row


def save_goodreads(telegram_id, goodreads_data):
    json_string = json.dumps(goodreads_data)
    connection = _connect()
    connection.execute(
        """
        UPDATE users
        SET goodreads_data = ?, goodreads_updated_at = CURRENT_TIMESTAMP
        WHERE telegram_id = ?
        """,
        (json_string, telegram_id),
    )
    connection.commit()
    connection.close()


def has_training_consent(telegram_id):
    connection = _connect()
    row = connection.execute(
        "SELECT training_consent FROM users WHERE telegram_id = ?",
        (telegram_id,),
    ).fetchone()
    connection.close()
    return bool(row and row[0])


def set_training_consent(telegram_id, consent):
    """Save the choice and erase contributed rows immediately on opt-out."""
    connection = _connect()
    connection.execute(
        """
        UPDATE users
        SET training_consent = ?, consent_updated_at = CURRENT_TIMESTAMP
        WHERE telegram_id = ?
        """,
        (1 if consent else 0, telegram_id),
    )
    if not consent:
        connection.execute(
            "DELETE FROM contributed_ratings WHERE telegram_id = ?",
            (telegram_id,),
        )
    connection.commit()
    connection.close()


def replace_contributed_ratings(telegram_id, rated_books):
    """Replace one opted-in user's derived ratings with their latest library."""
    if not has_training_consent(telegram_id):
        return 0

    rows = []
    seen_keys = set()
    for book in rated_books:
        if not isinstance(book, dict):
            continue

        title = book.get("book_title")
        rating = book.get("rating")
        if not isinstance(title, str) or rating not in {1, 2, 3, 4, 5}:
            continue

        title = " ".join(title.split())[:200]
        book_key = title.casefold()
        if not title or book_key in seen_keys:
            continue

        rows.append((telegram_id, book_key, title, rating))
        seen_keys.add(book_key)

    connection = _connect()
    connection.execute(
        "DELETE FROM contributed_ratings WHERE telegram_id = ?",
        (telegram_id,),
    )
    connection.executemany(
        """
        INSERT INTO contributed_ratings (
            telegram_id, book_key, book_title, rating
        ) VALUES (?, ?, ?, ?)
        """,
        rows,
    )
    connection.commit()
    connection.close()
    return len(rows)


def get_contributed_ratings():
    """Return only ratings whose users are currently opted in."""
    connection = _connect()
    rows = connection.execute(
        """
        SELECT contributed_ratings.telegram_id, book_title, rating
        FROM contributed_ratings
        JOIN users USING (telegram_id)
        WHERE users.training_consent = 1
        ORDER BY contributed_ratings.telegram_id, book_title
        """
    ).fetchall()
    connection.close()
    return rows


def get_collection_summary():
    """Return aggregate counts without exposing individual user identities."""
    connection = _connect()
    user_counts = connection.execute(
        """
        SELECT
            COUNT(*),
            COALESCE(SUM(goodreads_data IS NOT NULL), 0),
            COALESCE(SUM(training_consent = 1), 0)
        FROM users
        """
    ).fetchone()
    rating_count = connection.execute(
        "SELECT COUNT(*) FROM contributed_ratings"
    ).fetchone()[0]
    connection.close()
    return {
        "users": user_counts[0],
        "goodreads_users": user_counts[1],
        "contributing_users": user_counts[2],
        "contributed_ratings": rating_count,
    }
