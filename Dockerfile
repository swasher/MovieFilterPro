# syntax=docker/dockerfile:1

# Intel 64 архитектура

#############################################
# Stage 1: сборка фронтенда (Svelte, pnpm)
#############################################
FROM node:24-slim AS frontend-builder

# 1. Жестко ставим стабильный pnpm 9 через npm.
# Флаг --force убирает конфликт с предустановленной заглушкой в Node 24.
RUN npm install -g pnpm@9 --force

WORKDIR /app/front

# 2. Копируем манифесты И конфиги, необходимые для 'svelte-kit sync'
COPY front/package.json front/pnpm-lock.yaml front/.npmrc* ./
COPY front/svelte.config.js* front/vite.config.js* front/tsconfig.json* ./

# 3. Спокойно ставим зависимости (pnpm 9 не блокирует esbuild по умолчанию)
RUN pnpm install --frozen-lockfile

# 4. Копируем весь исходный код и собираем
COPY front/ .
RUN pnpm run build


#############################################
# Stage 2: сборка Python-зависимостей
#############################################
FROM python:3.12-slim AS python-builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Инструменты сборки нужны только на этом этапе —
# в финальный образ они не попадут
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt


#############################################
# Stage 3: финальный (runtime) образ
#############################################
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Установка supervisor для управления процессами
RUN apt-get update && apt-get install -y --no-install-recommends supervisor \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /torrents_hotfolder /app/logs

# Готовое python-окружение из builder-стадии
COPY --from=python-builder /opt/venv /opt/venv

# Код проекта (Django и всё остальное)
COPY . /app

# Готовая статика Svelte (перезаписывает front/, если он попал в COPY выше)
COPY --from=frontend-builder /app/front/build /app/front/build

# .env.production -> .env
COPY .env.production /app/.env

# Конфиг supervisord
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Временная метка сборки (как в оригинале)
RUN echo "$(date +'%Y-%m-%d %H:%M:%S')" > /app/timestamp

COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

EXPOSE 8009

# Запуск миграций, затем supervisord (web + worker)
CMD ["/app/entrypoint.sh"]