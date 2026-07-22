# Intel 64 архитектура
FROM python:3.12-slim

# Устанавливаем переменные окружения для экономии памяти
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV NODE_OPTIONS="--max_old_space_size=1024"

# Устанавливаем рабочую директорию
WORKDIR /app

# Устанавливаем инструменты сборки
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libffi-dev \
    nodejs \
    npm \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Создаем директорию /torrents_hotfolder
RUN mkdir -p /torrents_hotfolder

# Копируем файл зависимостей Python
COPY requirements.txt /app

# Устанавливаем зависимости Python
RUN pip install --no-cache-dir -r requirements.txt

# Копируем проект
COPY . /app

# Копируем файл .env.production и переименовываем его в .env
COPY .env.production /app/.env

# Собираем frontend Svelte с ограничением памяти
WORKDIR /app/front
RUN npm install && npm run build

# Возвращаемся в рабочую директорию
WORKDIR /app

# Создаем временный файл для проверки
RUN echo "$(date +'%Y-%m-%d %H:%M:%S')" > /app/timestamp

# Копируем entrypoint.sh (для одного контейнера)
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Открываем порты
EXPOSE 8008

# Устанавливаем entrypoint
ENTRYPOINT ["/app/entrypoint.sh"]

# По умолчанию запускаем web-режим.
CMD ["web"]