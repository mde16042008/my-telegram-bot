import asyncio
import logging
import os

import uvicorn
from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from dotenv import load_dotenv
from fastapi import HTTPException

from bot import router, BOT_TOKEN
from backup import start_backup_bot, send_daily_backup
from web import app as fastapi_app
import database as db

load_dotenv()
logging.basicConfig(level=logging.INFO)

BACKUP_CRON_SECRET = os.getenv("BACKUP_CRON_SECRET", "")


@fastapi_app.get("/cron-backup")
async def cron_backup(secret: str = ""):
    if not BACKUP_CRON_SECRET or secret != BACKUP_CRON_SECRET:
        raise HTTPException(403)
    await send_daily_backup()
    return {"status": "ok"}


async def start_bot():
    PROXY_URL = os.getenv("PROXY_URL")
    if PROXY_URL:
        session = AiohttpSession(proxy=PROXY_URL)
        bot = Bot(token=BOT_TOKEN, session=session)
        logging.info(f"Бот через прокси {PROXY_URL}")
    else:
        bot = Bot(token=BOT_TOKEN)
        logging.info("Бот запущен напрямую")
    fastapi_app.state.bot = bot
    dp = Dispatcher()
    dp.include_router(router)
    await dp.start_polling(bot)


async def main():
    db.init_db()
    try:
        from bot import ensure_admin_account
        ensure_admin_account()
    except Exception as e:
        logging.warning(f"ensure_admin_account failed: {e}")

    bot_task = asyncio.create_task(start_bot())
    backup_task = asyncio.create_task(start_backup_bot())

    port = int(os.environ.get("PORT", 8080))
    config = uvicorn.Config(fastapi_app, host="0.0.0.0", port=port, log_level="info")
    server = uvicorn.Server(config)
    try:
        await server.serve()
    finally:
        bot_task.cancel()
        backup_task.cancel()


if __name__ == "__main__":
    asyncio.run(main())