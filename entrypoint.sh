#!/bin/sh

echo "Running migrations..."
python /app/manage.py migrate --noinput
if [ $? -ne 0 ]; then
    echo "Migrations failed, exiting..."
    exit 1
fi

# Запускаем worker Huey в фоновом режиме (&)
# --worker-type thread экономит RAM по сравнению с process
python -m huey.bin.huey_consumer movie_filter_pro.huey.HUEY --worker-type thread --workers 2 &

#echo "Starting Gunicorn..."
#exec gunicorn --bind 0.0.0.0:8008 movie_filter_pro.wsgi:application
echo "Starting Daphne..."
exec daphne -b 0.0.0.0 -p 8008 --http-timeout 600 movie_filter_pro.asgi:application
