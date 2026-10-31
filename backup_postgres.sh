#!/usr/bin/env bash
set -euo pipefail

# ------------------------------------------------------------------
# Дамп PostgreSQL из docker-контейнера на хост (в текущую папку).
# Использование: ./backup_postgres.sh на хосте, где крутится контейнер, то есть qnap
# ------------------------------------------------------------------

# --- Явные переменные (подставь настоящие значения) ---
CONTAINER_NAME="postgres_container"
POSTGRES_USER="postgres"
POSTGRES_PASSWORD="changeme"
POSTGRES_DB="mydb"

# Имя файла дампа на хосте (в текущей папке)
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
DUMP_FILENAME="dump_${POSTGRES_DB}_${TIMESTAMP}.dump"
DUMP_HOST_PATH="./${DUMP_FILENAME}"

echo "==> Проверка: контейнер '${CONTAINER_NAME}' запущен..."
if ! docker ps --format '{{.Names}}' | grep -qx "${CONTAINER_NAME}"; then
    echo "ОШИБКА: контейнер '${CONTAINER_NAME}' не найден среди запущенных."
    echo "Запущенные контейнеры:"
    docker ps --format '{{.Names}}'
    exit 1
fi

echo "==> Снятие дампа: ${CONTAINER_NAME} -> ${DUMP_HOST_PATH}"
docker exec \
    -e PGPASSWORD="${POSTGRES_PASSWORD}" \
    "${CONTAINER_NAME}" \
    pg_dump -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -F c -Z 9 > "${DUMP_HOST_PATH}"

echo "==> Готово:"
ls -lh "${DUMP_HOST_PATH}"
