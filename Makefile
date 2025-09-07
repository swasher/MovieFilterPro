_GREEN := "\033[32m[%s]\033[0m %s\n" # Green text for "printf"
_RED := "\033[31m[%s]\033[0m %s\n" # Red text for "printf"
.SILENT:
.PHONY: all

# So in short:
# $  -> makefile variable => use a single dollar sign
# $$ -> shell variable => use two dollar signs

include .env
export WATCHTOWER_TOKEN

dummy:
	echo Do not run without arguments! $(_R)

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

TABLES = \
 moviefilter.Country

save_fixtures:
	read  -p "Are you sure? THIS WILL DELETE ALL EXISTING FIXTURES!!! [y/N] " ans && ans=$${ans:-N} ; \
    if [ $${ans} = y ] || [ $${ans} = Y ]; then \
		printf $(_RED) "YES" ; \
		for table in $(TABLES); do \
			doppler run -- python -Xutf8 manage.py dumpdata $$table --indent 4 --output fixtures/$$table.json ; \
		done; \
		doppler run -- python -Xutf8 manage.py dumpdata auth --natural-foreign --natural-primary -e auth.Permission --indent 4 --output fixtures/auth.Group.json ; \
    else \
        printf $(_GREEN) "NO" ; \
    fi
	echo 'Complete.'


load_fixtures:
	for table in $(TABLES); do \
		doppler run -- python manage.py loaddata fixtures/$$table.json; \
	done


flush_and_load_fixtures:
	# remove all data from tables and reload fixtures; not affect on migrations.
	python manage.py flush --no-input
	python manage.py loaddata fixtures/auth.Group.json
	for table in $(TABLES); do \
		python manage.py loaddata fixtures/$$table.json; \
	done



dropdb:
	@read  -p "Are you sure? IT WILL DELETE ALL EXISTING DATABASEs!!! [y/N] " ans && ans=$${ans:-N} ; \
    if [ $${ans} = y ] || [ $${ans} = Y ]; then \
		printf $(_GREEN) "YES" ; \
		#rm -rf core/migrations/* ; \
		#rm -rf orders/migrations/* ; \
		#rm -rf stanzforms/migrations/* ; \
		#rm -rf warehouse/migrations/* ; \
		docker compose down ; \
		docker volume prune --force ; \
		docker compose up -d ; \
		sleep 2 ; \
		#python manage.py makemigrations --no-input core orders stanzforms warehouse ; \
		python manage.py migrate ; \
		#python manage.py loaddata */fixtures/*.json ; \
		#python manage.py createsuperuser --username=swasher --email=mr.swasher@gmail.com; becouse it's already in fixtures ; \
    else \
        printf $(_RED) "NO" ; \
    fi
	@echo 'Next steps...'


dropdb_and_migrations:
	@read -p "Are you sure? IT WILL DELETE ALL EXISTING DATABASEs!!! [y/N] " ans && ans=$${ans:-N} ; \
    if [ $${ans} = y ] || [ $${ans} = Y ]; then \
		printf $(_RED) "YES" ; \
		rm -rf core/migrations/* ; \
		rm -rf orders/migrations/* ; \
		rm -rf stanzforms/migrations/* ; \
		rm -rf warehouse/migrations/* ; \
		docker compose down ; \
		docker volume prune --force ; \
		docker compose up -d ; \
		sleep 2 ; \
		python manage.py makemigrations --no-input core orders stanzforms warehouse ; \
		python manage.py migrate ; \
#		python manage.py loaddata */fixtures/*.json ; \
    else \
        printf $(_RED) "NO" ; \
    fi
	@echo 'Next steps...'



build:
	doppler run -- docker compose up -d  --build

up:
	docker compose up -d

down:
	docker compose down

freeze:
	pipenv run pip freeze > requirements.txt

ssh:
	docker exec -it sandglass_db_1 bash


tunnel:
	# first run `ngrok config add-authtoken <ngrok token>`  - token on page 'your-autotoken', not 'tunnels->autotoken'!!!
	ngrok http 8000


login:
	docker login

build-and-push:
	# build and upload
	uv version --frozen --bump patch
	python manage.py collectstatic --noinput
	uv export --no-dev --format requirements-txt > requirements.txt
	docker buildx build --platform linux/arm/v7 $(CACHE_OPTION) -t swasher/movie-filter-pro:armv7 --push .
	rm requirements.txt
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



run:
	# if you need run, you must build image with x86 compatible settings (not implemented)
	docker run -p 8000:8000 movie-filter-pro

pack:
	docker save -o movie-filter-pro.tar movie-filter-pro
