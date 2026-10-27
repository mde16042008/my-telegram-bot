FROM python:3.11-slim

# Создаем пользователя, как того требует HF Spaces
RUN useradd -m -u 1000 user
WORKDIR /app

# Копируем и устанавливаем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем весь остальной код
COPY . .

# Даем права на запись для папки с кодом (на случай если /data не используется)
RUN chown -R user:user /app
USER user

# HF Spaces ожидает порт 7860
ENV PORT=7860
EXPOSE 7860

# Запускаем наш веб-сервер (он же будет запускать и бота)
CMD ["python", "run.py"]