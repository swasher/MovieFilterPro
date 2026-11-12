_GREEN := "\033[32m[%s]\033[0m %s\n" # Green text for "printf"
_RED := "\033[31m[%s]\033[0m %s\n" # Red text for "printf"
.SILENT:
.ONESHELL:
.PHONY: all front
.DEFAULT_GOAL := help

define PRINT_HELP_PYSCRIPT
import re, sys

for line in sys.stdin:
	match = re.match(r'^([a-zA-Z_-]+):.*?## (.*)$$', line)
	if match:
		target, help = match.groups()
		print("%-20s %s" % (target, help))
endef
export PRINT_HELP_PYSCRIPT


# So in short:
# $  -> makefile variable => use a single dollar sign
# $$ -> shell variable => use two dollar signs

include .env

help: ## make help to get help!
	@python -c "$$PRINT_HELP_PYSCRIPT" < $(MAKEFILE_LIST)

superuser:
	# this environment variables came from doppler:
	#	DJANGO_SUPERUSER_USERNAME=testuser
	#	DJANGO_SUPERUSER_PASSWORD=testpass
	#	DJANGO_SUPERUSER_EMAIL="admin@admin.com"
	doppler run -- python manage.py createsuperuser --noinput

migrations:
	doppler run -- python manage.py makemigrations

migrate:
	doppler run -- python manage.py migrate

initital:
	# this command create datatables
	doppler run -- python manage.py makemigrations moviefilter
	doppler run -- python manage.py migrate
	@$(MAKE) load_fixtures
	@$(MAKE) superuser

collect:
	doppler run -- python manage.py collectstatic --noinput

flush:
	python manage.py flush --no-input


build:
	doppler run -- docker compose up -d  --build

create-volume: ## Содать том для персистентного хранения DB
	docker volume create moviefilterpro_postgres_data

remove-volume: ## Удалить контейнер со всей dev базой данных!!!
	docker rm -f postgres-local

create-container: ## только для создания контейнера, если он не существует.
	docker run -d \
	  --name postgres-mfp \
	  --restart unless-stopped \
	  --env-file .env \
	  -v moviefilterpro_postgres_data:/var/lib/postgresql \
	  -p 5432:5432 \
	  postgres:18-alpine

up: ## старт контейнера
	docker start postgres-mfp

down: ## стоп контейнера
	docker stop postgres-mfp

remove: ## удалить контейнер
	docker rm -f postgres-mfp

# Локальный registry на QNAP (контейнер registry:2 на порту 5000).
# С dev-машины образ пушится по DNS-имени qnap:5000, а на самом QNAP тот же
# registry доступен как 127.0.0.1:5000 (127.0.0.0/8 уже в insecure registries
# у docker-демона Container Station).
REGISTRY_PUSH ?= qnap:5000
REGISTRY_QNAP ?= 127.0.0.1:5000
IMAGE_REPO ?= swasher/movie-filter-pro-v2
IMAGE_TAG ?= amd64
IMAGE_PUSH := $(REGISTRY_PUSH)/$(IMAGE_REPO):$(IMAGE_TAG)
IMAGE_QNAP := $(REGISTRY_QNAP)/$(IMAGE_REPO):$(IMAGE_TAG)
# Имя без registry: именно его прописывает mfp2_create_main_container.sh на QNAP.
IMAGE_LEGACY := $(IMAGE_REPO):$(IMAGE_TAG)

build-and-push:
	# build and upload
	# set -e обязателен: из-за .ONESHELL весь рецепт — один shell-скрипт, и без этого
	# make смотрит только на код возврата последней команды (то есть на финальный echo),
	# поэтому упавшая сборка/деплой раньше выглядели как успех.
	set -e
	# Бамп patch-версии в файле VERSION (pyproject.toml/uv.lock заморожены на 0.0.0,
	# чтобы bump не инвалидировал слой зависимостей в Docker-образе).
	# newline='\n' обязателен: на Windows write_text() по умолчанию пишет CRLF,
	# из-за чего git ругался «CRLF will be replaced by LF» на каждый релиз
	# (в репозитории все файлы хранятся с LF, см. .gitattributes).
	python -c "import pathlib; p = pathlib.Path('VERSION'); v = p.read_text().split('.'); v[-1] = str(int(v[-1]) + 1); p.write_text('.'.join(v).strip() + '\n', newline='\n')"
	python manage.py collectstatic --noinput
	# Сразу фиксируем bump в git, чтобы `make push` не оставлял «грязное» дерево.
	# pathspec (-- VERSION) коммитит только версию и не задевает уже
	# проиндексированные/изменённые файлы пользователя.
	# git add нужен на случай, если VERSION ещё не отслеживается git.
	git add -- VERSION
	git commit -m "Release v$$(cat VERSION)" -- VERSION
	# Если остались другие незакоммиченные файлы — образ собирается из состояния,
	# которого нет в git. Не блокируем деплой, но предупреждаем.
	if [ -n "$$(git status --porcelain)" ]; then
		echo "WARNING: есть незакоммиченные изменения, их нет в релизном коммите:"
		git status --short
	fi
	# ВАЖНО: docker build и docker push — отдельными командами, НЕ через `&&`.
	# `set -e` не прерывает скрипт для команды, которая стоит в && -списке не
	# последней, поэтому раньше упавшая сборка молча продолжалась: скрипт
	# «заливал» образ, дергал QNAP (pull старого образа) и рапортовал успех.
	# Явные проверки ниже гарантируют, что при ошибке деплой не поедет.
	if ! docker build $(CACHE_OPTION) -t $(IMAGE_PUSH) .; then
		echo "ERROR: сборка образа провалилась — деплой на QNAP отменён."
		exit 1
	fi
	if ! docker push $(IMAGE_PUSH); then
		echo "ERROR: push образа в локальный registry $(REGISTRY_PUSH) провалился — деплой на QNAP отменён."
		exit 1
	fi
	@echo "--- Образ успешно залит в локальный registry $(REGISTRY_PUSH)! ---"
	@echo "Обновляю контейнер на QNAP по SSH (pull + пересоздание)..."
	# docker tag нужен потому, что mfp2_create_main_container.sh запускает
	# контейнер по имени без registry (swasher/movie-filter-pro-v2:amd64).
	ssh -o BatchMode=yes qnap 'cd /share/PERMANENT/movie-filter-pro-v2 && export PATH=/share/CACHEDEV1_DATA/.qpkg/container-station/bin:$$PATH && docker pull $(IMAGE_QNAP) && docker tag $(IMAGE_QNAP) $(IMAGE_LEGACY) && docker rm -f movie-filter-pro-v2 && ./mfp2_create_main_container.sh && docker image prune -f'
	@echo "updated to v.$$(cat VERSION)"

# Деплой с кэшем (обычный релиз)
push: CACHE_OPTION=
push: build-and-push

# Деплой без кэша слоёв образа — только для диагностики «странных» сборок.
# ВНИМАНИЕ: --no-cache НЕ чистит BuildKit cache-mount'ы (uv/pnpm/apt),
# для полного сброса кэшей: docker builder prune -af
# Стоимость: заново скачивается Chromium (~120 МБ) и собирается фронт.
push-no-cache: CACHE_OPTION=--no-cache
push-no-cache: build-and-push

#docker_github_login:
#	echo $$GITHUB_TOKEN | docker login ghcr.io -u $$GITHUB_USERNAME --password-stdin
#
#github_build_and_push: CACHE_OPTION=--no-cache
#github_build_and_push:
#	uv version --frozen --bump patch
#	uv run python manage.py collectstatic --noinput
#	uv export --no-dev --format requirements-txt > requirements.txt
#	docker buildx build --platform linux/arm/v7 $(CACHE_OPTION) \
#    -t ghcr.io/$$GITHUB_USERNAME/movie-filter-pro:armv7 \
#    --push .
#	rm requirements.txt




huey:
	uv run python -m huey.bin.huey_consumer movie_filter_pro.huey.HUEY -k thread -w 2 -v -S

daphne:
	watchfiles --filter python "daphne -b 127.0.0.1 -p 8000 movie_filter_pro.asgi:application"

front:
	cd front && pnpm run dev

tunnel:
	# first run `ngrok config add-authtoken <ngrok token>`  - token on page 'your-autotoken', not 'tunnels->autotoken'!!!
	ngrok http 8000




#
# DEBUGGING
#
get_details_one_movie:
	python manage.py get_details_one_movie 2104619

cloc:
	cloc . --exclude-dir=.venv,migrations,.idea,.git,__pycache__,static,collectstatic,.svelte-kit,build,node_modules,components,media


ngrok:
	@ngrok config add-authtoken $(NGROK_AUTHTOKEN)
	ngrok http 5173
