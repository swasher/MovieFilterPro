import os
from pathlib import Path

from decouple import config
from pathlib import Path

import django
from django.apps import apps
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from huey import SqliteHuey


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "movie_filter_pro.settings")
if not apps.ready:
    django.setup()

raw_value = config("HUEY_SQLITE_PATH", default="huey.sqlite3")

if not raw_value:
    raise ImproperlyConfigured("HUEY_SQLITE_PATH cannot be empty")
if raw_value.startswith("sqlite:"):
    raise ImproperlyConfigured("HUEY_SQLITE_PATH must be a filesystem path, not sqlite URL")

huey_db_path = Path(raw_value)
if not huey_db_path.is_absolute():
    huey_db_path = settings.BASE_DIR / huey_db_path

# Опционально: проверить, что директория существует
huey_db_path.parent.mkdir(parents=True, exist_ok=True)


HUEY = SqliteHuey(filename=str(huey_db_path))

# Ensure tasks are imported when the consumer loads this module.
import vault.tasks  # noqa: E402,F401
