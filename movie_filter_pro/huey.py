import os
from pathlib import Path

import django
from django.apps import apps
from huey import SqliteHuey


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "movie_filter_pro.settings")
if not apps.ready:
    django.setup()

db_dir = Path(__file__).resolve().parent
HUEY = SqliteHuey(filename=str(db_dir / "huey_tasks.db"))

# Ensure tasks are imported when the consumer loads this module.
import vault.tasks  # noqa: E402,F401
