"""Ручной синк bestfilmsof без Huey (диагностика / прогрев кеша)."""

import json

from django.core.management.base import BaseCommand, CommandError

from bestfilmsof.constants import GENRES
from bestfilmsof.services.sync_service import SyncService


class Command(BaseCommand):
    help = (
        "Синхронизировать список bestfilmsof по году/жанру или жанровую сводку. "
        "Примеры: sync_bestfilms 2010 --genre drama; sync_bestfilms --genre drama"
    )

    def add_arguments(self, parser):
        parser.add_argument("year", nargs="?", type=int, help="Год (нет — сводка по жанру)")
        parser.add_argument("--genre", default="", help="Жанр-слаг (пусто — весь год)")
        parser.add_argument(
            "--force", action="store_true", help="Синкать даже свежий кеш"
        )

    def handle(self, *args, **options):
        year = options["year"]
        genre = (options["genre"] or "").lower()

        if genre and genre not in GENRES:
            raise CommandError(f"unknown genre: {genre!r}. Known: {', '.join(GENRES)}")
        if year is None and not genre:
            raise CommandError("specify a year and/or --genre")

        claimed, row, token = SyncService.claim(year, genre, force=options["force"])
        if not claimed:
            self.stdout.write(
                self.style.WARNING(
                    f"sync skipped: {row.key} (status={row.status}, "
                    f"synced_at={row.synced_at})"
                )
            )
            return

        result = SyncService.run_claimed(year, genre, token)
        self.stdout.write(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        if result.get("status") != "ok":
            raise CommandError(f"sync failed: {result}")
