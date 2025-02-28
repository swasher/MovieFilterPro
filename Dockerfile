FROM arm32v7/python:3.12-slim

#ENV IN_DOCKER=True

# Устанавливаем рабочую директорию
WORKDIR /app

# Создаем директорию /torrents_hotfolder
RUN mkdir /torrents_hotfolder

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

# Копируем entrypoint.sh
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Открываем порт
EXPOSE 8008

# Устанавливаем entrypoint
ENTRYPOINT ["/app/entrypoint.sh"]

# CMD остаётся как запасной вариант, но entrypoint его перехватит
CMD ["gunicorn", "--bind", "0.0.0.0:8008", "movie_filter_pro.wsgi:application"]
