FROM arm32v7/python:3.12-slim

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем зависимости
COPY requirements.txt /app

# Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Копируем файл .env.production и переименовываем его в .env
COPY .env.production /app/.env

# Копируем проект
COPY . /app

# Не запускаем миграции, так как база у нас отдельно
# RUN python manage.py migrate

# Собираем статические файлы
RUN python manage.py collectstatic --noinput

# Открываем порт
EXPOSE 8008

# Задаем PYTHONPATH через ENV
ENV PYTHONPATH=/app

# Запускаем сервер
#CMD ["python", "manage.py", "runserver", "0.0.0.0:8008"]
# Запускаем Gunicorn
#CMD ["gunicorn", "--bind", "0.0.0.0:8008", "movie_filter_pro.wsgi:application"]
CMD ["sh", "-c", "cd /app && echo \"Current dir: $(pwd)\" && gunicorn --bind 0.0.0.0:8008 --pythonpath /app movie_filter_pro.wsgi:application"]
