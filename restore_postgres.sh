#!/usr/bin/env bash
set -euo pipefail

# ------------------------------------------------------------------
# Восстановление PostgreSQL-дампа на dev-машине.
# База пересоздается: DROP + CREATE, затем заливка дампа.
# Настройки подключения берутся из .env (POSTGRES_*).
# Использование: ./restore_postgres.sh <dump_file> [--yes]
# Поддерживает: custom-формат pg_dump -Fc (*.dump) и plain SQL (*.sql)
# ------------------------------------------------------------------

CONTAINER_NAME="${CONTAINER_NAME:-postgres-mfp}"

usage() {
    cat <<EOF
Использование: $(basename "$0") <dump_file> [--yes]

  dump_file   *.dump (pg_dump -Fc) или *.sql (plain SQL)
  --yes, -y   не спрашивать подтверждение
  --help, -h  эта справка

Настройки берутся из .env: POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB.
Контейнер: ${CONTAINER_NAME} (можно переопределить переменной CONTAINER_NAME).
EOF
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${ENV_FILE:-${SCRIPT_DIR}/.env}"

if [[ ! -f "${ENV_FILE}" ]]; then
    echo "ОШИБКА: .env не найден: ${ENV_FILE}" >&2
    exit 1
fi

# Читаем значение ключа из .env БЕЗ source: иначе bash-подстановка
# ($var, !, `...`) ломается на спецсимволах в других строках (SECRET_KEY и т.п.).
load_env_key() {
    local key="$1" line val
    line="$(grep -E "^[[:space:]]*(export[[:space:]]+)?${key}[[:space:]]*=" "${ENV_FILE}" \
        | grep -vE "^[[:space:]]*#" | tail -n 1 | tr -d '\r' || true)"
    if [[ -z "${line}" ]]; then
        echo "ОШИБКА: в ${ENV_FILE} нет ${key}" >&2
        return 1
    fi
    val="${line#*=}"
    val="$(printf '%s' "${val}" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
    if [[ "${val}" == \"*\" && "${val}" == *\" && ${#val} -ge 2 ]]; then
        val="${val:1:${#val}-2}"
    elif [[ "${val}" == \'*\' && "${val}" == *\' && ${#val} -ge 2 ]]; then
        val="${val:1:${#val}-2}"
    else
        val="${val%% #*}"
        val="$(printf '%s' "${val}" | sed -e 's/[[:space:]]*$//')"
    fi
    printf '%s' "${val}"
}

POSTGRES_USER="$(load_env_key POSTGRES_USER)"
POSTGRES_PASSWORD="$(load_env_key POSTGRES_PASSWORD)"
POSTGRES_DB="$(load_env_key POSTGRES_DB)"

DUMP_FILE=""
ASSUME_YES=0
for arg in "$@"; do
    case "${arg}" in
        -y|--yes)  ASSUME_YES=1 ;;
        -h|--help) usage; exit 0 ;;
        -*)        echo "ОШИБКА: неизвестный параметр: ${arg}" >&2; usage; exit 1 ;;
        *)
            if [[ -n "${DUMP_FILE}" ]]; then
                echo "ОШИБКА: указано больше одного файла дампа." >&2
                usage
                exit 1
            fi
            DUMP_FILE="${arg}"
            ;;
    esac
done

if [[ -z "${DUMP_FILE}" ]]; then
    usage
    exit 1
fi
if [[ ! -f "${DUMP_FILE}" ]]; then
    echo "ОШИБКА: файл не найден: ${DUMP_FILE}" >&2
    exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
    echo "ОШИБКА: docker не найден в PATH." >&2
    exit 1
fi

echo "==> Проверка: контейнер '${CONTAINER_NAME}' запущен..."
if ! docker ps --format '{{.Names}}' | grep -qx "${CONTAINER_NAME}"; then
    echo "ОШИБКА: контейнер '${CONTAINER_NAME}' не найден среди запущенных." >&2
    docker ps --format '{{.Names}}' >&2 || true
    exit 1
fi

if [[ "${POSTGRES_DB}" == "postgres" || "${POSTGRES_DB}" == "template0" || "${POSTGRES_DB}" == "template1" ]]; then
    echo "ОШИБКА: отказываюсь пересоздавать системную базу '${POSTGRES_DB}'." >&2
    exit 1
fi

echo "Цель: контейнер=${CONTAINER_NAME} db=${POSTGRES_DB} user=${POSTGRES_USER} файл=${DUMP_FILE}"
echo "ВНИМАНИЕ: база '${POSTGRES_DB}' будет УДАЛЕНА и создана заново."
echo "Останови dev-сервер / huey перед запуском."
if [[ "${ASSUME_YES}" -eq 0 ]]; then
    read -r -p "Продолжить? [y/N] " confirm
    [[ "${confirm}" == "y" || "${confirm}" == "Y" ]] || { echo "Отмена."; exit 1; }
fi

PSQL_BASE=(docker exec -e PGPASSWORD="${POSTGRES_PASSWORD}" "${CONTAINER_NAME}"
    psql -U "${POSTGRES_USER}" -d postgres -v ON_ERROR_STOP=1)

echo "==> Пересоздание базы '${POSTGRES_DB}'..."
# WITH (FORCE) закрывает оставшиеся подключения к базе (PostgreSQL 13+).
"${PSQL_BASE[@]}" -c "DROP DATABASE IF EXISTS \"${POSTGRES_DB}\" WITH (FORCE);"
"${PSQL_BASE[@]}" -c "CREATE DATABASE \"${POSTGRES_DB}\";"

# Дамп подается на stdin: это избавляет от docker cp и путей, которые
# Git Bash (MSYS2) на Windows конвертирует в виндовые (C:/...).
if [[ "${DUMP_FILE}" == *.sql ]]; then
    echo "==> Восстановление SQL-дампа через psql..."
    docker exec -i -e PGPASSWORD="${POSTGRES_PASSWORD}" "${CONTAINER_NAME}" \
        psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
        -v ON_ERROR_STOP=1 --single-transaction < "${DUMP_FILE}"
else
    echo "==> Восстановление дампа через pg_restore..."
    docker exec -i -e PGPASSWORD="${POSTGRES_PASSWORD}" "${CONTAINER_NAME}" \
        pg_restore -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
        --no-owner --no-privileges --single-transaction --exit-on-error < "${DUMP_FILE}"
fi

echo "==> Готово. База '${POSTGRES_DB}' восстановлена из ${DUMP_FILE}."
