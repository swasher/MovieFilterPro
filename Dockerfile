# syntax=docker/dockerfile:1

# Intel 64 архитектура

# Версия playwright для «тяжёлых» слоёв Chromium (скачивание браузера + apt-библиотеки).
# ВАЖНО: должна совпадать с версией playwright в uv.lock — patchright (его использует
# scrapling StealthyFetcher) берёт бинарники из того же каталога и той же ревизии
# Chromium. Проверить: grep -A1 'name = "playwright"' uv.lock
# Если версии разойдутся, сборка упадёт на проверке в финальной стадии.
ARG PLAYWRIGHT_VERSION=1.64.1

#############################################
# Stage 1: сборка фронтенда (Svelte, pnpm)
#############################################
FROM node:24-slim AS frontend-builder

# 1. Жестко ставим стабильный pnpm 9 через npm.
# Флаг --force убирает конфликт с предустановленной заглушкой в Node 24.
RUN --mount=type=cache,target=/root/.npm \
    npm install -g pnpm@9 --force

WORKDIR /app/front

# 2. Копируем манифесты И конфиги, необходимые для 'svelte-kit sync'
COPY front/package.json front/pnpm-lock.yaml front/.npmrc* ./
COPY front/svelte.config.js* front/vite.config.js* front/tsconfig.json* ./

# 3. Спокойно ставим зависимости (pnpm 9 не блокирует esbuild по умолчанию)
RUN --mount=type=cache,target=/root/.local/share/pnpm/store \
    pnpm install --frozen-lockfile

# 4. Копируем весь исходный код и собираем
COPY front/ .
RUN pnpm run build


#############################################
# Stage 2: сборка Python-зависимостей (uv)
#############################################
FROM python:3.12-slim AS python-builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv

# Инструменты сборки нужны только на этом этапе —
# в финальный образ они не попадут.
# git обязателен: tmdbapis тянется из git (см. [tool.uv.sources] в pyproject.toml).
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libffi-dev \
    git \
    && rm -rf /var/lib/apt/lists/*

# uv ставим из официального образа, версию фиксируем (lockfile revision 3)
COPY --from=ghcr.io/astral-sh/uv:0.9.28 /uv /bin/uv

WORKDIR /app

COPY pyproject.toml uv.lock ./

# pyproject.toml + uv.lock — единственный источник зависимостей.
# Ставим их ДО копирования исходников: слой не инвалидируется правками кода.
# Проект «virtual» (не пакет), поэтому сам он не устанавливается.
# --locked = сборка упадёт, если lock рассинхронизирован с pyproject.toml.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev


#############################################
# Stage 3: Chromium для Scrapling (тяжёлый слой)
# Зависит ТОЛЬКО от PLAYWRIGHT_VERSION: не пересобирается при изменении
# python-зависимостей и кода приложения.
#############################################
FROM python:3.12-slim AS browser-builder

ARG PLAYWRIGHT_VERSION

ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

COPY --from=ghcr.io/astral-sh/uv:0.9.28 /uv /bin/uv

# Отдельный временный venv только ради CLI playwright.
# `scrapling install` = playwright install chromium + playwright install-deps,
# поэтому вызываем playwright напрямую: apt-часть ставим в финальной стадии.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv venv /opt/pw \
    && uv pip install --python /opt/pw/bin/python "playwright==${PLAYWRIGHT_VERSION}"

RUN /opt/pw/bin/python -m playwright install chromium


#############################################
# Stage 4: финальный (runtime) образ
#############################################
FROM python:3.12-slim

ARG PLAYWRIGHT_VERSION

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

# Установка supervisor для управления процессами
RUN apt-get update && apt-get install -y --no-install-recommends supervisor \
    && rm -rf /var/lib/apt/lists/*

# Системные библиотеки Chromium (`playwright install-deps`).
# Слой зависит только от версии playwright, а не от зависимостей приложения:
# временный venv удаляется в том же RUN, в образ он не попадает.
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    python -m venv /opt/pw \
    && /opt/pw/bin/pip install --no-cache-dir --disable-pip-version-check \
        "playwright==${PLAYWRIGHT_VERSION}" \
    && /opt/pw/bin/python -m playwright install-deps chromium \
    && rm -rf /opt/pw

# Готовый Chromium из browser-builder-стадии
COPY --from=browser-builder /ms-playwright /ms-playwright

# Готовое python-окружение из builder-стадии
COPY --from=python-builder /opt/venv /opt/venv

# Проверка согласованности: playwright и patchright должны указывать на
# установленную ревизию Chromium. Ловит ситуацию «обновили uv.lock,
# а PLAYWRIGHT_VERSION в Dockerfile забыли».
RUN python - <<'PY'
import json
import os
import pathlib
import sys
import sysconfig

site = pathlib.Path(sysconfig.get_paths()['purelib'])
browsers_root = pathlib.Path(os.environ['PLAYWRIGHT_BROWSERS_PATH'])

def revisions(package):
    data = json.loads((site / package / 'driver/package/browsers.json').read_text())
    return {b['name']: b['revision'] for b in data['browsers'] if b.get('installByDefault')}

playwright_rev = revisions('playwright')
patchright_rev = revisions('patchright')

if playwright_rev['chromium'] != patchright_rev['chromium']:
    sys.exit(f'playwright/patchright ревизии Chromium разошлись: {playwright_rev} vs {patchright_rev}')

chromium_dir = browsers_root / f"chromium-{playwright_rev['chromium']}"
if not chromium_dir.is_dir():
    sys.exit(f'Chromium {playwright_rev["chromium"]} не найден в {browsers_root}. '
             'Обновите PLAYWRIGHT_VERSION в Dockerfile под uv.lock.')

print('Chromium OK:', chromium_dir)
PY

RUN mkdir -p /app/backup_torrents /app/logs /app/media /app/cache

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
