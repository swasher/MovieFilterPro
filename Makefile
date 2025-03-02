_GREEN := "\033[32m[%s]\033[0m %s\n" # Green text for "printf"
_RED := "\033[31m[%s]\033[0m %s\n" # Red text for "printf"
.SILENT:
.PHONY: all

# So in short:
# $  -> makefile variable => use a single dollar sign
# $$ -> shell variable => use two dollar signs


dummy:
	echo Do not run without arguments! $(_R)

factory:
	doppler run --  python -m factory_boy.main

install:
	pipenv install

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
	doppler run -- docker compose up -d

down:
	docker compose down

freeze:
	pipenv run pip freeze > requirements.txt

ssh:
	docker exec -it sandglass_db_1 bash

messages:
	echo 'First `make messages`, then POEdit, then `compile`!'
	# update translation strings
	django-admin makemessages --all --ignore=env

compile:
	echo 'First `make messages`, then POEdit, then `compile`!'
	django-admin compilemessages --ignore=env

provision:
	# === work under WSL ===
	# Install server fron scratch. Only ssh access needed.
	# -vvv for three level verbosity
	# usage:
	#    make provision server=[production|stage]
	wsl doppler run -p print_mes -c $(server) -- ansible-playbook --limit $(server) ansible/provision.yml

full_deploy:
	# === work under WSL ===
	# Deploy software on tuned server. Full deploy.
	wsl ansible-playbook --limit $(server) ansible/provision.yml --tags "deploy_tag"

deploy:
	# === work under WSL ===
	# Deploy software on tuned server. Quick deploy.
	wsl doppler run -p print_mes -c $(server) -- ansible-playbook --limit $(server) ansible/deploy.yml

vault-edit:
	# === work under WSL ===
	ansible-vault edit --vault-password-file=.vault_password -v ansible/group_vars/vault.yml

vault-decrypt:
	# === work under WSL ===
	ansible-vault decrypt --vault-password-file=.vault_password -v ansible/group_vars/vault.yml

vault-encrypt:
	# === work under WSL ===
	ansible-vault encrypt --encrypt-vault-id=default --vault-password-file=.vault_password -v ansible/group_vars/vault.yml

ssl:
	# DEPRECATED
	# === work under WSL ===
	# creating ssl certificates
	openssl req -x509 -sha256 -days 3560 -nodes -newkey rsa:2048 -subj "/CN=production/C=LV/L=Riga" -keyout rootCA.key -out rootCA.crt

copydb-dev-prod:
	@read  -p "Are you sure? This will delete PRODUCTION database!!! [y/N] " ans && ans=$${ans:-N} ; \
    if [ $${ans} = y ] || [ $${ans} = Y ]; then \
		printf $(_RED) "YES" ; \
		pg_dump --format=custom --dbname=postgresql://postgres:postgres@localhost:5432/postgres \
		| PGPASSWORD=$(DATABASE_PASSWORD) pg_restore -v --clean --host=$(DATABASE_HOST) --username=$(DATABASE_USER) --dbname=$(DATABASE_NAME) ; \
	else \
        printf $(_GREEN) "NO" ; \
    fi
	# pg_dump --clean --create --format=custom --dbname=postgresql://postgres:postgres@localhost:5432/postgres | pg_restore --clean --create --dbname=postgresql://$(DATABASE_USER):$(DATABASE_PASSWORD)@$(DATABASE_HOST):5432/$(DATABASE_NAME) ; \

DB_PROD := $(shell doppler secrets -p print_mes -c production get DB_URL --plain)
DB_STAGE := $(shell doppler secrets -p print_mes -c stage get DB_URL --plain)
copydb-prod-stage:
	pg_dump --format=custom --dbname=$(DB_PROD)| pg_restore -v --clean -d $(DB_STAGE)


tunnel:
	# first run `ngrok config add-authtoken <ngrok token>`  - token on page 'your-autotoken', not 'tunnels->autotoken'!!!
	ngrok http 8000


login:
	docker login

push:
	# build and upload
	python manage.py collectstatic --noinput
	uv export --format requirements-txt > requirements.txt
	docker buildx build --platform linux/arm/v7 -t swasher/movie-filter-pro:armv7 --push .
	#docker buildx build --platform linux/arm/v7 --no-cache -t swasher/movie-filter-pro:armv7 --push .
	rm requirements.txt

run:
	# if you need run, you must build image with x86 compatible settings (not implemented)
	docker run -p 8000:8000 movie-filter-pro

pack:
	docker save -o movie-filter-pro.tar movie-filter-pro
