# Используем Python 3.11 (легкая версия)
FROM python:3.11-slim

# Отключаем создание .pyc файлов и буферизацию вывода (чтобы логи шли сразу)
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Устанавливаем рабочую папку внутри контейнера
WORKDIR /app

# Устанавливаем системные зависимости и tzdata для работы со временем
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем часовой пояс по умолчанию
ENV TZ=Europe/Moscow

# Копируем файл зависимостей и устанавливаем их
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем весь код проекта
COPY . .

# Команда запуска (важно: host 0.0.0.0 открывает доступ для телефона)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]