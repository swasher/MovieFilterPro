#!/usr/bin/env bash
set -euo pipefail

# ------------------------------------------------------------------
# QNAP -> файл.
#   1. По SSH заходим на QNAP и снимаем дамп PostgreSQL из docker-контейнера.
#   2. Стримим дамп по SSH на локальную машину и сохраняем в файл
#      (по умолчанию — в ./backups).
# Базы не трогаются: только чтение QNAP и запись локального файла.
#
# Использование: ./copydb_qnap_to_file.sh [--dir DIR]
# Подробности: ./copydb_qnap_to_file.sh --help
#
# Настройки QNAP-базы (prod) берутся из .env.production: POSTGRES_USER,
# POSTGRES_PASSWORD, POSTGRES_DB (переопределение — QNAP_POSTGRES_*).
# SSH на QNAP — под пользователем QNAP_USER (по умолчанию admin), по ключу.
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
DUMP_PREFIX="dump"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROD_ENV_FILE="${PROD_ENV_FILE:-${SCRIPT_DIR}/.env.production}"

usage() {
    cat <<EOF
Использование: $(basename "$0") [опции]

Снимает дамп PostgreSQL с QNAP по SSH и сохраняет его в локальный файл.

  --dir DIR     куда сохранить дамп (по умолчанию: ${SCRIPT_DIR}/backups)
  --help, -h    эта справка

Поддерживает: custom-формат pg_dump -Fc (*.dump).

.env.production (QNAP/prod): POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB
  (можно переопределить переменными окружения QNAP_POSTGRES_*)

Константы в скрипте (можно переопределить переменными окружения):
  QNAP_SSH_HOST=${QNAP_SSH_HOST}
  QNAP_USER=${QNAP_USER}
  QNAP_CONTAINER_NAME=${QNAP_CONTAINER_NAME}
  QNAP_DOCKER_BIN=${QNAP_DOCKER_BIN:-<авто>}
EOF
}

# Читаем значение ключа из .env БЕЗ source: иначе bash-подстановка
# ($var, !, `...`) ломается на спецсимволах в других строках (SECRET_KEY и т.п.).
load_env_key() {
    local key="$1" line val
    line="$(grep -E "^[[:space:]]*(export[[:space:]]+)?${key}[[:space:]]*=" "${PROD_ENV_FILE}" \
        | grep -vE "^[[:space:]]*#" | tail -n 1 | tr -d '\r' || true)"
    if [[ -z "${line}" ]]; then
        echo "ОШИБКА: в ${PROD_ENV_FILE} нет ${key}" >&2
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

# Значение из файла, с приоритетом переменной окружения с ДРУГИМ именем.
# В .env.production ключи называются POSTGRES_*, а переопределить их можно
# через QNAP_POSTGRES_* (чтобы не конфликтовать с dev-переменными).
env_value_alt() {
    local override_key="$1" file_key="$2" override
    override="${!override_key-}"
    if [[ -n "${override}" ]]; then
        printf '%s' "${override}"
        return 0
    fi
    load_env_key "${file_key}"
}

# ------------------------------------ #
#           РАЗБОР АРГУМЕНТОВ          #
# ------------------------------------ #
DUMP_DIR="${SCRIPT_DIR}/backups"

while [[ $# -gt 0 ]]; do
    case "$1" in
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

if [[ ! -f "${PROD_ENV_FILE}" ]]; then
    echo "ОШИБКА: .env.production не найден: ${PROD_ENV_FILE}" >&2
    exit 1
fi

for tool in ssh; do
    if ! command -v "${tool}" >/dev/null 2>&1; then
        echo "ОШИБКА: ${tool} не найден в PATH." >&2
        exit 1
    fi
done

# -------------------- QNAP (prod) --------------------
# Креды прод-базы лежат в .env.production под именами POSTGRES_*.
# Переопределение через окружение — QNAP_POSTGRES_*.
QNAP_POSTGRES_USER="$(env_value_alt QNAP_POSTGRES_USER POSTGRES_USER || true)"
QNAP_POSTGRES_PASSWORD="$(env_value_alt QNAP_POSTGRES_PASSWORD POSTGRES_PASSWORD || true)"
QNAP_POSTGRES_DB="$(env_value_alt QNAP_POSTGRES_DB POSTGRES_DB || true)"

MISSING_PROD=()
[[ -n "${QNAP_POSTGRES_USER}" ]]     || MISSING_PROD+=("POSTGRES_USER")
[[ -n "${QNAP_POSTGRES_PASSWORD}" ]] || MISSING_PROD+=("POSTGRES_PASSWORD")
[[ -n "${QNAP_POSTGRES_DB}" ]]       || MISSING_PROD+=("POSTGRES_DB")

if [[ ${#MISSING_PROD[@]} -gt 0 ]]; then
    echo "ОШИБКА: в ${PROD_ENV_FILE} не заданы: ${MISSING_PROD[*]}" >&2
    exit 1
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
    echo "Задай путь явно: QNAP_DOCKER_BIN=/share/.../container-station/bin/docker ./copydb_qnap_to_file.sh" >&2
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
echo "==> Готово: ${DUMP_PATH}"
