#!/bin/sh
### BEGIN INIT INFO
# Provides:          webhook_httpd
# Required-Start:    $remote_fs $syslog
# Required-Stop:     $remote_fs $syslog
# Default-Start:     2 3 4 5
# Default-Stop:      0 1 6
# Short-Description: Start webhook httpd server at boot time
# Description:       Enable service provided by webhook server.
### END INIT INFO



LOG_FILE="/share/CACHEDEV1_DATA/homes/swasher/webhook/initd.log"


# Если есть терминал, выводим в него, иначе пишем в лог-файл
if [ -t 1 ]; then
    exec > /dev/tty 2>&1
else
    exec > "$LOG_FILE" 2>&1
fi


echo "Запуск скрипта init.d..."


# Путь к Python-скрипту
SCRIPT_PATH="/share/CACHEDEV1_DATA/homes/swasher/webhook/webhook_httpd.py"
VENV_PATH="/share/CACHEDEV1_DATA/homes/swasher/webhook/.venv"
PYTHON_PATH="$VENV_PATH/bin/python3"
PID_FILE="/var/run/webhook_server.pid"



case "$1" in
    start)
        echo "Starting webhook server..."

        if [ -f "$PID_FILE" ]; then
            echo "Webhook server is already running with PID $(cat $PID_FILE)"
            exit 1
        fi


        # Проверяем, что виртуальная среда существует
        if [ ! -d "$VENV_PATH" ]; then
            echo "Virtual environment not found at $VENV_PATH"
            exit 1
        fi


        # Загружаем окружение Python 3
        if ! command -v python3 >/dev/null 2>&1; then
            echo "Python 3 not found. Trying to load it..."
            source /share/CACHEDEV1_DATA/.qpkg/Python3/python3.bash
        fi

        # Проверяем, что Python 3 действительно загрузился
        if ! command -v python3 >/dev/null 2>&1; then
            echo "Error: Python 3 is still not available!"
            exit 1
        fi

        echo "Python 3 found: $(which python3)"


        # Активируем виртуальное окружение
        export PATH="$VENV_PATH/bin:$PATH"
        source "$VENV_PATH/bin/activate"


        # Проверяем наличие docker
        #if ! command -v docker >/dev/null 2>&1; then
        #    echo "Error: docker not found!"
        #    exit 1
        #fi

        # Запускаем сервер
        "$PYTHON_PATH" "$SCRIPT_PATH" &
        echo $! > "$PID_FILE"
        echo "Webhook server started with PID $(cat $PID_FILE)"
        deactivate
        ;;
    stop)
        echo "Stopping webhook server..."
        if [ -f "$PID_FILE" ]; then
            kill $(cat "$PID_FILE")
            rm -f "$PID_FILE"
            echo "Webhook server stopped"
        else
            echo "Webhook server is not running"
        fi
        ;;
    restart)
        $0 stop
        sleep 1
        $0 start
        ;;
    status)
        if [ -f "$PID_FILE" ]; then
            echo "Webhook server is running with PID $(cat $PID_FILE)"
        else
            echo "Webhook server is not running."
        fi
        ;;
    *)
        echo "Usage: $0 {start|stop|restart}"
        exit 1
        ;;
esac

exit 0
