import asyncio
import uvicorn
from bot import main as bot_main  # Импортируем вашу функцию запуска бота
from web import app  # Импортируем FastAPI приложение

async def run_bot():
    # Запускаем бота в фоновой задаче
    await bot_main()

if __name__ == "__main__":
    # Запускаем бота
    asyncio.create_task(run_bot())
    
    # Запускаем веб-сервер на порту 7860
    uvicorn.run(app, host="0.0.0.0", port=7860)