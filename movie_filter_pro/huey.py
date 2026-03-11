import os
from pathlib import Path

from decouple import config
from pathlib import Path

import django
from django.apps import apps
from huey import SqliteHuey


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "movie_filter_pro.settings")
if not apps.ready:
    django.setup()

huey_db_path = Path(config("HUEY_SQLITE_PATH"))
HUEY = SqliteHuey(filename=str(huey_db_path))

# Ensure tasks are imported when the consumer loads this module.
import vault.tasks  # noqa: E402,F401
