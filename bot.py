import asyncio
import logging
import os

from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import Command
from aiogram.types import Message, FSInputFile
from aiogram.client.session.aiohttp import AiohttpSession
from dotenv import load_dotenv

import database as db

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не задан")
if not ADMIN_ID:
    raise RuntimeError("ADMIN_ID не задан")

logging.basicConfig(level=logging.INFO)

router = Router()


# ---------- Команды администратора ----------

@router.message(F.from_user.id == ADMIN_ID, Command("start"))
async def admin_start(message: Message):
    await message.answer(
        "Привет, админ!\n\n"
        "/users — список пользователей\n"
        "/reply <id> <текст> — задать автоответ\n"
        "/toggle <id> — вкл/выкл автоответ\n"
        "/inbox <id> — последние сообщения\n"
        "/templates — список шаблонов\n"
        "/add_template <текст> — добавить шаблон\n"
        "/del_template <id> — удалить шаблон\n"
        "/backup — скачать базу данных"
    )


@router.message(F.from_user.id == ADMIN_ID, Command("users"))
async def admin_users(message: Message):
    users = db.list_users()
    if not users:
        await message.answer("Пока никто не писал.")
        return
    lines = []
    for u in users:
        status = "✅" if u["reply_enabled"] else "❌"
        username = f"@{u['username']}" if u["username"] else "—"
        lines.append(f"{status} id={u['id']} {username} ({u['first_name']}) tg={u['telegram_id']}")
    await message.answer("Пользователи:\n" + "\n".join(lines))


@router.message(F.from_user.id == ADMIN_ID, Command("reply"))
async def admin_reply(message: Message):
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        await message.answer("Использование: /reply <id> <текст ответа>")
        return
    try:
        user_id = int(parts[1])
    except ValueError:
        await message.answer("id должен быть числом")
        return
    if not db.get_user_by_internal_id(user_id):
        await message.answer(f"Пользователь с id={user_id} не найден")
        return
    db.set_auto_reply(user_id, parts[2], enabled=True)
    await message.answer(f"✅ Автоответ для id={user_id} установлен:\n{parts[2]}")


@router.message(F.from_user.id == ADMIN_ID, Command("toggle"))
async def admin_toggle(message: Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Использование: /toggle <id>")
        return
    try:
        user_id = int(parts[1])
    except ValueError:
        await message.answer("id должен быть числом")
        return
    state = db.toggle_auto_reply(user_id)
    if state is None:
        await message.answer("У этого пользователя не настроен автоответ")
        return
    await message.answer(f"Автоответ {'включён ✅' if state else 'выключен ❌'}")


@router.message(F.from_user.id == ADMIN_ID, Command("inbox"))
async def admin_inbox(message: Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Использование: /inbox <id>")
        return
    try:
        user_id = int(parts[1])
    except ValueError:
        await message.answer("id должен быть числом")
        return
    msgs = db.get_messages(user_id, limit=10)
    if not msgs:
        await message.answer("Сообщений нет")
        return
    lines = [f"[{m['received_at']}] {m['text']}" for m in msgs]
    await message.answer("Последние сообщения:\n" + "\n".join(lines))


@router.message(F.from_user.id == ADMIN_ID, Command("templates"))
async def admin_templates(message: Message):
    templates = db.list_templates()
    if not templates:
        await message.answer("Шаблонов нет. Добавьте: /add_template <текст>")
        return
    lines = [f"id={t['id']}: {t['text']}" for t in templates]
    await message.answer("Шаблоны:\n" + "\n".join(lines))


@router.message(F.from_user.id == ADMIN_ID, Command("add_template"))
async def admin_add_template(message: Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Использование: /add_template <текст>")
        return
    tid = db.add_template(parts[1])
    await message.answer(f"✅ Шаблон id={tid} добавлен:\n{parts[1]}")


@router.message(F.from_user.id == ADMIN_ID, Command("del_template"))
async def admin_del_template(message: Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Использование: /del_template <id>")
        return
    try:
        tid = int(parts[1])
    except ValueError:
        await message.answer("id должен быть числом")
        return
    db.delete_template(tid)
    await message.answer(f"Шаблон id={tid} удалён")


@router.message(F.from_user.id == ADMIN_ID, Command("backup"))
async def admin_backup(message: Message):
    if not os.path.exists(db.DB_PATH):
        await message.answer("Файл базы данных ещё не создан.")
        return
    try:
        doc = FSInputFile(db.DB_PATH, filename="bot.db")
        await message.answer_document(doc, caption="💾 Бэкап базы данных")
    except Exception as e:
        logging.error(f"Backup error: {e}")
        await message.answer(f"Ошибка бэкапа: {e}")


# ---------- Whoami ----------

@router.message(Command("whoami"))
async def whoami(message: Message):
    await message.answer(
        f"Ваш Telegram ID: `{message.from_user.id}`\n"
        f"Username: @{message.from_user.username or '—'}\n"
        f"ADMIN_ID: `{ADMIN_ID}`\n"
        f"Совпадает: {'✅ да' if message.from_user.id == ADMIN_ID else '❌ нет'}",
        parse_mode="Markdown",
    )


# ---------- Бизнес-сообщения ----------

@router.business_message()
async def handle_business_message(message: Message):
    user = message.from_user
    if user.id == ADMIN_ID:
        return
    user_id = db.upsert_user(user.id, user.username, user.first_name)
    db.save_message(user_id, message.text)
    reply_text = db.get_active_reply(user.id)
    if reply_text:
        try:
            await message.bot.send_message(
                business_connection_id=message.business_connection_id,
                chat_id=message.chat.id,
                text=reply_text,
            )
        except Exception as e:
            logging.error(f"Не удалось отправить бизнес-ответ: {e}")


# ---------- Локальный запуск (на Render используется app.py) ----------

async def main():
    db.init_db()
    PROXY_URL = os.getenv("PROXY_URL")
    if PROXY_URL:
        session = AiohttpSession(proxy=PROXY_URL)
        bot = Bot(token=BOT_TOKEN, session=session)
    else:
        bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)
    logging.info("Бот запущен, слушаю сообщения...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
