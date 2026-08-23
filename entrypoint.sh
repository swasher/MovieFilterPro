#!/bin/sh
set -e

# Wait for PostgreSQL to be ready
if [ -n "$POSTGRES_HOST" ]; then
    echo "Waiting for PostgreSQL at $POSTGRES_HOST:${POSTGRES_PORT:-5432}..."
    until python -c "
import os, sys, time
import psycopg
host = os.getenv('POSTGRES_HOST')
port = int(os.getenv('POSTGRES_PORT', '5432'))
user = os.getenv('POSTGRES_USER')
password = os.getenv('POSTGRES_PASSWORD')
db = os.getenv('POSTGRES_DB')
try:
    conn = psycopg.connect(host=host, port=port, user=user, password=password, dbname=db, connect_timeout=3)
    conn.close()
    sys.exit(0)
except Exception as e:
    print(f'PostgreSQL not ready: {e}', flush=True)
    sys.exit(1)
"; do
        sleep 2
    done
    echo "PostgreSQL is ready."
fi

echo "Running migrations..."
python /app/manage.py migrate --noinput
if [ $? -ne 0 ]; then
    echo "Migrations failed, exiting..."
    exit 1
fi

echo "Starting supervisord..."
exec /usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf