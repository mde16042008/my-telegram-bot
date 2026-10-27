import hashlib
import logging
import os
import secrets
import sqlite3
from datetime import datetime

DB_PATH = "/data/bot.db" if os.path.isdir("/data") else "bot.db"


# ---------- Подключение и хеширование ----------

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def hash_password(password, salt=None):
    if salt is None:
        salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 100_000)
    return f"{salt}${digest.hex()}"


def verify_password(password, stored):
    try:
        salt, _ = stored.split("$", 1)
        return hash_password(password, salt) == stored
    except Exception:
        return False


# ---------- Инициализация и миграция ----------

def init_db():
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS system_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'operator',
                display_name TEXT,
                telegram_id INTEGER,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS contacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                assigned_to INTEGER,
                telegram_id INTEGER,
                username TEXT,
                first_name TEXT,
                phone TEXT,
                last_seen TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (assigned_to) REFERENCES system_users(id) ON DELETE SET NULL
            );
            CREATE TABLE IF NOT EXISTS auto_replies (
                contact_id INTEGER PRIMARY KEY,
                text TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT,
                FOREIGN KEY (contact_id) REFERENCES contacts(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                contact_id INTEGER NOT NULL,
                text TEXT,
                received_at TEXT NOT NULL,
                FOREIGN KEY (contact_id) REFERENCES contacts(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id INTEGER,
                text TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (owner_id) REFERENCES system_users(id) ON DELETE CASCADE
            );
        """)

        # ---- Миграция старых таблиц (users/auto_replies/messages) ----
        info = conn.execute("PRAGMA table_info(users)").fetchall()
        if info:
            logging.info("Миграция старых данных users → contacts…")
            admin = conn.execute(
                "SELECT id FROM system_users WHERE role='admin' ORDER BY id LIMIT 1"
            ).fetchone()
            admin_id = admin["id"] if admin else None
            old_users = conn.execute("SELECT * FROM users").fetchall()
            for ou in old_users:
                conn.execute("""
                    INSERT INTO contacts (assigned_to, telegram_id, username, first_name, last_seen, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (admin_id, ou["telegram_id"], ou["username"], ou["first_name"],
                      ou["last_seen"], datetime.utcnow().isoformat()))
                new_id = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
                old_reply = conn.execute(
                    "SELECT * FROM auto_replies WHERE user_id = ?", (ou["id"],)
                ).fetchone()
                if old_reply:
                    conn.execute("""
                        INSERT INTO auto_replies (contact_id, text, enabled, updated_at)
                        VALUES (?, ?, ?, ?)
                    """, (new_id, old_reply["text"], old_reply["enabled"], old_reply["updated_at"]))
                old_msgs = conn.execute(
                    "SELECT * FROM messages WHERE user_id = ?", (ou["id"],)
                ).fetchall()
                for m in old_msgs:
                    conn.execute(
                        "INSERT INTO messages (contact_id, text, received_at) VALUES (?, ?, ?)",
                        (new_id, m["text"], m["received_at"]),
                    )
            conn.executescript("""
                DROP TABLE IF EXISTS auto_replies;
                DROP TABLE IF EXISTS messages;
                DROP TABLE IF EXISTS users;
            """)
            logging.info("Миграция завершена.")


# ---------- Системные пользователи (админ/операторы) ----------

def create_system_user(username, password, role="operator", display_name=None, telegram_id=None):
    with get_conn() as conn:
        cur = conn.execute("""
            INSERT INTO system_users (username, password_hash, role, display_name, telegram_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (username.lower(), hash_password(password), role, display_name, telegram_id,
              datetime.utcnow().isoformat()))
        return cur.lastrowid


def get_system_user_by_username(username):
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM system_users WHERE username = ?", (username.lower(),)
        ).fetchone()


def get_system_user_by_telegram_id(telegram_id):
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM system_users WHERE telegram_id = ?", (telegram_id,)
        ).fetchone()


def list_system_users():
    with get_conn() as conn:
        return conn.execute("SELECT * FROM system_users ORDER BY id").fetchall()


def delete_system_user(user_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM system_users WHERE id = ?", (user_id,))


def change_password(user_id, new_password):
    with get_conn() as conn:
        conn.execute(
            "UPDATE system_users SET password_hash = ? WHERE id = ?",
            (hash_password(new_password), user_id),
        )


# ---------- Контакты ----------

def add_contact(assigned_to=None, telegram_id=None, username=None, first_name=None,
                phone=None, last_seen=None):
    with get_conn() as conn:
        cur = conn.execute("""
            INSERT INTO contacts (assigned_to, telegram_id, username, first_name, phone, last_seen, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (assigned_to, telegram_id, username, first_name, phone,
              last_seen or datetime.utcnow().isoformat(),
              datetime.utcnow().isoformat()))
        return cur.lastrowid


def update_contact(contact_id, **fields):
    allowed = {"telegram_id", "username", "first_name", "phone", "assigned_to", "last_seen"}
    keys = [k for k in fields if k in allowed]
    if not keys:
        return
    with get_conn() as conn:
        set_clause = ", ".join(f"{k} = ?" for k in keys)
        values = [fields[k] for k in keys] + [contact_id]
        conn.execute(f"UPDATE contacts SET {set_clause} WHERE id = ?", values)


def get_contact(contact_id):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM contacts WHERE id = ?", (contact_id,)).fetchone()


def get_contact_by_telegram_id(tg_id):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM contacts WHERE telegram_id = ?", (tg_id,)).fetchone()


def get_contact_by_username(username):
    username_clean = username.lstrip("@").strip()
    if not username_clean:
        return None
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM contacts WHERE LOWER(username) = LOWER(?)", (username_clean,)
        ).fetchone()


def get_contact_by_phone(phone):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM contacts WHERE phone = ?", (phone,)).fetchone()


def list_contacts(assigned_to=None, include_all=False):
    with get_conn() as conn:
        if include_all:
            return conn.execute("""
                SELECT c.*, ar.text AS reply_text, ar.enabled AS reply_enabled,
                       su.username AS operator_username
                FROM contacts c
                LEFT JOIN auto_replies ar ON ar.contact_id = c.id
                LEFT JOIN system_users su ON su.id = c.assigned_to
                ORDER BY c.last_seen DESC
            """).fetchall()
        return conn.execute("""
            SELECT c.*, ar.text AS reply_text, ar.enabled AS reply_enabled
            FROM contacts c
            LEFT JOIN auto_replies ar ON ar.contact_id = c.id
            WHERE c.assigned_to = ? OR c.assigned_to IS NULL
            ORDER BY c.last_seen DESC
        """, (assigned_to,)).fetchall()


def delete_contact(contact_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM contacts WHERE id = ?", (contact_id,))


def find_contact_for_reply(tg_id, username):
    """Ищет контакт по telegram_id, потом по username (для привязки ранее добавленных)."""
    contact = get_contact_by_telegram_id(tg_id)
    if contact:
        return contact
    if username:
        return get_contact_by_username(username)
    return None


# ---------- Автоответы ----------

def set_auto_reply(contact_id, text, enabled=True):
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO auto_replies (contact_id, text, enabled, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(contact_id) DO UPDATE SET
                text = excluded.text, enabled = excluded.enabled, updated_at = excluded.updated_at
        """, (contact_id, text, 1 if enabled else 0, datetime.utcnow().isoformat()))


def toggle_auto_reply(contact_id):
    with get_conn() as conn:
        row = conn.execute("SELECT enabled FROM auto_replies WHERE contact_id = ?", (contact_id,)).fetchone()
        if not row:
            return None
        new_state = 0 if row["enabled"] else 1
        conn.execute("UPDATE auto_replies SET enabled = ? WHERE contact_id = ?", (new_state, contact_id))
        return bool(new_state)


def get_active_reply_for_contact(contact_id):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT text FROM auto_replies WHERE contact_id = ? AND enabled = 1", (contact_id,)
        ).fetchone()
        return row["text"] if row else None


# ---------- Сообщения ----------

def save_message(contact_id, text):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO messages (contact_id, text, received_at) VALUES (?, ?, ?)",
            (contact_id, text, datetime.utcnow().isoformat()),
        )


def get_messages(contact_id, limit=100):
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM messages WHERE contact_id = ? ORDER BY received_at DESC LIMIT ?",
            (contact_id, limit),
        ).fetchall()


# ---------- Шаблоны ----------

def add_template(text, owner_id=None):
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO templates (owner_id, text, created_at) VALUES (?, ?, ?)",
            (owner_id, text, datetime.utcnow().isoformat()),
        )
        return cur.lastrowid


def list_templates(owner_id=None, include_shared=True):
    with get_conn() as conn:
        if include_shared:
            return conn.execute("""
                SELECT * FROM templates
                WHERE owner_id = ? OR owner_id IS NULL
                ORDER BY created_at DESC
            """, (owner_id,)).fetchall()
        return conn.execute(
            "SELECT * FROM templates WHERE owner_id = ? ORDER BY created_at DESC", (owner_id,)
        ).fetchall()


def delete_template(template_id, requester_id=None, is_admin=False):
    with get_conn() as conn:
        if is_admin:
            conn.execute("DELETE FROM templates WHERE id = ?", (template_id,))
        else:
            conn.execute(
                "DELETE FROM templates WHERE id = ? AND owner_id = ?", (template_id, requester_id)
            )