#!/bin/sh
echo "Running migrations..."
python /app/manage.py migrate
if [ $? -ne 0 ]; then
    echo "Migrations failed, exiting..."
    exit 1
fi
echo "Starting Gunicorn..."
exec gunicorn --bind 0.0.0.0:8008 movie_filter_pro.wsgi:application
