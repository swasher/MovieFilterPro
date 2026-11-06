#!/usr/bin/env bash
set -euo pipefail

# ------------------------------------------------------------------
# Обратный к copydb_qnap_to_dev.sh: dev -> QNAP (prod).
#   1. Берем последний дамп из ./backups (или указанный через --file).
#   2. (по умолчанию) Снимаем страховочный дамп прод-базы в ./backups.
#   3. Останавливаем приложение на QNAP (Django/huey).
#   4. По SSH стримим дамп на QNAP и восстанавливаем в базу:
#      DROP DATABASE ... WITH (FORCE) + CREATE + pg_restore (или psql для *.sql).
#   5. Заново поднимаем приложение (в том числе если восстановление упало).
#
# Использование: ./copydb_dev_to_qnap.sh [опции]
# Подробности: ./copydb_dev_to_qnap.sh --help
#
# Настройки QNAP-базы (prod) берутся из .env.production: POSTGRES_USER,
# POSTGRES_PASSWORD, POSTGRES_DB (переопределение — QNAP_POSTGRES_*).
# SSH на QNAP — под пользователем QNAP_USER (по умолчанию admin), по ключу.
#
# ВНИМАНИЕ: скрипт пересоздает ПРОД-базу.
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
# Контейнеры приложения (Django/huey), которые надо остановить на время
# заливки. Список через пробел. Пусто = определить автоматически:
# все запущенные контейнеры, кроме postgres-контейнера, у которых задан
# POSTGRES_HOST / PGHOST / DATABASE_URL.
QNAP_APP_CONTAINERS="${QNAP_APP_CONTAINERS:-}"
# Сколько секунд ждать graceful stop приложения.
QNAP_APP_STOP_TIMEOUT="${QNAP_APP_STOP_TIMEOUT:-30}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROD_ENV_FILE="${PROD_ENV_FILE:-${SCRIPT_DIR}/.env.production}"

usage() {
    cat <<EOF
Использование: $(basename "$0") [опции]

Заливает дамп в PostgreSQL на QNAP (prod). По умолчанию берется самый
свежий файл *.dump / *.sql из папки ./backups.

  --yes, -y          не спрашивать подтверждение (база будет пересоздана!)
  --file FILE        конкретный файл дампа (вместо последнего из --dir)
  --dir DIR          папка с дампами (по умолчанию: ${SCRIPT_DIR}/backups)
  --no-safety-backup не снимать страховочный дамп прод-базы перед заливкой
  --no-app-stop      не останавливать приложение на QNAP (по умолчанию
                     скрипт сам останавливает его и поднимает обратно)
  --help, -h         эта справка

Поддерживает: custom-формат pg_dump -Fc (*.dump) и plain SQL (*.sql).

.env.production (QNAP/prod): POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB
  (можно переопределить переменными окружения QNAP_POSTGRES_*)

Константы в скрипте (можно переопределить переменными окружения):
  QNAP_SSH_HOST=${QNAP_SSH_HOST}
  QNAP_USER=${QNAP_USER}
  QNAP_CONTAINER_NAME=${QNAP_CONTAINER_NAME}
  QNAP_DOCKER_BIN=${QNAP_DOCKER_BIN:-<авто>}
  QNAP_APP_CONTAINERS=${QNAP_APP_CONTAINERS:-<авто-определение>}
  QNAP_APP_STOP_TIMEOUT=${QNAP_APP_STOP_TIMEOUT}
EOF
}

# Читаем значение ключа из .env БЕЗ source: иначе bash-подстановка
# ($var, !, `...`) ломается на спецсимволах в других строках (SECRET_KEY и т.п.).
load_env_key() {
    local key="$1" file="${2:-${PROD_ENV_FILE}}" line val
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

# Значение из файла, с приоритетом переменной окружения с ДРУГИМ именем.
# В .env.production ключи называются POSTGRES_*, а переопределить их можно
# через QNAP_POSTGRES_* (чтобы не конфликтовать с dev-переменными).
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
SAFETY_BACKUP=1
APP_STOP=1
DUMP_DIR="${SCRIPT_DIR}/backups"
DUMP_FILE=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        -y|--yes)             ASSUME_YES=1 ;;
        --no-safety-backup)   SAFETY_BACKUP=0 ;;
        --no-app-stop)        APP_STOP=0 ;;
        --dir)
            if [[ $# -lt 2 ]]; then
                echo "ОШИБКА: --dir требует путь." >&2
                usage
                exit 1
            fi
            DUMP_DIR="$2"
            shift
            ;;
        --file)
            if [[ $# -lt 2 ]]; then
                echo "ОШИБКА: --file требует путь." >&2
                usage
                exit 1
            fi
            DUMP_FILE="$2"
            shift
            ;;
        -h|--help)            usage; exit 0 ;;
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

for tool in ssh base64; do
    if ! command -v "${tool}" >/dev/null 2>&1; then
        echo "ОШИБКА: ${tool} не найден в PATH." >&2
        exit 1
    fi
done

# -------------------- QNAP (prod) --------------------
QNAP_POSTGRES_USER="$(env_value_alt QNAP_POSTGRES_USER POSTGRES_USER "${PROD_ENV_FILE}" || true)"
QNAP_POSTGRES_PASSWORD="$(env_value_alt QNAP_POSTGRES_PASSWORD POSTGRES_PASSWORD "${PROD_ENV_FILE}" || true)"
QNAP_POSTGRES_DB="$(env_value_alt QNAP_POSTGRES_DB POSTGRES_DB "${PROD_ENV_FILE}" || true)"

MISSING_PROD=()
[[ -n "${QNAP_POSTGRES_USER}" ]]     || MISSING_PROD+=("POSTGRES_USER")
[[ -n "${QNAP_POSTGRES_PASSWORD}" ]] || MISSING_PROD+=("POSTGRES_PASSWORD")
[[ -n "${QNAP_POSTGRES_DB}" ]]       || MISSING_PROD+=("POSTGRES_DB")

if [[ ${#MISSING_PROD[@]} -gt 0 ]]; then
    echo "ОШИБКА: в ${PROD_ENV_FILE} не заданы: ${MISSING_PROD[*]}" >&2
    exit 1
fi

case "${QNAP_POSTGRES_DB}" in
    postgres|template0|template1)
        echo "ОШИБКА: отказываюсь пересоздавать системную базу '${QNAP_POSTGRES_DB}'." >&2
        exit 1
        ;;
esac

# ------------------------------------ #
#         ВЫБОР ФАЙЛА ДАМПА            #
# ------------------------------------ #
if [[ -z "${DUMP_FILE}" ]]; then
    if [[ ! -d "${DUMP_DIR}" ]]; then
        echo "ОШИБКА: папка с дампами не найдена: ${DUMP_DIR}" >&2
        exit 1
    fi
    # ls -1t: самый свежий по mtime первым. Отсутствующий glob (например,
    # нет ни одного *.sql) просто игнорируется.
    # pre_restore_* (страховочные дампы прод-базы) в выборку не попадают,
    # иначе повторный запуск заливал бы не «последний дамп», а страховку.
    DUMP_FILE="$(ls -1t -- "${DUMP_DIR}"/*.dump "${DUMP_DIR}"/*.sql 2>/dev/null \
        | grep -v '/pre_restore_' | head -n 1 || true)"
    if [[ -z "${DUMP_FILE}" ]]; then
        echo "ОШИБКА: в ${DUMP_DIR} нет файлов *.dump / *.sql." >&2
        exit 1
    fi
    echo "==> Взят последний дамп из ${DUMP_DIR}: $(basename "${DUMP_FILE}")"
fi

if [[ ! -f "${DUMP_FILE}" ]]; then
    echo "ОШИБКА: файл не найден: ${DUMP_FILE}" >&2
    exit 1
fi
if [[ ! -s "${DUMP_FILE}" ]]; then
    echo "ОШИБКА: файл дампа пустой: ${DUMP_FILE}" >&2
    exit 1
fi

DUMP_KIND="dump"
if [[ "${DUMP_FILE}" == *.sql ]]; then
    DUMP_KIND="sql"
fi

# Быстрая проверка, что *.dump действительно в custom-формате pg_dump.
if [[ "${DUMP_KIND}" == "dump" && "$(head -c 5 "${DUMP_FILE}")" != "PGDMP" ]]; then
    echo "ОШИБКА: файл не похож на pg_dump custom-формат (нет заголовка PGDMP): ${DUMP_FILE}" >&2
    exit 1
fi

# ------------------------------------ #
#        УДАЛЕННЫЙ СКРИПТ (QNAP)       #
# ------------------------------------ #
# Скрипт уезжает на QNAP в base64 и исполняется из временного файла:
# stdin ssh-сессии остается свободным под сам дамп (pg_restore читает его).
read -r -d '' REMOTE_SCRIPT <<'REMOTE' || true
set -euo pipefail

# Аргументы (позиционные, переданы через ssh).
mode="$1"                # dump | restore | app-detect | app-stop | app-start
container="$2"
pguser="$3"
pgpass="$4"
pgdb="$5"
docker_bin="${6:-}"
dump_kind="${7:-dump}"   # dump (pg_dump -Fc) | sql (plain SQL)
app_list="${8:-}"        # контейнеры приложения через запятую (для app-stop/start)
stop_timeout="${9:-30}"  # сколько секунд ждать graceful stop приложения

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
    echo "Задай путь явно: QNAP_DOCKER_BIN=/share/.../container-station/bin/docker ./copydb_dev_to_qnap.sh" >&2
    exit 1
fi
echo "docker: ${docker_bin}" >&2

# Контейнеры приложения: ищем те, что смотрят на postgres (POSTGRES_HOST,
# PGHOST или DATABASE_URL в окружении), исключая сам postgres-контейнер.
# Имена печатаем в stdout — их забирает локальная часть скрипта.
detect_app_containers() {
    local c env_out
    for c in $("${docker_bin}" ps --format '{{.Names}}'); do
        [[ "${c}" == "${container}" ]] && continue
        env_out="$("${docker_bin}" inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "${c}" 2>/dev/null || true)"
        if printf '%s\n' "${env_out}" | grep -qE '^(POSTGRES_HOST|PGHOST|DATABASE_URL)='; then
            printf '%s\n' "${c}"
        fi
    done
}

app_containers="${app_list//,/ }"

case "${mode}" in
    app-detect)
        detect_app_containers
        exit 0
        ;;
    app-stop)
        for c in ${app_containers}; do
            if ! "${docker_bin}" ps --format '{{.Names}}' | grep -qx "${c}"; then
                echo "    ${c}: уже остановлен" >&2
                continue
            fi
            echo "    останавливаю ${c}..." >&2
            # -t: даем приложению время завершиться штатно.
            "${docker_bin}" stop -t "${stop_timeout}" "${c}" >/dev/null
        done
        exit 0
        ;;
    app-start)
        for c in ${app_containers}; do
            echo "    запускаю ${c}..." >&2
            "${docker_bin}" start "${c}" >/dev/null
            if [[ "$("${docker_bin}" inspect -f '{{.State.Running}}' "${c}" 2>/dev/null || true)" != "true" ]]; then
                echo "ВНИМАНИЕ: ${c} запущен, но не в состоянии running (проверь логи)." >&2
            fi
        done
        exit 0
        ;;
esac

if ! "${docker_bin}" ps --format '{{.Names}}' | grep -qx "${container}"; then
    echo "ОШИБКА: контейнер '${container}' не найден среди запущенных на удаленном хосте." >&2
    "${docker_bin}" ps --format '{{.Names}}' >&2 || true
    exit 1
fi

if [[ "${mode}" == "dump" ]]; then
    "${docker_bin}" exec -e PGPASSWORD="${pgpass}" "${container}" pg_dump --version >&2
    exec "${docker_bin}" exec -e PGPASSWORD="${pgpass}" "${container}" \
        pg_dump -U "${pguser}" -d "${pgdb}" -F c -Z 9
fi

case "${pgdb}" in
    postgres|template0|template1)
        echo "ОШИБКА: отказываюсь пересоздавать системную базу '${pgdb}'." >&2
        exit 1
        ;;
esac

psql_base=("${docker_bin}" exec -e PGPASSWORD="${pgpass}" "${container}" \
    psql -U "${pguser}" -d postgres -v ON_ERROR_STOP=1)

echo "==> Пересоздание базы '${pgdb}'..." >&2
# WITH (FORCE) закрывает оставшиеся подключения к базе (PostgreSQL 13+).
"${psql_base[@]}" -c "DROP DATABASE IF EXISTS \"${pgdb}\" WITH (FORCE);" >&2
"${psql_base[@]}" -c "CREATE DATABASE \"${pgdb}\";" >&2

if [[ "${dump_kind}" == "sql" ]]; then
    echo "==> Восстановление SQL-дампа через psql..." >&2
    exec "${docker_bin}" exec -i -e PGPASSWORD="${pgpass}" "${container}" \
        psql -U "${pguser}" -d "${pgdb}" -v ON_ERROR_STOP=1 --single-transaction
fi

echo "==> Восстановление дампа через pg_restore..." >&2
exec "${docker_bin}" exec -i -e PGPASSWORD="${pgpass}" "${container}" \
    pg_restore -U "${pguser}" -d "${pgdb}" \
    --no-owner --no-privileges --single-transaction --exit-on-error
REMOTE

REMOTE_SCRIPT_B64="$(printf '%s' "${REMOTE_SCRIPT}" | base64 | tr -d '\r\n')"

# Собирает команду для ssh: разворачивает remote-скрипт из base64 во
# временный файл и запускает его с позиционными аргументами.
# Значения экранируем локальным %q: ssh склеивает аргументы через пробел.
remote_command() {
    local mode="$1" kind="${2:-}" apps="${3:-}" args wrapper
    args="$(printf '%q ' "${mode}" "${QNAP_CONTAINER_NAME}" "${QNAP_POSTGRES_USER}" \
        "${QNAP_POSTGRES_PASSWORD}" "${QNAP_POSTGRES_DB}" "${QNAP_DOCKER_BIN}" "${kind}" \
        "${apps}" "${QNAP_APP_STOP_TIMEOUT}")"
    wrapper=$(cat <<'WRAPPER'
tmp_script="$(mktemp 2>/dev/null || echo /tmp/mfp_restore_$$.sh)"
trap 'rm -f "${tmp_script}"' EXIT
printf %s 'B64_PAYLOAD' | (base64 -d 2>/dev/null || openssl base64 -d) > "${tmp_script}"
bash "${tmp_script}" REMOTE_ARGS
WRAPPER
)
    wrapper="${wrapper/B64_PAYLOAD/${REMOTE_SCRIPT_B64}}"
    wrapper="${wrapper/REMOTE_ARGS/${args}}"
    printf '%s' "${wrapper}"
}

SSH_TARGET="${QNAP_USER}@${QNAP_SSH_HOST}"

echo "==> Цель:   ${SSH_TARGET}:${QNAP_CONTAINER_NAME} db=${QNAP_POSTGRES_DB} user=${QNAP_POSTGRES_USER}"
echo "==> Дамп:   ${DUMP_FILE} ($(ls -lh "${DUMP_FILE}" | awk '{print $5}'), ${DUMP_KIND})"

# ------------------------------------ #
#          КОНТЕЙНЕРЫ ПРИЛОЖЕНИЯ       #
# ------------------------------------ #
# Пусто = определить автоматически на QNAP (контейнеры, смотрящие на postgres).
APP_CONTAINERS="${QNAP_APP_CONTAINERS}"
if [[ "${APP_STOP}" -eq 1 && -z "${APP_CONTAINERS}" ]]; then
    echo "==> Ищу приложение на QNAP (контейнеры, смотрящие на postgres)..."
    detected="$(ssh -n -o BatchMode=yes "${SSH_TARGET}" "$(remote_command app-detect)" 2>/dev/null \
        | tr -d '\r' | grep -v '^[[:space:]]*$' || true)"
    APP_CONTAINERS="$(printf '%s' "${detected}" | tr '\n' ' ' | sed -e 's/[[:space:]]*$//')"
fi

if [[ "${APP_STOP}" -eq 1 ]]; then
    if [[ -n "${APP_CONTAINERS}" ]]; then
        echo "==> Будет остановлено и запущено обратно: ${APP_CONTAINERS}"
    else
        echo "ВНИМАНИЕ: не удалось определить контейнер приложения на QNAP." >&2
        echo "          Приложение НЕ будет остановлено. Если база занята — задай" >&2
        echo "          QNAP_APP_CONTAINERS='имя_контейнера' и запусти снова." >&2
    fi
else
    echo "==> --no-app-stop: приложение на QNAP не трогаем."
fi

echo "Цель: контейнер=${QNAP_CONTAINER_NAME} db=${QNAP_POSTGRES_DB} user=${QNAP_POSTGRES_USER} файл=${DUMP_FILE}"
echo "ВНИМАНИЕ: ПРОД-база '${QNAP_POSTGRES_DB}' на ${SSH_TARGET} будет УДАЛЕНА и создана заново."
if [[ "${ASSUME_YES}" -eq 0 ]]; then
    read -r -p "Продолжить? [y/N] " confirm
    [[ "${confirm}" == "y" || "${confirm}" == "Y" ]] || { echo "Отмена."; exit 1; }
fi

# ------------------------------------ #
#      СТРАХОВОЧНЫЙ ДАМП ПРОД-БАЗЫ     #
# ------------------------------------ #
SAFETY_FILE=""
if [[ "${SAFETY_BACKUP}" -eq 1 ]]; then
    TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
    SAFETY_FILE="${DUMP_DIR}/pre_restore_${QNAP_POSTGRES_DB}_${TIMESTAMP}.dump"
    mkdir -p "${DUMP_DIR}"
    echo "==> Страховочный дамп прод-базы: ${SAFETY_FILE}"
    # -n: ssh не должен читать локальный stdin, вывод pg_dump пишем в файл.
    if ! ssh -n -o BatchMode=yes "${SSH_TARGET}" "$(remote_command dump dump)" > "${SAFETY_FILE}"; then
        rm -f "${SAFETY_FILE}"
        echo "ОШИБКА: не удалось снять страховочный дамп с ${SSH_TARGET}." >&2
        echo "Проверь SSH-доступ (ключ), имя контейнера и POSTGRES_* в ${PROD_ENV_FILE}." >&2
        exit 1
    fi
    if [[ ! -s "${SAFETY_FILE}" || "$(head -c 5 "${SAFETY_FILE}")" != "PGDMP" ]]; then
        rm -f "${SAFETY_FILE}"
        echo "ОШИБКА: страховочный дамп пустой или битый (нет заголовка PGDMP)." >&2
        exit 1
    fi
    echo "    ок: $(ls -lh "${SAFETY_FILE}" | awk '{print $5}')"
fi

# ------------------------------------ #
#            СТОП ПРИЛОЖЕНИЯ           #
# ------------------------------------ #
APP_STOPPED=0

restart_app_at_exit() {
    local rc=$?
    if [[ "${APP_STOPPED}" -eq 1 ]]; then
        APP_STOPPED=0
        echo "==> Возвращаю приложение на QNAP: ${APP_CONTAINERS}"
        if ! ssh -n -o BatchMode=yes "${SSH_TARGET}" \
            "$(remote_command app-start '' "${APP_CONTAINERS}")"; then
            echo "ВНИМАНИЕ: не удалось запустить приложение на QNAP." >&2
            echo "          Подними контейнеры вручную: ${APP_CONTAINERS}" >&2
        else
            echo "==> Приложение запущено. После старта контейнер выполнит миграции."
        fi
    fi
    return "${rc}"
}
trap restart_app_at_exit EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

if [[ "${APP_STOP}" -eq 1 && -n "${APP_CONTAINERS}" ]]; then
    echo "==> Останавливаю приложение на QNAP..."
    # Флаг ставим ДО вызова: если stop частично прошел и упал,
    # trap все равно поднимет контейнеры обратно.
    APP_STOPPED=1
    if ! ssh -n -o BatchMode=yes "${SSH_TARGET}" \
        "$(remote_command app-stop '' "${APP_CONTAINERS}")"; then
        echo "ОШИБКА: не удалось остановить приложение (${APP_CONTAINERS})." >&2
        echo "База не тронута. Проверь имена контейнеров (QNAP_APP_CONTAINERS)." >&2
        exit 1
    fi
    echo "    ок"
fi

# ------------------------------------ #
#        ВОССТАНОВЛЕНИЕ НА QNAP        #
# ------------------------------------ #
# Дамп подается на stdin ssh-сессии и дальше в pg_restore/psql.
if ! ssh -o BatchMode=yes "${SSH_TARGET}" "$(remote_command restore "${DUMP_KIND}")" < "${DUMP_FILE}"; then
    echo "ОШИБКА: восстановление на ${SSH_TARGET} не удалось." >&2
    if [[ "${SAFETY_BACKUP}" -eq 1 ]]; then
        echo "Страховочный дамп прод-базы сохранен: ${SAFETY_FILE}" >&2
        echo "Вернуть его можно так: ./copydb_dev_to_qnap.sh --file \"${SAFETY_FILE}\" --no-safety-backup" >&2
    fi
    exit 1
fi

echo "==> Готово. Прод-база '${QNAP_POSTGRES_DB}' на ${SSH_TARGET} восстановлена из ${DUMP_FILE}."

# Поднимаем приложение сразу, не дожидаясь выхода (trap на случай ошибок выше).
restart_app_at_exit
trap - EXIT
