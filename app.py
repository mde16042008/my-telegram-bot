import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiohttp import web  # Используем aiohttp для веб-сервера
from dotenv import load_dotenv

# Импортируем ваши обработчики и роутер из bot.py
# (предполагается, что bot.py лежит в той же папке)
from bot import router, BOT_TOKEN

load_dotenv()

logging.basicConfig(level=logging.INFO)

# --- Веб-сервер для health-check и предотвращения сна ---
async def health_check(request):
    return web.Response(text="Bot is alive!")

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    # Render передаёт порт в переменной окружения PORT
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logging.info(f"Health-check server started on port {port}")

# --- Запуск бота ---
async def start_bot():
    # Проверьте, нужен ли вам прокси на Render.
    # Если прямой доступ к Telegram работает, строку с PROXY_URL можно убрать.
    PROXY_URL = os.getenv("PROXY_URL") # Например, "http://127.0.0.1:8080"
    if PROXY_URL:
        session = AiohttpSession(proxy=PROXY_URL)
        bot = Bot(token=BOT_TOKEN, session=session)
    else:
        bot = Bot(token=BOT_TOKEN)

    dp = Dispatcher()
    dp.include_router(router)
    logging.info("Starting bot polling...")
    await dp.start_polling(bot)

async def main():
    # Запускаем веб-сервер и бота параллельно
    await asyncio.gather(
        start_web_server(),
        start_bot()
    )

if __name__ == "__main__":
    asyncio.run(main())