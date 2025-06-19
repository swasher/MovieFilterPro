FROM arm32v7/python:3.12-slim

#ENV IN_DOCKER=True

# Устанавливаем рабочую директорию
WORKDIR /app

# Устанавливаем инструменты сборки и nginx
# deprecated
#RUN apt-get update && apt-get install -y --no-install-recommends \
#    build-essential \
#    libffi-dev \
#    nginx \
#    && rm -rf /var/lib/apt/lists/*
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Создаем директорию /torrents_hotfolder и /run/nginx
# deprecated RUN mkdir -p /torrents_hotfolder /run/nginx
RUN mkdir -p /torrents_hotfolder

# Копируем конфиг nginx
# deprecated COPY nginx.conf /etc/nginx/nginx.conf

# Копируем зависимости
COPY requirements.txt /app

# Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Копируем файл .env.production и переименовываем его в .env
COPY .env.production /app/.env

# Копируем проект
COPY . /app

# Не запускаем миграции, так как база у нас отдельно от проекта и еще не примонтирована
# RUN python manage.py migrate

# Собираем статические файлы
# Просто копируем статику из папки collectstatic
# RUN python manage.py collectstatic --noinput

# Копируем entrypoint.sh
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh


RUN echo "$(date +'%Y-%m-%d %H:%M:%S')" > /app/timestamp

# Открываем порт
EXPOSE 8008

# Устанавливаем entrypoint
ENTRYPOINT ["/app/entrypoint.sh"]

# CMD остаётся как запасной вариант, но entrypoint его перехватит
#CMD ["gunicorn", "--bind", "0.0.0.0:8008", "movie_filter_pro.wsgi:application"]
#CMD ["daphne", "-b", "0.0.0.0", "-p", "8008", "movie_filter_pro.asgi:application"]
