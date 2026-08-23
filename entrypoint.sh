#!/bin/sh
set -e

# -----------------------------------------------
# Wait for PostgreSQL to be ready
# -----------------------------------------------
if [ -n "$POSTGRES_HOST" ]; then
    PGHOST="$POSTGRES_HOST"
    PGPORT="${POSTGRES_PORT:-5432}"
    PGUSER="$POSTGRES_USER"
    PGPASSWORD="$POSTGRES_PASSWORD"
    PGDATABASE="$POSTGRES_DB"

    export PGHOST PGPORT PGUSER PGPASSWORD PGDATABASE

    MAX_ATTEMPTS=30
    ATTEMPT=0

    echo "Waiting for PostgreSQL at $PGHOST:$PGPORT..."
    until pg_isready -q; do
        ATTEMPT=$((ATTEMPT + 1))
        if [ "$ATTEMPT" -ge "$MAX_ATTEMPTS" ]; then
            echo "ERROR: PostgreSQL did not become ready after $MAX_ATTEMPTS attempts. Exiting."
            exit 1
        fi
        echo "  Attempt $ATTEMPT/$MAX_ATTEMPTS - PostgreSQL not ready, retrying in 2s..."
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