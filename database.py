import sqlite3
from datetime import datetime

import os

DB_PATH = "/data/bot.db" if os.path.isdir("/data") else "bot.db"


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER UNIQUE NOT NULL,
                username TEXT,
                first_name TEXT,
                last_seen TEXT
            );
            CREATE TABLE IF NOT EXISTS auto_replies (
                user_id INTEGER PRIMARY KEY,
                text TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                text TEXT,
                received_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
        """)


def upsert_user(telegram_id, username, first_name):
    now = datetime.utcnow().isoformat()
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO users (telegram_id, username, first_name, last_seen)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(telegram_id) DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name,
                last_seen = excluded.last_seen
        """, (telegram_id, username, first_name, now))
        row = conn.execute(
            "SELECT id FROM users WHERE telegram_id = ?", (telegram_id,)
        ).fetchone()
        return row["id"]


def get_user_by_internal_id(user_id):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def list_users():
    with get_conn() as conn:
        return conn.execute("""
            SELECT u.*, ar.text AS reply_text, ar.enabled AS reply_enabled
            FROM users u
            LEFT JOIN auto_replies ar ON ar.user_id = u.id
            ORDER BY u.last_seen DESC
        """).fetchall()


def set_auto_reply(user_id, text, enabled=True):
    now = datetime.utcnow().isoformat()
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO auto_replies (user_id, text, enabled, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                text = excluded.text,
                enabled = excluded.enabled,
                updated_at = excluded.updated_at
        """, (user_id, text, 1 if enabled else 0, now))


def toggle_auto_reply(user_id):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT enabled FROM auto_replies WHERE user_id = ?", (user_id,)
        ).fetchone()
        if not row:
            return None
        new_state = 0 if row["enabled"] else 1
        conn.execute(
            "UPDATE auto_replies SET enabled = ? WHERE user_id = ?",
            (new_state, user_id),
        )
        return bool(new_state)


def get_active_reply(telegram_id):
    with get_conn() as conn:
        row = conn.execute("""
            SELECT ar.text
            FROM auto_replies ar
            JOIN users u ON u.id = ar.user_id
            WHERE u.telegram_id = ? AND ar.enabled = 1
        """, (telegram_id,)).fetchone()
        return row["text"] if row else None


def save_message(user_id, text):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO messages (user_id, text, received_at) VALUES (?, ?, ?)",
            (user_id, text, datetime.utcnow().isoformat()),
        )


def get_messages(user_id, limit=10):
    with get_conn() as conn:
        return conn.execute("""
            SELECT * FROM messages WHERE user_id = ?
            ORDER BY received_at DESC LIMIT ?
        """, (user_id, limit)).fetchall()