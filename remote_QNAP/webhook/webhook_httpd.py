"""

В итоге я отказался от использования библиотеки docker для перезапуска контейнера, и использую просто
шелл-команду с docker compose.

Сам контейнер я тоже поднимаю через Conteiner Station->Приложения, используя рядом лежащий docker-compose.yml.

"""

import sys
import os
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import logging
import docker
import subprocess

# Настройка логгера
logging.basicConfig(filename='/share/CACHEDEV1_DATA/homes/swasher/webhook/webhook.log', level=logging.DEBUG, format='%(asctime)s - %(message)s')



"""
Лог такой получается (с одного пуша). Может быть три респонса, а может быть и два. 

Received webhook for repository: swasher/movie-filter-pro, tag:
52.204.105.43 - - [13/Feb/2025 23:05:17] "POST /webhook HTTP/1.1" 200 -
Received webhook for repository: swasher/movie-filter-pro, tag:
52.2.68.253 - - [13/Feb/2025 23:05:17] "POST /webhook HTTP/1.1" 200 -
Received webhook for repository: swasher/movie-filter-pro, tag: armv7
52.204.105.43 - - [13/Feb/2025 23:05:18] "POST /webhook HTTP/1.1" 200 -
"""


"""
payload example (от Docker hub)

payload = {
    'callback_url': 'https://registry.hub.docker.com/u/swasher/movie-filter-pro/hook/2cfd7a437f04427085b83bb8b7a01e24/',
    'push_data': {'pusher': 'swasher', 'pushed_at': 1739573301, 'tag': 'armv7', 'images': [],
                  'media_type': 'application/vnd.oci.image.index.v1+json'},
    'repository': {'status': 'Active', 'namespace': 'swasher', 'name': 'movie-filter-pro',
                   'repo_name': 'swasher/movie-filter-pro',
                   'repo_url': 'https://hub.docker.com/r/swasher/movie-filter-pro', 'description': '',
                   'full_description': None, 'star_count': 0, 'is_private': False, 'is_trusted': False,
                   'is_official': False, 'owner': 'swasher', 'date_created': 1738705387}}
"""



@dataclass
class Config:
    IMAGE = "swasher/movie-filter-pro"
    TAG = "armv7"
    FULL_IMAGE = f"{IMAGE}:{TAG}"  # Полное имя образа с тегом
    CONTAINER = "movie-filter-pro"
    LISTEN_PORT = 43512  # Вебхук
    HOST_VOLUME_PATH = "/share/CACHEDEV1_DATA/homes/swasher/PERSISTENT_VOLUME"  # Путь на QNAP
    CONTAINER_VOLUME_PATH = "/app"  # Путь внутри контейнера
    PORTS = {'8008/tcp': 8008}  # Проброс порта 8000
    COMPOSE_DIR = "/share/Container/container-station-data/application/mfp"


def log(message):
    logging.debug(message)  # Запись в лог-файл
    print(message)  # Вывод в консоль


def remove_existing_containers(client, container_name_prefix):
    """Удаляет все контейнеры, имена которых начинаются с заданного префикса."""
    # Получаем все контейнеры (включая остановленные) с именем, начинающимся на container_name_prefix
    containers = client.containers.list(all=True, filters={"name": container_name_prefix})
    if not containers:
        log(f"No containers found with name prefix '{container_name_prefix}'.")
        return

    for cont in containers:
        log(f"Removing existing container {cont.name} (ID: {cont.id})...")
        try:
            cont.stop()
            cont.remove()
            log(f"Container {cont.name} stopped and removed.")
        except docker.errors.APIError as e:
            log(f"Failed to remove container {cont.name}: {e}")
            # Принудительное удаление, если обычное не сработало
            try:
                cont.remove(force=True)
                log(f"Forced removal of {cont.name} succeeded.")
            except docker.errors.APIError as e:
                log(f"Force removal of {cont.name} failed: {e}")


def remove_none_tag_images(client, image_name):
    """Удаляет все образы с тегом <none> для указанного имени."""
    images = client.images.list(all=True)
    for img in images:
        if not img.tags and image_name in [tag.split(':')[0] for tag in img.attrs.get('RepoTags', [])]:
            try:
                log(f"Removing dangling image {img.id}...")
                client.images.remove(img.id, force=True)
                log(f"Dangling image {img.id} removed.")
            except docker.errors.APIError as e:
                log(f"Ошибка при удалении dangling образа {img.id}: {e}")


def docker_check():
    try:
        # Создаем клиент Docker

        client = docker.from_env()

        # Проверяем подключение, получая информацию о Docker
        docker_info = client.info()
        log("Успешное подключение к Docker!")
        log(f"Версия Docker: {docker_info['ServerVersion']}")
        log(f"Количество контейнеров: {docker_info['Containers']}")
        log(f"Количество образов: {docker_info['Images']}")

        # Выводим список запущенных контейнеров
        # print("\nСписок запущенных контейнеров:")
        # containers = client.containers.list()
        # for container in containers:
        #     print(f"Имя контейнера: {container.name}, ID: {container.id}")

    except docker.errors.DockerException as e:
        log(f"Ошибка подключения к Docker: {e}")
        exit(1)


def update_compose():
    command = "docker compose pull && docker compose down && docker compose up -d && docker container prune -f && docker image prune --all -f"

    try:
        # Выполняем команду в указанной папке
        log(subprocess.run(command, cwd=Config.COMPOSE_DIR, shell=True, text=True))

    except subprocess.CalledProcessError as e:
        print(f"Ошибка: {e.stderr}")



def update_container():
    client = docker.from_env()

    log('\n')
    log('NEW UPDATE')
    log('\n')

    try:
        # # Проверяем, существует ли контейнер
        # try:
        #     container = client.containers.get(Config.CONTAINER)
        #     image_name = container.image.tags[0]  # Получаем имя образа
        #
        #     # Останавливаем и удаляем текущий контейнер
        #     log(f"Stopping and removing container {Config.CONTAINER}...")
        #     container.stop()
        #     container.remove()
        # except docker.errors.NotFound:
        #     log("Контейнер не найден, создаём новый.")
        #     image_name = Config.FULL_IMAGE

        # Удаляем все существующие контейнеры с именем movie-filter-pro или его вариациями
        remove_existing_containers(client, Config.CONTAINER)

        # Обновляем образ из Docker Hub
        log(f"Pulling latest image: {Config.FULL_IMAGE}...")
        client.images.pull(Config.FULL_IMAGE)
        log("--> Образ успешно скачан.")

        # # Удаляем старый образ, если он отличается от нового
        # if image_name != Config.FULL_IMAGE:
        #     try:
        #         log(f"Removing old image {image_name}...")
        #         client.images.remove(image_name, force=True)
        #         log("Старый образ успешно удалён.")
        #     except docker.errors.ImageNotFound:
        #         log("Старый образ не найден, пропускаем удаление.")
        #     except docker.errors.APIError as e:
        #         log(f"Ошибка при удалении старого образа: {e}")

        # Запускаем новый контейнер с обновленным образом
        log(f"Starting new container {Config.CONTAINER}...")
        container = None  # Инициализируем container как None
        try:
            container = client.containers.run(
                Config.FULL_IMAGE,
                name=Config.CONTAINER,
                detach=True,
                # restart_policy={"Name": "always"},
                ports=Config.PORTS,  # Сохраняем порты
                volumes={
                    Config.HOST_VOLUME_PATH: {
                        'bind': Config.CONTAINER_VOLUME_PATH,
                        'mode': 'rw'  # Чтение и запись
                    }
                }
            )
            log(f"Container {Config.CONTAINER} updated successfully.")
        except docker.errors.APIError as e:
            log(f"Failed to start container {Config.CONTAINER}: {e}")
            raise  # Поднимаем исключение выше для обработки

        # Проверяем, подключён ли том
        if container:
            mounts = container.attrs['Mounts']
            if mounts:
                for mount in mounts:
                    log(f"Mounted volume: {mount['Source']} -> {mount['Destination']}")
            else:
                log("WARNING: No volumes mounted!")
        else:
            log("Container not started, skipping mount check.")

        # Удаляем образы с тегом <none>
        log("Cleaning up dangling images for swasher/movie-filter-pro...")
        remove_none_tag_images(client, Config.IMAGE)

        # Дополнительная очистка неиспользуемых образов
        log("Cleaning up unused images...")
        pruned = client.images.prune()
        log(f"Removed {pruned['ImagesDeleted'] or 'no'} unused images, freed {pruned['SpaceReclaimed']} bytes.")


    except docker.errors.APIError as e:
        log(f"Ошибка при работе с Docker: {e}")
    except Exception as e:
        log(f"Error while work with: {Config.CONTAINER}: {e}")
    finally:
        client.close()


# Класс для обработки HTTP-запросов
class WebhookHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        # Получаем длину тела запроса
        content_length = int(self.headers['Content-Length'])

        # Читаем тело запроса
        post_data = self.rfile.read(content_length)

        try:
            # Парсим JSON из тела запроса
            payload = json.loads(post_data)

            # Извлекаем информацию о репозитории и теге
            repo_name = payload['repository']['repo_name']
            tag = payload['push_data']['tag']

            # Логируем информацию
            log(f"Received webhook for repository: {repo_name}, tag: {tag}")

            # Отправляем ответ об успешном получении веб-хука
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'Webhook received successfully')

            if repo_name == Config.IMAGE and tag == Config.TAG:
                # update_container()
                update_compose()

        except Exception as e:
            # В случае ошибки логируем и отправляем ошибку клиенту
            log(f"Error processing webhook: {e}")
            self.send_response(500)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'Error processing webhook')


# Запуск сервера
if __name__ == '__main__':
    log("\n")
    log("NEW SESSION")
    log("\n")

    os.environ['DOCKER_HOST'] = 'unix:///var/run/docker.sock'
    os.environ["DOCKER_CONFIG"] = "/share/CACHEDEV1_DATA/homes/swasher/webhook"
    docker_check()

    if len(sys.argv) > 1 and sys.argv[1] == "update":
        update_container()
    else:
        server_address = ('', Config.LISTEN_PORT)
        httpd = HTTPServer(server_address, WebhookHandler)
        log(f"Starting webhook server on port {Config.LISTEN_PORT}...")
        httpd.serve_forever()
