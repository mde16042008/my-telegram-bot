import logging
import os
import shutil

from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import Command
from aiogram.types import Message, FSInputFile

import database as db

BACKUP_BOT_TOKEN = os.getenv("BACKUP_BOT_TOKEN", "")
BACKUP_CHAT_ID = int(os.getenv("BACKUP_CHAT_ID", "0"))

router = Router()


@router.message(F.from_user.id == BACKUP_CHAT_ID, Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "🤖 Бэкап-бот\n\n"
        "/backup — получить текущую базу\n"
        "Отправьте файл .db — восстановить базу"
    )


@router.message(F.from_user.id == BACKUP_CHAT_ID, Command("backup"))
async def cmd_backup(message: Message):
    if not os.path.exists(db.DB_PATH):
        await message.answer("❌ Файл базы данных не найден")
        return
    await message.answer_document(
        FSInputFile(db.DB_PATH, filename="bot.db"),
        caption="💾 Бэкап базы данных",
    )


@router.message(F.from_user.id == BACKUP_CHAT_ID, F.document)
async def receive_restore(message: Message):
    doc = message.document
    logging.info(f"[RESTORE] received file: {doc.file_name}, size={doc.file_size}, db_path={db.DB_PATH}")
    if not doc.file_name.endswith(".db"):
        await message.answer(f"❌ Нужен файл .db, а пришёл {doc.file_name}")
        return

    file = await message.bot.get_file(doc.file_id)
    temp_path = "restore_temp.db"
    try:
        await message.bot.download_file(file.file_path, temp_path)
        logging.info(f"[RESTORE] downloaded to {temp_path}, size={os.path.getsize(temp_path)}")
        shutil.copy(temp_path, db.DB_PATH)
        os.remove(temp_path)
        logging.info(f"[RESTORE] copied to {db.DB_PATH}, size={os.path.getsize(db.DB_PATH)}")
        await message.answer(
            "✅ База восстановлена.\n"
            "Перезапустите сервис на Render (Manual Deploy → Restart)."
        )
    except Exception as e:
        logging.exception(f"[RESTORE] failed: {e}")
        await message.answer(f"❌ Ошибка восстановления: {e}")


async def start_backup_bot():
    if not BACKUP_BOT_TOKEN or not BACKUP_CHAT_ID:
        logging.warning("BACKUP_BOT_TOKEN/BACKUP_CHAT_ID не заданы — бэкап-бот выключен")
        return
    bot = Bot(token=BACKUP_BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)
    logging.info("Backup bot started")
    await dp.start_polling(bot)


async def send_daily_backup():
    if not BACKUP_BOT_TOKEN or not BACKUP_CHAT_ID:
        return
    if not os.path.exists(db.DB_PATH):
        return
    bot = Bot(token=BACKUP_BOT_TOKEN)
    try:
        await bot.send_document(
            chat_id=BACKUP_CHAT_ID,
            document=FSInputFile(db.DB_PATH, filename="bot_backup.db"),
            caption="🗓 Ежедневный бэкап",
        )
        logging.info("Daily backup sent")
    except Exception as e:
        logging.error(f"Daily backup failed: {e}")
    finally:
        await bot.session.close()
