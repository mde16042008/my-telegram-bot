import asyncio
import logging
import os

from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import Command
from aiogram.types import Message, FSInputFile, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
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


# ---------- Хелперы ----------

def resolve_contact(target: str):
    """
    Ищет контакт по:
      - внутреннему id (1, 2, 3...)
      - @username / username
      - telegram_id (число, если не найден внутренний id)
      - номеру телефона
    """
    target = target.strip()
    if not target:
        return None
    if target.lstrip("-").isdigit():
        num = int(target)
        c = db.get_contact(num)
        if c:
            return c
        c = db.get_contact_by_telegram_id(num)
        if c:
            return c
        return db.get_contact_by_phone(target)
    if target.startswith("+") or target.replace(" ", "").replace("-", "").isdigit():
        c = db.get_contact_by_phone(target)
        if c:
            return c
    return db.get_contact_by_username(target)


def ensure_admin_account():
    """Гарантирует, что в system_users есть запись admin, связанная с telegram_id админа."""
    su = db.get_system_user_by_telegram_id(ADMIN_ID)
    if su:
        return su
    existing = db.get_system_user_by_username("admin")
    if existing:
        db.update_contact  # no-op, оставлено для читаемости
        with db.get_conn() as conn:
            conn.execute(
                "UPDATE system_users SET telegram_id = ?, role = 'admin' WHERE id = ?",
                (ADMIN_ID, existing["id"]),
            )
        return db.get_system_user_by_username("admin")
    default_password = os.getenv("ADMIN_PASSWORD", "admin123")
    db.create_system_user("admin", default_password, role="admin",
                          display_name="Администратор", telegram_id=ADMIN_ID)
    logging.warning(f"Создан системный админ 'admin' с паролем '{default_password}' — СМЕНИТЕ ЕГО!")
    return db.get_system_user_by_username("admin")


# ---------- Команды администратора ----------

@router.message(F.from_user.id == ADMIN_ID, Command("start"))
async def admin_start(message: Message):
    await message.answer(
        "Привет, админ!\n\n"
        "Во всех командах вместо <id> можно указывать: внутренний id, @username, telegram_id или телефон.\n\n"
        "/users — все контакты\n"
        "/add_user <@username|tg_id|телефон> [текст] — добавить вручную\n"
        "/set_phone <id> <телефон> — задать телефон контакту\n"
        "/ask_phone <id> — попросить у пользователя телефон через Telegram\n"
        "/assign <id> <оператор> — назначить контакт оператору\n"
        "/del_user <id> — удалить контакт\n"
        "/reply <id> <текст> — задать автоответ\n"
        "/toggle <id> — вкл/выкл автоответ\n"
        "/inbox <id> — последние сообщения\n"
        "/templates — все шаблоны\n"
        "/add_template <текст> — добавить общий шаблон\n"
        "/del_template <id> — удалить шаблон\n"
        "/operators — список операторов\n"
        "/add_operator <логин> <пароль> <имя> — создать оператора\n"
        "/del_operator <логин> — удалить оператора\n"
        "/backup — скачать базу"
    )


@router.message(F.from_user.id == ADMIN_ID, Command("users"))
async def admin_users(message: Message):
    contacts = db.list_contacts(include_all=True)
    if not contacts:
        await message.answer("Контактов нет.")
        return
    lines = []
    for c in contacts:
        status = "✅" if c["reply_enabled"] else "❌"
        username = f"@{c['username']}" if c["username"] else "—"
        phone = c["phone"] or "—"
        operator = c["operator_username"] or "админ"
        lines.append(
            f"{status} id={c['id']} {username} | тел: {phone} | "
            f"tg: {c['telegram_id'] or '—'} | у: {operator}"
        )
    # Разбиваем на части, если >30 строк
    text = "Контакты:\n" + "\n".join(lines)
    for chunk in [text[i:i+4000] for i in range(0, len(text), 4000)]:
        await message.answer(chunk)


@router.message(F.from_user.id == ADMIN_ID, Command("add_user"))
async def admin_add_user(message: Message):
    parts = message.text.split(maxsplit=2)
    if len(parts) < 2:
        await message.answer(
            "Использование:\n"
            "/add_user @username [текст]\n"
            "/add_user 123456789 [текст]\n"
            "/add_user +37360000000 [текст]"
        )
        return
    target = parts[1]
    reply_text = parts[2] if len(parts) > 2 else None

    contact_id = None
    try:
        if target.startswith("+") or (target.replace(" ", "").replace("-", "").isdigit() and len(target) > 9):
            phone = target
            existing = db.get_contact_by_phone(phone)
            if existing:
                contact_id = existing["id"]
            else:
                contact_id = db.add_contact(phone=phone)
        elif target.lstrip("-").isdigit():
            tg_id = int(target)
            existing = db.get_contact_by_telegram_id(tg_id)
            if existing:
                contact_id = existing["id"]
            else:
                contact_id = db.add_contact(telegram_id=tg_id)
        else:
            username = target.lstrip("@")
            existing = db.get_contact_by_username(username)
            if existing:
                contact_id = existing["id"]
            else:
                contact_id = db.add_contact(username=username)
    except Exception as e:
        await message.answer(f"Ошибка: {e}")
        return

    if reply_text:
        db.set_auto_reply(contact_id, reply_text, enabled=True)
        await message.answer(f"✅ {target} добавлен (id={contact_id}) с автоответом:\n{reply_text}")
    else:
        await message.answer(f"✅ {target} добавлен (id={contact_id}).")


@router.message(F.from_user.id == ADMIN_ID, Command("set_phone"))
async def admin_set_phone(message: Message):
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        await message.answer("Использование: /set_phone <id|@username|tg_id> <телефон>")
        return
    contact = resolve_contact(parts[1])
    if not contact:
        await message.answer(f"Контакт «{parts[1]}» не найден")
        return
    db.update_contact(contact["id"], phone=parts[2].strip())
    await message.answer(f"✅ Телефон контакта id={contact['id']} установлен: {parts[2]}")


@router.message(F.from_user.id == ADMIN_ID, Command("ask_phone"))
async def admin_ask_phone(message: Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Использование: /ask_phone <id|@username|tg_id>")
        return
    contact = resolve_contact(parts[1])
    if not contact:
        await message.answer(f"Контакт «{parts[1]}» не найден")
        return
    if not contact["telegram_id"]:
        await message.answer(
            f"У контакта «{parts[1]}» нет telegram_id — попросить телефон нельзя.\n"
            f"Можно задать вручную: /set_phone {contact['id']} +37360000000"
        )
        return
    try:
        kb = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="📱 Поделиться контактом", request_contact=True)]],
            resize_keyboard=True, one_time_keyboard=True,
        )
        await message.bot.send_message(
            chat_id=contact["telegram_id"],
            text="Пожалуйста, поделитесь своим номером телефона, нажав на кнопку ниже.",
            reply_markup=kb,
        )
        await message.answer(f"📨 Запрос отправлен контакту id={contact['id']}.")
    except Exception as e:
        await message.answer(f"Ошибка отправки: {e}")


@router.message(F.from_user.id == ADMIN_ID, Command("assign"))
async def admin_assign(message: Message):
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        await message.answer("Использование: /assign <id|@username|tg_id> <логин_оператора>")
        return
    contact = resolve_contact(parts[1])
    if not contact:
        await message.answer(f"Контакт «{parts[1]}» не найден")
        return
    operator = db.get_system_user_by_username(parts[2].lstrip("@"))
    if not operator:
        await message.answer(f"Оператор «{parts[2]}» не найден")
        return
    db.update_contact(contact["id"], assigned_to=operator["id"])
    await message.answer(f"✅ Контакт id={contact['id']} назначен оператору @{operator['username']}")


@router.message(F.from_user.id == ADMIN_ID, Command("del_user"))
async def admin_del_user(message: Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Использование: /del_user <id|@username|tg_id>")
        return
    contact = resolve_contact(parts[1])
    if not contact:
        await message.answer(f"Контакт «{parts[1]}» не найден")
        return
    db.delete_contact(contact["id"])
    await message.answer(f"🗑 Контакт id={contact['id']} удалён")


@router.message(F.from_user.id == ADMIN_ID, Command("reply"))
async def admin_reply(message: Message):
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        await message.answer("Использование: /reply <id|@username|tg_id> <текст>")
        return
    contact = resolve_contact(parts[1])
    if not contact:
        await message.answer(f"Контакт «{parts[1]}» не найден")
        return
    db.set_auto_reply(contact["id"], parts[2], enabled=True)
    await message.answer(f"✅ Автоответ для id={contact['id']} установлен:\n{parts[2]}")


@router.message(F.from_user.id == ADMIN_ID, Command("toggle"))
async def admin_toggle(message: Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Использование: /toggle <id|@username|tg_id>")
        return
    contact = resolve_contact(parts[1])
    if not contact:
        await message.answer(f"Контакт «{parts[1]}» не найден")
        return
    state = db.toggle_auto_reply(contact["id"])
    if state is None:
        await message.answer("У этого контакта не настроен автоответ")
        return
    await message.answer(f"Автоответ {'включён ✅' if state else 'выключен ❌'}")


@router.message(F.from_user.id == ADMIN_ID, Command("inbox"))
async def admin_inbox(message: Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Использование: /inbox <id|@username|tg_id>")
        return
    contact = resolve_contact(parts[1])
    if not contact:
        await message.answer(f"Контакт «{parts[1]}» не найден")
        return
    msgs = db.get_messages(contact["id"], limit=15)
    if not msgs:
        await message.answer("Сообщений нет")
        return
    lines = [f"[{m['received_at']}] {m['text']}" for m in msgs]
    await message.answer(f"Последние сообщения (id={contact['id']}):\n" + "\n".join(lines))


@router.message(F.from_user.id == ADMIN_ID, Command("templates"))
async def admin_templates(message: Message):
    templates = db.list_templates(include_shared=True)
    if not templates:
        await message.answer("Шаблонов нет.")
        return
    lines = [f"id={t['id']}: {t['text']}" for t in templates]
    await message.answer("Шаблоны:\n" + "\n".join(lines))


@router.message(F.from_user.id == ADMIN_ID, Command("add_template"))
async def admin_add_template(message: Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Использование: /add_template <текст>")
        return
    tid = db.add_template(parts[1], owner_id=None)  # общий шаблон
    await message.answer(f"✅ Шаблон id={tid} добавлен:\n{parts[1]}")


@router.message(F.from_user.id == ADMIN_ID, Command("del_template"))
async def admin_del_template(message: Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Использование: /del_template <id>")
        return
    db.delete_template(int(parts[1]), is_admin=True)
    await message.answer(f"Шаблон id={parts[1]} удалён")


@router.message(F.from_user.id == ADMIN_ID, Command("operators"))
async def admin_operators(message: Message):
    users = db.list_system_users()
    if not users:
        await message.answer("Операторов нет.")
        return
    lines = [f"{u['role']}: {u['username']} ({u['display_name'] or '—'})" for u in users]
    await message.answer("Системные пользователи:\n" + "\n".join(lines))


@router.message(F.from_user.id == ADMIN_ID, Command("add_operator"))
async def admin_add_operator(message: Message):
    parts = message.text.split(maxsplit=3)
    if len(parts) < 4:
        await message.answer("Использование: /add_operator <логин> <пароль> <имя>")
        return
    login, password, name = parts[1], parts[2], parts[3]
    if db.get_system_user_by_username(login):
        await message.answer(f"Логин «{login}» уже занят.")
        return
    db.create_system_user(login, password, role="operator", display_name=name)
    await message.answer(f"✅ Оператор @{login} создан.")


@router.message(F.from_user.id == ADMIN_ID, Command("del_operator"))
async def admin_del_operator(message: Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Использование: /del_operator <логин>")
        return
    op = db.get_system_user_by_username(parts[1].lstrip("@"))
    if not op:
        await message.answer("Оператор не найден.")
        return
    if op["role"] == "admin":
        await message.answer("Нельзя удалить админа.")
        return
    db.delete_system_user(op["id"])
    await message.answer(f"🗑 Оператор @{op['username']} удалён.")


@router.message(F.from_user.id == ADMIN_ID, Command("backup"))
async def admin_backup(message: Message):
    if not os.path.exists(db.DB_PATH):
        await message.answer("Файл БД не найден.")
        return
    await message.answer_document(FSInputFile(db.DB_PATH, filename="bot.db"), caption="💾 Бэкап")


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


# ---------- Приём телефона от пользователя (request_contact) ----------

@router.message(F.contact)
async def receive_contact(message: Message):
    contact_info = message.contact
    if not contact_info:
        return
    phone = contact_info.phone_number
    if not phone.startswith("+"):
        phone = "+" + phone
    tg_id = contact_info.user_id  # это ID пользователя, который поделился (если поделился собой)
    if tg_id and tg_id != message.from_user.id:
        # Поделились чужим контактом — игнорируем или сохраняем отдельно
        await message.answer("Спасибо, но нужен именно ваш контакт.")
        return
    contact = db.get_contact_by_telegram_id(message.from_user.id)
    if contact:
        db.update_contact(contact["id"], phone=phone)
    else:
        db.add_contact(telegram_id=message.from_user.id,
                       username=message.from_user.username,
                       first_name=message.from_user.first_name,
                       phone=phone)
    await message.answer("Спасибо! Ваш номер сохранён.", reply_markup=ReplyKeyboardRemove())


# ---------- Бизнес-сообщения ----------

@router.business_message()
async def handle_business_message(message: Message):
    user = message.from_user
    if user.id == ADMIN_ID:
        return

    logging.info(
        f"[BIZ] from={user.id} @{user.username} text={message.text!r} "
        f"biz_id={message.business_connection_id!r} chat={message.chat.id}"
    )

    contact = db.find_contact_for_reply(user.id, user.username)
    if contact:
        logging.info(f"[BIZ] found existing contact id={contact['id']}")
        db.update_contact(
            contact["id"],
            telegram_id=user.id,
            username=user.username,
            first_name=user.first_name,
        )
    else:
        contact_id = db.add_contact(
            telegram_id=user.id, username=user.username, first_name=user.first_name,
        )
        contact = db.get_contact(contact_id)
        logging.info(f"[BIZ] created new contact id={contact['id']}")

    db.save_message(contact["id"], message.text)

    reply_text = db.get_active_reply_for_contact(contact["id"])
    logging.info(f"[BIZ] contact_id={contact['id']} reply_text={reply_text!r}")

    if not reply_text:
        logging.info("[BIZ] no active auto-reply — skipping send")
        return

    if not message.business_connection_id:
        logging.error("[BIZ] business_connection_id is None — cannot reply")
        return

    try:
        sent = await message.bot.send_message(
            business_connection_id=message.business_connection_id,
            chat_id=message.chat.id,
            text=reply_text,
        )
        logging.info(f"[BIZ] reply sent OK, message_id={sent.message_id}")
    except Exception as e:
        logging.exception(f"[BIZ] send failed: {e}")


async def main():
    db.init_db()
    ensure_admin_account()
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
