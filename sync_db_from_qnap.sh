#!/usr/bin/env bash
set -euo pipefail

# ------------------------------------------------------------------
# Полный цикл: QNAP -> dev.
#   1. По SSH заходим на QNAP и снимаем дамп PostgreSQL из docker-контейнера.
#   2. Стримим дамп по SSH на dev-машину в локальный файл.
#   3. Пересоздаем dev-базу (DROP + CREATE) и восстанавливаем в нее дамп.
#
# Использование: ./sync_db_from_qnap.sh [--yes] [--dir DIR] [--no-restore] [--delete-dump]
# Подробности: ./sync_db_from_qnap.sh --help
#
# Настройки dev-базы берутся из .env: POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB.
# Настройки QNAP-базы (prod) — из .env.production: POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB.
# SSH на QNAP — под пользователем QNAP_USER (по умолчанию admin), по ключу, без пароля.
# ------------------------------------------------------------------

# ------------------------------------ #
#              КОНСТАНТЫ               #
# ------------------------------------ #
QNAP_SSH_HOST="${QNAP_SSH_HOST:-qnap}"
QNAP_USER="${QNAP_USER:-admin}"
QNAP_CONTAINER_NAME="${QNAP_CONTAINER_NAME:-mfp-postgres}"
# Путь к docker на QNAP. Пусто = искать автоматически (Container Station
# не добавляет свой bin в PATH неинтерактивного ssh-шелла).
QNAP_DOCKER_BIN="${QNAP_DOCKER_BIN:-}"
DEV_CONTAINER_NAME="${DEV_CONTAINER_NAME:-postgres-mfp}"
DUMP_PREFIX="dump"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${ENV_FILE:-${SCRIPT_DIR}/.env}"
PROD_ENV_FILE="${PROD_ENV_FILE:-${SCRIPT_DIR}/.env.production}"

usage() {
    cat <<EOF
Использование: $(basename "$0") [опции]

Снимает дамп с QNAP по SSH и восстанавливает его в dev-базу.

  --yes, -y     не спрашивать подтверждение перед пересозданием dev-базы
  --dir DIR     куда сохранить дамп (по умолчанию: ${SCRIPT_DIR}/backups)
  --no-restore  только забрать дамп, dev-базу не трогать
  --delete-dump удалить локальный файл дампа после успешного восстановления
  --help, -h    эта справка

.env (dev):  POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB
.env.production (QNAP/prod): POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB
  (можно переопределить переменными окружения QNAP_POSTGRES_*)

Константы в скрипте (можно переопределить переменными окружения):
  QNAP_SSH_HOST=${QNAP_SSH_HOST}
  QNAP_USER=${QNAP_USER}
  QNAP_CONTAINER_NAME=${QNAP_CONTAINER_NAME}
  QNAP_DOCKER_BIN=${QNAP_DOCKER_BIN:-<авто>}
  DEV_CONTAINER_NAME=${DEV_CONTAINER_NAME}
EOF
}

# Читаем значение ключа из .env БЕЗ source: иначе bash-подстановка
# ($var, !, `...`) ломается на спецсимволах в других строках (SECRET_KEY и т.п.).
# Второй аргумент — файл (по умолчанию ENV_FILE).
load_env_key() {
    local key="$1" file="${2:-${ENV_FILE}}" line val
    line="$(grep -E "^[[:space:]]*(export[[:space:]]+)?${key}[[:space:]]*=" "${file}" \
        | grep -vE "^[[:space:]]*#" | tail -n 1 | tr -d '\r' || true)"
    if [[ -z "${line}" ]]; then
        echo "ОШИБКА: в ${file} нет ${key}" >&2
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

# Значение из окружения имеет приоритет над .env.
env_value() {
    local key="$1" override
    override="${!key-}"
    if [[ -n "${override}" ]]; then
        printf '%s' "${override}"
        return 0
    fi
    load_env_key "${key}"
}

# Значение из файла, с приоритетом переменной окружения с ДРУГИМ именем.
# Нужно для prod: в .env.production ключи называются POSTGRES_*,
# а переопределить их можно через QNAP_POSTGRES_* (чтобы не конфликтовать с dev).
env_value_alt() {
    local override_key="$1" file_key="$2" file="$3" override
    override="${!override_key-}"
    if [[ -n "${override}" ]]; then
        printf '%s' "${override}"
        return 0
    fi
    load_env_key "${file_key}" "${file}"
}

# ------------------------------------ #
#           РАЗБОР АРГУМЕНТОВ          #
# ------------------------------------ #
ASSUME_YES=0
DO_RESTORE=1
DELETE_DUMP=0
DUMP_DIR="${SCRIPT_DIR}/backups"

while [[ $# -gt 0 ]]; do
    case "$1" in
        -y|--yes)     ASSUME_YES=1 ;;
        --no-restore) DO_RESTORE=0 ;;
        --delete-dump) DELETE_DUMP=1 ;;
        --dir)
            if [[ $# -lt 2 ]]; then
                echo "ОШИБКА: --dir требует путь." >&2
                usage
                exit 1
            fi
            DUMP_DIR="$2"
            shift
            ;;
        -h|--help)    usage; exit 0 ;;
        *)
            echo "ОШИБКА: неизвестный параметр: $1" >&2
            usage
            exit 1
            ;;
    esac
    shift
done

if [[ ! -f "${ENV_FILE}" ]]; then
    echo "ОШИБКА: .env не найден: ${ENV_FILE}" >&2
    exit 1
fi

if [[ ! -f "${PROD_ENV_FILE}" ]]; then
    echo "ОШИБКА: .env.production не найден: ${PROD_ENV_FILE}" >&2
    exit 1
fi

for tool in ssh docker; do
    if ! command -v "${tool}" >/dev/null 2>&1; then
        echo "ОШИБКА: ${tool} не найден в PATH." >&2
        exit 1
    fi
done

# -------------------- dev --------------------
POSTGRES_USER="$(env_value POSTGRES_USER || true)"
POSTGRES_PASSWORD="$(env_value POSTGRES_PASSWORD || true)"
POSTGRES_DB="$(env_value POSTGRES_DB || true)"

# -------------------- QNAP (prod) --------------------
# Креды прод-базы лежат в .env.production под именами POSTGRES_*.
# Переопределение через окружение — QNAP_POSTGRES_*.
QNAP_POSTGRES_USER="$(env_value_alt QNAP_POSTGRES_USER POSTGRES_USER "${PROD_ENV_FILE}" || true)"
QNAP_POSTGRES_PASSWORD="$(env_value_alt QNAP_POSTGRES_PASSWORD POSTGRES_PASSWORD "${PROD_ENV_FILE}" || true)"
QNAP_POSTGRES_DB="$(env_value_alt QNAP_POSTGRES_DB POSTGRES_DB "${PROD_ENV_FILE}" || true)"

MISSING_PROD=()
[[ -n "${QNAP_POSTGRES_USER}" ]]     || MISSING_PROD+=("POSTGRES_USER")
[[ -n "${QNAP_POSTGRES_PASSWORD}" ]] || MISSING_PROD+=("POSTGRES_PASSWORD")
[[ -n "${QNAP_POSTGRES_DB}" ]]       || MISSING_PROD+=("POSTGRES_DB")

MISSING=()
if [[ "${DO_RESTORE}" -eq 1 ]]; then
    [[ -n "${POSTGRES_USER}" ]]     || MISSING+=("POSTGRES_USER")
    [[ -n "${POSTGRES_PASSWORD}" ]] || MISSING+=("POSTGRES_PASSWORD")
    [[ -n "${POSTGRES_DB}" ]]       || MISSING+=("POSTGRES_DB")
fi

if [[ ${#MISSING_PROD[@]} -gt 0 || ${#MISSING[@]} -gt 0 ]]; then
    if [[ ${#MISSING_PROD[@]} -gt 0 ]]; then
        echo "ОШИБКА: в ${PROD_ENV_FILE} не заданы: ${MISSING_PROD[*]}" >&2
    fi
    if [[ ${#MISSING[@]} -gt 0 ]]; then
        echo "ОШИБКА: в ${ENV_FILE} не заданы: ${MISSING[*]}" >&2
    fi
    exit 1
fi

# ------------------------------------ #
#         ПРОВЕРКИ ПЕРЕД ЗАПИСЬЮ       #
# ------------------------------------ #
if [[ "${DO_RESTORE}" -eq 1 ]]; then
    case "${POSTGRES_DB}" in
        postgres|template0|template1)
            echo "ОШИБКА: отказываюсь пересоздавать системную базу '${POSTGRES_DB}'." >&2
            exit 1
            ;;
    esac

    echo "==> Проверка: dev-контейнер '${DEV_CONTAINER_NAME}' запущен..."
    if ! docker ps --format '{{.Names}}' | grep -qx "${DEV_CONTAINER_NAME}"; then
        echo "ОШИБКА: контейнер '${DEV_CONTAINER_NAME}' не найден среди запущенных." >&2
        docker ps --format '{{.Names}}' >&2 || true
        exit 1
    fi
fi

TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
DUMP_FILENAME="${DUMP_PREFIX}_${QNAP_POSTGRES_DB}_${TIMESTAMP}.dump"
DUMP_PATH="${DUMP_DIR}/${DUMP_FILENAME}"

mkdir -p "${DUMP_DIR}"

# ------------------------------------ #
#           ДАМП С QNAP ПО SSH         #
# ------------------------------------ #
# Значения передаем позиционными аргументами, экранируя их локальным %q:
# ssh склеивает аргументы через пробел, поэтому кавычки ставим заранее.
remote_args="$(printf '%q' "${QNAP_CONTAINER_NAME}") $(printf '%q' "${QNAP_POSTGRES_USER}") $(printf '%q' "${QNAP_POSTGRES_PASSWORD}") $(printf '%q' "${QNAP_POSTGRES_DB}") $(printf '%q' "${QNAP_DOCKER_BIN}")"

echo "==> Источник: ${QNAP_USER}@${QNAP_SSH_HOST}:${QNAP_CONTAINER_NAME} db=${QNAP_POSTGRES_DB}"
echo "==> Дамп:     ${DUMP_PATH}"

cleanup_partial() {
    if [[ -f "${DUMP_PATH}" ]]; then
        rm -f "${DUMP_PATH}"
        echo "Частично скачанный дамп удален: ${DUMP_PATH}" >&2
    fi
}
trap cleanup_partial ERR

if ! ssh -o BatchMode=yes "${QNAP_USER}@${QNAP_SSH_HOST}" "bash -s -- ${remote_args}" <<'REMOTE' > "${DUMP_PATH}"
set -euo pipefail
container="$1"
pguser="$2"
pgpass="$3"
pgdb="$4"
docker_bin="${5:-}"

# Container Station на QNAP не добавляет свой bin в PATH неинтерактивного
# ssh-шелла, поэтому если docker не задан явно — ищем бинарь сами.
if [[ -z "${docker_bin}" ]]; then
    docker_bin="$(command -v docker 2>/dev/null || true)"
fi
if [[ -z "${docker_bin}" ]]; then
    for candidate in \
        /share/*/.qpkg/container-station/bin/docker \
        /share/*/.qpkg/*/bin/docker \
        /usr/local/bin/docker \
        /opt/bin/docker; do
        if [[ -x "${candidate}" ]]; then
            docker_bin="${candidate}"
            break
        fi
    done
fi
if [[ -z "${docker_bin}" ]]; then
    echo "ОШИБКА: docker не найден на удаленном хосте." >&2
    echo "Задай путь явно: QNAP_DOCKER_BIN=/share/.../container-station/bin/docker ./sync_db_from_qnap.sh" >&2
    exit 1
fi
echo "docker: ${docker_bin}" >&2

if ! "${docker_bin}" ps --format '{{.Names}}' | grep -qx "${container}"; then
    echo "ОШИБКА: контейнер '${container}' не найден среди запущенных на удаленном хосте." >&2
    "${docker_bin}" ps --format '{{.Names}}' >&2 || true
    exit 1
fi

"${docker_bin}" exec -e PGPASSWORD="${pgpass}" "${container}" pg_dump --version >&2
exec "${docker_bin}" exec -e PGPASSWORD="${pgpass}" "${container}" \
    pg_dump -U "${pguser}" -d "${pgdb}" -F c -Z 9
REMOTE
then
    cleanup_partial
    trap - ERR
    echo "ОШИБКА: не удалось снять дамп с ${QNAP_USER}@${QNAP_SSH_HOST}." >&2
    echo "Проверь SSH-доступ (ключ), имя контейнера и POSTGRES_* в ${PROD_ENV_FILE}." >&2
    echo "Если docker не в PATH — задай QNAP_DOCKER_BIN (например, /share/CACHEDEV1_DATA/.qpkg/container-station/bin/docker)." >&2
    exit 1
fi

trap - ERR

if [[ ! -s "${DUMP_PATH}" ]]; then
    rm -f "${DUMP_PATH}"
    echo "ОШИБКА: получен пустой дамп." >&2
    exit 1
fi

if [[ "$(head -c 5 "${DUMP_PATH}")" != "PGDMP" ]]; then
    rm -f "${DUMP_PATH}"
    echo "ОШИБКА: файл не похож на pg_dump custom-формат (нет заголовка PGDMP)." >&2
    exit 1
fi

echo "==> Дамп получен: $(ls -lh "${DUMP_PATH}" | awk '{print $5}')"

if [[ "${DO_RESTORE}" -eq 0 ]]; then
    echo "==> --no-restore: dev-база не тронута."
    echo "Готово: ${DUMP_PATH}"
    exit 0
fi

# ------------------------------------ #
#        ВОССТАНОВЛЕНИЕ В DEV          #
# ------------------------------------ #
echo "Цель: контейнер=${DEV_CONTAINER_NAME} db=${POSTGRES_DB} user=${POSTGRES_USER} файл=${DUMP_PATH}"
echo "ВНИМАНИЕ: база '${POSTGRES_DB}' будет УДАЛЕНА и создана заново."
echo "Останови dev-сервер / huey перед запуском."
if [[ "${ASSUME_YES}" -eq 0 ]]; then
    read -r -p "Продолжить? [y/N] " confirm
    [[ "${confirm}" == "y" || "${confirm}" == "Y" ]] || { echo "Отмена."; exit 1; }
fi

PSQL_BASE=(docker exec -e PGPASSWORD="${POSTGRES_PASSWORD}" "${DEV_CONTAINER_NAME}"
    psql -U "${POSTGRES_USER}" -d postgres -v ON_ERROR_STOP=1)

echo "==> Пересоздание базы '${POSTGRES_DB}'..."
# WITH (FORCE) закрывает оставшиеся подключения к базе (PostgreSQL 13+).
"${PSQL_BASE[@]}" -c "DROP DATABASE IF EXISTS \"${POSTGRES_DB}\" WITH (FORCE);"
"${PSQL_BASE[@]}" -c "CREATE DATABASE \"${POSTGRES_DB}\";"

# Дамп подается на stdin: это избавляет от docker cp и путей, которые
# Git Bash (MSYS2) на Windows конвертирует в виндовые (C:/...).
echo "==> Восстановление дампа через pg_restore..."
docker exec -i -e PGPASSWORD="${POSTGRES_PASSWORD}" "${DEV_CONTAINER_NAME}" \
    pg_restore -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
    --no-owner --no-privileges --single-transaction --exit-on-error < "${DUMP_PATH}"

echo "==> Готово. База '${POSTGRES_DB}' восстановлена из ${DUMP_PATH}."

if [[ "${DELETE_DUMP}" -eq 1 ]]; then
    rm -f "${DUMP_PATH}"
    echo "==> Локальный дамп удален (--delete-dump)."
fi
