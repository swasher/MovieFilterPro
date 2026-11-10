import time
import unicodedata

from django.core.management.base import BaseCommand

from tmdb_adapter.client_singleton import get_english_title, get_tmdb_client_en
from vault.models import Movie


def _is_readable_letter(char: str) -> bool:
    """Латинские и кириллические буквы считаем читаемыми для RU-пользователя."""
    if not char.isalpha():
        return True
    if char.isascii():
        return True
    name = unicodedata.name(char, "")
    return name.startswith("LATIN") or name.startswith("CYRILLIC")


def _has_unreadable_title(value: str | None) -> bool:
    return any(not _is_readable_letter(char) for char in (value or ""))


def _resolve_media_type(movie: Movie) -> str:
    if movie.tmdb_media_type in {"movie", "tv"}:
        return movie.tmdb_media_type
    if movie.movie_type in {
        Movie.MovieType.SERIES,
        Movie.MovieType.MINISERIES,
        Movie.MovieType.SHOW,
    }:
        return "tv"
    return "movie"


class Command(BaseCommand):
    help = (
        "Backfill английских (международных) названий из TMDB en-US "
        "в Movie.title_en."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Ограничить число фильмов (0 = все)",
        )
        parser.add_argument(
            "--non-latin",
            action="store_true",
            help="Только фильмы, у которых title/original_title нелатинские/некириллические",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Перезаписывать уже заполненный title_en",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Запросить TMDB, показать результат, но не писать в БД",
        )
        parser.add_argument(
            "--sleep-ms",
            type=int,
            default=250,
            help="Пауза между запросами к TMDB, мс (по умолчанию 250)",
        )

    def handle(self, *args, **options):
        limit = max(0, int(options.get("limit") or 0))
        only_non_latin = bool(options.get("non_latin"))
        force = bool(options.get("force"))
        dry_run = bool(options.get("dry_run"))
        sleep_ms = max(0, int(options.get("sleep_ms") or 0))

        qs = (
            Movie.objects.filter(tmdb_id__isnull=False)
            .only(
                "id",
                "title",
                "original_title",
                "title_en",
                "tmdb_id",
                "tmdb_media_type",
                "movie_type",
            )
            .order_by("id")
        )

        movies: list[Movie] = []
        skipped_filled = 0
        for movie in qs.iterator(chunk_size=1000):
            if not force and (movie.title_en or "").strip():
                skipped_filled += 1
                continue
            if only_non_latin and not (
                _has_unreadable_title(movie.title)
                or _has_unreadable_title(movie.original_title)
            ):
                continue
            movies.append(movie)
            if limit and len(movies) >= limit:
                break

        total = len(movies)
        self.stdout.write(
            f"Found {total} movie(s) for English title backfill "
            f"(non_latin={only_non_latin}, force={force}, dry_run={dry_run}, "
            f"sleep_ms={sleep_ms}, already_filled_skipped={skipped_filled})"
        )

        updated = 0
        unchanged = 0
        not_found = 0
        failed = 0
        started_at = time.monotonic()
        # Один клиент на весь backfill: не перечитываем UserPreferences на каждый фильм.
        tmdb_en = None

        for index, movie in enumerate(movies, start=1):
            # Всегда запрашиваем en-US у TMDB, без эвристик по языку оригинала:
            # title_en должен быть реальным ответом TMDB, а не догадкой.
            try:
                if tmdb_en is None:
                    tmdb_en = get_tmdb_client_en()
                english_title = get_english_title(
                    movie.tmdb_id,
                    _resolve_media_type(movie),
                    tmdb=tmdb_en,
                )
            except Exception as exc:  # за往外: одна ошибка не должна ронять backfill
                failed += 1
                self.stderr.write(
                    f"[{index}/{total}] id={movie.id} tmdb_id={movie.tmdb_id} "
                    f"ERROR {type(exc).__name__}: {exc}"
                )
                english_title = None

            if not english_title:
                not_found += 1
            elif english_title == (movie.title_en or "").strip():
                unchanged += 1
            else:
                if not dry_run:
                    Movie.objects.filter(pk=movie.pk).update(title_en=english_title)
                movie.title_en = english_title
                updated += 1
                self.stdout.write(
                    f"[{index}/{total}] id={movie.id} tmdb_id={movie.tmdb_id} | "
                    f"{movie.title} | {movie.original_title or '-'} -> {english_title}"
                )

            if index % 50 == 0 or index == total:
                elapsed = time.monotonic() - started_at
                self.stdout.write(
                    f"Progress {index}/{total}: updated={updated}, unchanged={unchanged}, "
                    f"not_found={not_found}, failed={failed}, elapsed={elapsed:.1f}s"
                )

            if sleep_ms and index < total:
                time.sleep(sleep_ms / 1000)

        mode = "DRY RUN" if dry_run else "DONE"
        self.stdout.write(
            f"{mode}: updated={updated}, unchanged={unchanged}, not_found={not_found}, "
            f"failed={failed}, skipped_filled={skipped_filled}, total={total}"
        )
