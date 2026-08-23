#!/bin/sh
set -e

# -----------------------------------------------
# Wait for PostgreSQL to be ready
# -----------------------------------------------
if [ -n "$POSTGRES_HOST" ]; then
    PGHOST="$POSTGRES_HOST"
    PGPORT="${POSTGRES_PORT:-5432}"

    MAX_ATTEMPTS=30
    ATTEMPT=0

    echo "Waiting for PostgreSQL at $PGHOST:$PGPORT..."
    until python -c "
import socket, sys
try:
    s = socket.socket()
    s.settimeout(2)
    s.connect(('$PGHOST', $PGPORT))
    s.close()
except Exception:
    sys.exit(1)
"; do
        ATTEMPT=$((ATTEMPT + 1))
        if [ "$ATTEMPT" -ge "$MAX_ATTEMPTS" ]; then
            echo "ERROR: PostgreSQL did not become ready after $MAX_ATTEMPTS attempts. Exiting."
            exit 1
        fi
        echo "  Attempt $ATTEMPT/$MAX_ATTEMPTS - not ready, retrying in 2s..."
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