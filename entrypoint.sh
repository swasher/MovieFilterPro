#!/bin/sh

set -e

MODE="${1:-web}"

case "$MODE" in
    web)
        echo "Running migrations..."
        python /app/manage.py migrate --noinput
        if [ $? -ne 0 ]; then
            echo "Migrations failed, exiting..."
            exit 1
        fi

        echo "Starting Daphne..."
        exec daphne -b 0.0.0.0 -p 8008 --http-timeout 600 movie_filter_pro.asgi:application
        ;;
    worker)
        echo "Starting Huey consumer..."
        exec python -m huey.bin.huey_consumer movie_filter_pro.huey.HUEY --worker-type thread --workers 2
        ;;
    *)
        echo "Unknown mode: $MODE"
        echo "Usage: /app/entrypoint.sh [web|worker]"
        exit 1
        ;;
esac
