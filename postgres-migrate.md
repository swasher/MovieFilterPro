### 1. Дамп из старой SQLite (в корне проекта, где лежит db.sqlite3)

> Активируй venv, если не активен.  
> В settings.py временно верни 
> ```
> DATABASES = {
>     'default': {
>         'ENGINE': 'django.db.backends.sqlite3',
>         'NAME': BASE_DIR / 'db.sqlite3',
>     }
> }
> ```

    uv run python manage.py dumpdata \
    --natural-foreign --natural-primary \
    -e contenttypes -e auth.Permission \
    -o dump.json

### 2. Загрузка в Postgres (схема уже создана migrate)

Возвращаем `settings.py` как для postgres.

    uv run python manage.py loaddata dump.json

### 3. Сброс последовательностей (обязательно для Postgres после loaddata) всех приложений, которые имеют миграции:

Смотрим, какие приложения имеют миграции:

    ❯ ls -d */migrations/ 2>/dev/null | sed 's|/migrations/||'
    core/
    moviefilter/
    vault/

Сбрасываем:

    uv run python manage.py sqlsequencereset moviefilter vault core  \
        | uv run python manage.py dbshell

### 4. (Опционально) Проверка:  

    uv run python manage.py shell -c "
    from vault.models import Movie, Person
    from moviefilter.models import MovieRSS
    print('Movies:', Movie.objects.count())
    print('Persons:', Person.objects.count())
    print('RSS:', MovieRSS.objects.count())
    "