import logging
import os
import sqlite3
from datetime import datetime

DB_PATH = "/data/bot.db" if os.path.isdir("/data") else "bot.db"


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS auto_replies (
                user_id INTEGER PRIMARY KEY,
                text TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                text TEXT,
                received_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)

        info = conn.execute("PRAGMA table_info(users)").fetchall()
        if not info:
            conn.execute("""
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id INTEGER UNIQUE,
                    username TEXT,
                    first_name TEXT,
                    last_seen TEXT
                )
            """)
        else:
            tg_col = next((c for c in info if c["name"] == "telegram_id"), None)
            if tg_col and tg_col["notnull"] == 1:
                logging.info("Migrating users table: telegram_id becomes nullable")
                conn.executescript("""
                    CREATE TABLE users_new (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        telegram_id INTEGER UNIQUE,
                        username TEXT,
                        first_name TEXT,
                        last_seen TEXT
                    );
                    INSERT INTO users_new (id, telegram_id, username, first_name, last_seen)
                        SELECT id, telegram_id, username, first_name, last_seen FROM users;
                    DROP TABLE users;
                    ALTER TABLE users_new RENAME TO users;
                """)


def add_user_by_telegram_id(telegram_id, username=None, first_name=None):
    now = datetime.utcnow().isoformat()
    with get_conn() as conn:
        row = conn.execute("SELECT id FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone()
        if row:
            conn.execute("""
                UPDATE users SET
                    username = COALESCE(?, username),
                    first_name = COALESCE(?, first_name),
                    last_seen = ?
                WHERE id = ?
            """, (username, first_name, now, row["id"]))
            return row["id"]
        cur = conn.execute(
            "INSERT INTO users (telegram_id, username, first_name, last_seen) VALUES (?, ?, ?, ?)",
            (telegram_id, username, first_name, now),
        )
        return cur.lastrowid


def add_user_by_username(username, first_name=None):
    username_clean = username.lstrip("@").strip()
    if not username_clean:
        raise ValueError("Username пустой")
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id FROM users WHERE LOWER(username) = LOWER(?)", (username_clean,)
        ).fetchone()
        if row:
            if first_name:
                conn.execute(
                    "UPDATE users SET first_name = COALESCE(first_name, ?) WHERE id = ?",
                    (first_name, row["id"]),
                )
            return row["id"]
        cur = conn.execute(
            "INSERT INTO users (telegram_id, username, first_name, last_seen) VALUES (NULL, ?, ?, ?)",
            (username_clean, first_name, datetime.utcnow().isoformat()),
        )
        return cur.lastrowid


def delete_user(user_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM auto_replies WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM messages WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))


def upsert_user(telegram_id, username, first_name):
    now = datetime.utcnow().isoformat()
    with get_conn() as conn:
        row = conn.execute("SELECT id FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone()
        if row:
            conn.execute(
                "UPDATE users SET username=?, first_name=?, last_seen=? WHERE id=?",
                (username, first_name, now, row["id"]),
            )
            return row["id"]
        if username:
            row = conn.execute(
                "SELECT id FROM users WHERE LOWER(username) = LOWER(?) AND telegram_id IS NULL",
                (username,),
            ).fetchone()
            if row:
                conn.execute(
                    "UPDATE users SET telegram_id=?, first_name=?, last_seen=? WHERE id=?",
                    (telegram_id, first_name, now, row["id"]),
                )
                return row["id"]
        cur = conn.execute(
            "INSERT INTO users (telegram_id, username, first_name, last_seen) VALUES (?, ?, ?, ?)",
            (telegram_id, username, first_name, now),
        )
        return cur.lastrowid


def get_user_by_internal_id(user_id):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def list_users():
    with get_conn() as conn:
        return conn.execute("""
            SELECT u.*, ar.text AS reply_text, ar.enabled AS reply_enabled
            FROM users u
            LEFT JOIN auto_replies ar ON ar.user_id = u.id
            ORDER BY (u.telegram_id IS NULL), u.last_seen DESC
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
        row = conn.execute("SELECT enabled FROM auto_replies WHERE user_id = ?", (user_id,)).fetchone()
        if not row:
            return None
        new_state = 0 if row["enabled"] else 1
        conn.execute("UPDATE auto_replies SET enabled = ? WHERE user_id = ?", (new_state, user_id))
        return bool(new_state)


def get_active_reply(telegram_id):
    with get_conn() as conn:
        row = conn.execute("""
            SELECT ar.text FROM auto_replies ar
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
        return conn.execute(
            "SELECT * FROM messages WHERE user_id = ? ORDER BY received_at DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()


def add_template(text):
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO templates (text, created_at) VALUES (?, ?)",
            (text, datetime.utcnow().isoformat()),
        )
        return cur.lastrowid


def list_templates():
    with get_conn() as conn:
        return conn.execute("SELECT * FROM templates ORDER BY created_at DESC").fetchall()


def delete_template(template_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM templates WHERE id = ?", (template_id,))

def get_user_by_telegram_id(telegram_id):
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
        ).fetchone()


def get_user_by_username(username):
    username_clean = username.lstrip("@").strip()
    if not username_clean:
        return None
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE LOWER(username) = LOWER(?)", (username_clean,)
        ).fetchone()
