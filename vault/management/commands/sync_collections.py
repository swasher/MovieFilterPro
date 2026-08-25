import logging
from django.core.management.base import BaseCommand

from vault.models import Movie
from vault.services.tmdb_movie_sync_service import TMDBMovieSyncService

logger = logging.getLogger("vault.collection_sync")


class Command(BaseCommand):
    help = "Backfill коллекций TMDB: пересинхронизирует фильмы с tmdb_id и подтянет belongs_to_collection."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Ограничить число фильмов (0 = все)",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            help="Синкнуть все фильмы с tmdb_id (по умолчанию только без коллекции)",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Принудительный rematch (force_rematch=True)",
        )

    def handle(self, *args, **options):
        limit = int(options.get("limit") or 0)
        sync_all = bool(options.get("all"))
        force = bool(options.get("force"))

        qs = Movie.objects.filter(tmdb_id__isnull=False)
        # По умолчанию — только без коллекции (для backfill до введения фичи). С --all — все.
        if not sync_all:
            qs = qs.filter(collection__isnull=True)
        qs = qs.order_by("id")
        if limit > 0:
            qs = qs[:limit]

        total = qs.count() if limit == 0 else len(list(qs))
        # для qs с limit нам уже считали slice, надо пересчитать корректно
        if limit > 0:
            movies = list(qs)
            total = len(movies)
        else:
            movies = list(qs)

        self.stdout.write(f"Found {total} movie(s) to sync collections (all={sync_all}, force={force})")

        ok = 0
        attached = 0
        detached = 0
        errors = 0
        skipped = 0

        for movie in movies:
            prev_coll = movie.collection_id
            try:
                result = TMDBMovieSyncService.sync_movie(movie, force_rematch=force)
            except Exception as exc:
                errors += 1
                self.stdout.write(self.style.ERROR(f"[{movie.id}] {movie.title} — error: {exc}"))
                logger.warning("sync_collections error movie_id=%s: %s", movie.id, exc, exc_info=True)
                continue

            # sync_movie может вернуть needs_confirmation / needs_user_choice — коллекция не затронута
            if result.status in ("needs_confirmation", "needs_user_choice"):
                skipped += 1
                self.stdout.write(self.style.WARNING(f"[{movie.id}] {movie.title} — skipped ({result.status})"))
                continue

            if result.status == "error":
                errors += 1
                self.stdout.write(self.style.ERROR(f"[{movie.id}] {movie.title} — error: {result.message}"))
                continue

            ok += 1
            # Проверяем изменилась ли коллекция
            movie.refresh_from_db(fields=["collection"])
            new_coll = movie.collection_id
            if prev_coll is None and new_coll is not None:
                attached += 1
                self.stdout.write(self.style.SUCCESS(f"[{movie.id}] {movie.title} — attached collection {new_coll}"))
            elif prev_coll is not None and new_coll is None:
                detached += 1
                self.stdout.write(f"[{movie.id}] {movie.title} — detached")
            elif "collection" in (result.updated_fields or ()):
                self.stdout.write(f"[{movie.id}] {movie.title} — updated collection")
            else:
                self.stdout.write(f"[{movie.id}] {movie.title} — ok (no collection change)")

        self.stdout.write(
            self.style.SUCCESS(
                f"Done: ok={ok} attached={attached} detached={detached} skipped={skipped} errors={errors} total={total}"
            )
        )
