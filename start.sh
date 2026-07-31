#!/bin/sh
set -e

echo "Running migrations..."
python /app/manage.py migrate --noinput
if [ $? -ne 0 ]; then
    echo "Migrations failed, exiting..."
    exit 1
fi

echo "Starting supervisord..."
exec /usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf