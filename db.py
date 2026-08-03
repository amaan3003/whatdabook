import sqlite3
import json

def init_db():
    conn = sqlite3.connect("users.db")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            telegram_id INTEGER PRIMARY KEY,
            name TEXT,
            goodreads_data TEXT
        )
    """)
    conn.commit()
    conn.close()
    

def save_user(telegram_id, name):
    conn = sqlite3.connect("users.db")
    conn.execute(
        "INSERT OR REPLACE INTO users (telegram_id, name) VALUES (?, ?)",
        (telegram_id, name)
    )
    conn.commit()
    conn.close()
    
def get_user(telegram_id):
    conn = sqlite3.connect("users.db")
    cursor = conn.execute(
        "SELECT name, goodreads_data FROM users WHERE telegram_id = ?",
        (telegram_id,)
    )
    row = cursor.fetchone()
    conn.close()
    return row

def save_goodreads(telegram_id, goodreads_data):
    conn = sqlite3.connect("users.db")
    json_string = json.dumps(goodreads_data)        
    conn.execute(
        "UPDATE users SET goodreads_data = ? WHERE telegram_id = ?",
        (json_string, telegram_id)
    )
    conn.commit()
    conn.close()