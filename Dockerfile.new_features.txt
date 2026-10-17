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
    git \
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

# Установка supervisor и браузеров для обхода Cloudflare в kinozal_scan.
# chromium (apt) — резервный браузер + он тянет все системные библиотеки,
#   которые нужны Chrome for Testing (тот приходит без зависимостей).
# Chrome for Testing — "брендовый" Google Chrome, к нему Cloudflare
#   доверяет заметно больше, чем к Debian Chromium.
# chromedriver rtfox_browser скачивает и патчит сам на первом запуске.
# xvfb — запасной вариант: headed-браузер без дисплея, если headless не пройдёт челлендж.
# fonts-liberation — шрифты, чтобы страницы корректно рендерились в headless.
RUN apt-get update && apt-get install -y --no-install-recommends \
    supervisor \
    chromium \
    xvfb \
    fonts-liberation \
    curl \
    unzip \
    && rm -rf /var/lib/apt/lists/*

RUN set -ex; \
    CHROME_VERSION=$(curl -fsSL https://googlechromelabs.github.io/chrome-for-testing/last-known-good-versions-with-downloads.json \
        | python3 -c "import sys, json; print(json.load(sys.stdin)['channels']['Stable']['version'])"); \
    echo "Chrome for Testing version: ${CHROME_VERSION}"; \
    curl -fsSL -o /tmp/chrome-linux64.zip "https://storage.googleapis.com/chrome-for-testing-public/${CHROME_VERSION}/linux64/chrome-linux64.zip"; \
    unzip -q /tmp/chrome-linux64.zip -d /opt; \
    mv /opt/chrome-linux64 /opt/chrome; \
    rm /tmp/chrome-linux64.zip

ENV KINOZAL_BROWSER_BINARY=/opt/chrome/chrome

RUN mkdir -p /torrents_hotfolder /app/logs

# Готовое python-окружение из builder-стадии
COPY --from=python-builder /opt/venv /opt/venv

# Код проекта (Django и всё остальное)
COPY . /app

# Готовая статика Svelte (перезаписывает front/, если он попал в COPY выше)
COPY --from=frontend-builder /app/front/build /app/front/build

# .env.production -> .env
#COPY .env.production /app/.env

# Конфиг supervisord
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Временная метка сборки (как в оригинале)
RUN echo "$(date +'%Y-%m-%d %H:%M:%S')" > /app/timestamp

COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

EXPOSE 8009

# Запуск миграций, затем supervisord (web + worker)
CMD ["/app/entrypoint.sh"]