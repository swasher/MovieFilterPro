_GREEN := "\033[32m[%s]\033[0m %s\n" # Green text for "printf"
_RED := "\033[31m[%s]\033[0m %s\n" # Red text for "printf"
.SILENT:
.ONESHELL:
.PHONY: all
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
export WATCHTOWER_TOKEN

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


login:
	docker login

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

build-and-push:
	# build and upload
	uv version --frozen --bump patch
	python manage.py collectstatic --noinput
	uv export --no-dev --no-hashes --format requirements-txt > requirements.txt
	docker build -t swasher/movie-filter-pro-v2:amd64 . && docker push swasher/movie-filter-pro-v2:amd64
	rm requirements.txt
	@echo "--- Образ успешно залит в Docker Hub! ---"
	@echo "Отправляю сигнал на QNAP и жду, пока Watchtower скачает обновление..."
	curl -H "Authorization: Bearer $$WATCHTOWER_TOKEN" qnap:9090/v1/update

# Деплой с кэшем
push: CACHE_OPTION=
push: build-and-push

# Деплой без кэша
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