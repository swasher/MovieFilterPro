import csv
import logging
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction
from slugify import slugify

from core.models import Country
from movie_filter_pro.settings import SKIP
from moviefilter.models import MovieRSS
from vault.models import (
    FavoritePerson,
    Genre,
    Movie,
    MoviePerson,
    Person,
    UserList,
    UserListMovie,
    UserMovie,
)


logger = logging.getLogger('debug_logger')


STATUS_TO_WATCH_STATUS = {
    'Буду смотреть': UserMovie.WatchStatus.PLAN,
    'Просмотрен': UserMovie.WatchStatus.WATCHED,
    'Не буду смотреть': UserMovie.WatchStatus.SKIP,
}

SYSTEM_LIST_TITLES = {
    'Просмотрено',
    'Буду смотреть',
    'Не буду смотреть',
}

TYPE_TO_MOVIE_TYPE = {
    'Фильм': Movie.MovieType.MOVIE,
    'Сериал': Movie.MovieType.SERIES,
    'Мультфильм': Movie.MovieType.CARTOON,
    'Аниме': Movie.MovieType.ANIME,
    'ТВ шоу': Movie.MovieType.SHOW,
}

TRASH_GENRE_RE = re.compile(r'^\d{4}-[eе]$')


def parse_decimal(value: str):
    if not value:
        return None
    cleaned = re.sub(r'[^0-9,.-]', '', str(value)).replace(',', '.').strip()
    if not cleaned:
        return None
    try:
        return Decimal(cleaned)
    except Exception:
        return None


def normalize_decimal_for_field(
    value: Decimal | None,
    field,
    min_value: Decimal | None = None,
    max_value: Decimal | None = None,
):
    if value is None:
        return None
    quant = Decimal('1').scaleb(-field.decimal_places)
    try:
        value = value.quantize(quant)
    except (InvalidOperation, ValueError):
        return None

    max_abs = (Decimal(10) ** (field.max_digits - field.decimal_places)) - quant
    if abs(value) > max_abs:
        return None
    if min_value is not None and value < min_value:
        return None
    if max_value is not None and value > max_value:
        return None
    return value


def parse_int(value: str):
    if value is None:
        return None
    cleaned = re.sub(r'[^0-9-]', '', str(value))
    if not cleaned:
        return None
    try:
        return int(cleaned)
    except ValueError:
        return None


def parse_date(value: str):
    if not value or not str(value).strip():
        return None
    for fmt in ('%Y-%m-%d', '%d.%m.%Y', '%Y/%m/%d'):
        try:
            return datetime.strptime(str(value).strip(), fmt).date()
        except ValueError:
            continue
    return None


def unique_slug(base_slug: str):
    slug = base_slug
    counter = 1
    while slug and Movie.objects.filter(slug=slug).exists():
        counter += 1
        slug = f"{base_slug}-{counter}"
    return slug


class Command(BaseCommand):
    help = 'Импортирует выгрузку Kinorium из папки vault/current_csv в пустые таблицы Vault.'

    MIN_IMDB_RATING = Decimal('0.0')
    MAX_IMDB_RATING = Decimal('10.0')

    def _iter_csv(self, path: Path):
        if not path.exists():
            self.stdout.write(self.style.WARNING(f"{path.name} not found, skipping."))
            return []
        with path.open(encoding='utf-16') as fh:
            reader = csv.DictReader(fh, delimiter='\t')
            return list(reader)

    def _ensure_user(self):
        user, created = User.objects.get_or_create(
            id=1,
            defaults={'username': 'import_user'},
        )
        if created:
            user.set_unusable_password()
            user.save()
        return user

    def _ensure_unknown_country(self):
        country, _ = Country.objects.get_or_create(name='Unknown', defaults={'code': 'XX'})
        return country

    def _get_country(self, name: str, cache: dict, unknown_country: Country):
        if not name:
            return unknown_country
        name = name.strip()
        if name in cache:
            return cache[name]
        base_code = (name[:2].upper() if len(name) >= 2 else 'XX')
        code = base_code
        suffix = 1
        while Country.objects.filter(code=code).exclude(name=name).exists():
            suffix += 1
            code = f"{base_code[:1]}{suffix:01d}" if len(base_code) == 2 else f"X{suffix}"
            if len(code) > 2:
                code = code[:2]
        country, _ = Country.objects.get_or_create(name=name, defaults={'code': code})
        cache[name] = country
        return country

    def _get_or_create_person(self, full_name: str, original_name: str, note: str, cache: dict, unknown_country: Country):
        if not full_name and not original_name:
            return None
        key = (full_name or original_name).strip()
        if key in cache:
            return cache[key]

        idx = len(cache) + 1
        tmdb_id = f"k{idx:09d}"
        imdb_id = f"im{idx:08d}"
        person = Person.objects.create(
            tmdb_id=tmdb_id,
            imdb_id=imdb_id,
            name=full_name or original_name or '',
            original_name=original_name or full_name or '',
            biography=note or '',
            country=unknown_country,
        )
        cache[key] = person
        return person

    def _movie_from_row(self, row):
        title = (row.get('Title') or '').strip()
        original_title = (row.get('Original Title') or '').strip()
        if not title:
            title = original_title
        if not title:
            return None

        raw_year = (row.get('Year') or '').strip()
        year = None
        year_end = None
        if '-' in raw_year:
            parts = raw_year.split('-', 1)
            year = parse_int(parts[0])
            year_end = parse_int(parts[1])
        else:
            year = parse_int(raw_year)

        movie_type = TYPE_TO_MOVIE_TYPE.get(row.get('Type'), Movie.MovieType.MOVIE)
        status = Movie.Status.RELEASED
        duration = parse_int(row.get('Runtime'))
        release_date = parse_date(row.get('World premier date') or row.get('Digital premier date'))

        slug_source = title
        base_slug = slugify(slug_source) if slug_source else None
        slug = unique_slug(base_slug) if base_slug else None

        budget = normalize_decimal_for_field(
            parse_decimal(row.get('Budget')),
            Movie._meta.get_field('budget'),
        )
        box_office = normalize_decimal_for_field(
            parse_decimal(row.get('Box world') or row.get('Box USA') or row.get('Box RU')),
            Movie._meta.get_field('box_office'),
        )
        imdb_rating = normalize_decimal_for_field(
            parse_decimal(row.get('IMDb rating')),
            Movie._meta.get_field('imdb_rating'),
            min_value=self.MIN_IMDB_RATING,
            max_value=self.MAX_IMDB_RATING,
        )
        imdb_votes = parse_int(row.get('IMDb cnt'))
        if imdb_votes is not None and imdb_votes < 0:
            imdb_votes = None

        return {
            'title': title,
            'original_title': original_title,
            'year': year,
            'year_end': year_end,
            'duration': duration,
            'movie_type': movie_type,
            'status': status,
            'release_date': release_date,
            'slug': slug,
            'description': row.get('Note') or '',
            'poster': None,
            'age_rating': (row.get('Age limit') or '').strip(),
            'budget': budget,
            'box_office': box_office,
            'imdb_rating': imdb_rating,
            'imdb_votes': imdb_votes,
            'source': Movie.Source.KINORIUM,
        }

    def _is_valid_genre(self, value: str) -> bool:
        genre = (value or '').strip()
        if not genre:
            return False
        return TRASH_GENRE_RE.fullmatch(genre) is None

    def _append_movie_note(self, user, movie: Movie, text: str):
        value = (text or '').strip()
        if not value:
            return
        user_movie = self._get_or_create_user_movie(user, movie)
        existing = (user_movie.note or '').strip()
        if not existing:
            user_movie.note = value
            user_movie.save(update_fields=['note', 'updated_at'])
            return
        if value in existing:
            return
        user_movie.note = f"{existing}\n\n{value}"
        user_movie.save(update_fields=['note', 'updated_at'])

    def _movie_lookup_keys(self, title: str, original_title: str, year: int | None):
        title_key = (title or '').strip()
        original_key = (original_title or '').strip()
        return (title_key, original_key, year), (title_key, year)

    def _find_movie(self, row: dict, movie_by_full_key: dict, movie_by_title_year: dict):
        title = row.get('Title') or ''
        original_title = row.get('Original Title') or ''
        year = parse_int(row.get('Year'))
        full_key, fallback_key = self._movie_lookup_keys(title, original_title, year)
        movie = movie_by_full_key.get(full_key)
        if movie:
            return movie
        return movie_by_title_year.get(fallback_key)

    def _get_or_create_user_movie(self, user, movie):
        user_movie, _ = UserMovie.objects.get_or_create(user=user, movie=movie)
        return user_movie

    def _set_watch_status(self, user, movie, watch_status):
        user_movie = self._get_or_create_user_movie(user, movie)
        if user_movie.watch_status != watch_status:
            user_movie.watch_status = watch_status
            user_movie.save(update_fields=['watch_status', 'updated_at'])

    def _set_favorite(self, user, movie):
        user_movie = self._get_or_create_user_movie(user, movie)
        if not user_movie.is_favorite:
            user_movie.is_favorite = True
            user_movie.save(update_fields=['is_favorite', 'updated_at'])

    def _add_to_custom_list(self, user, movie, list_title: str):
        user_list, _ = UserList.objects.get_or_create(user=user, name=list_title)
        UserListMovie.objects.get_or_create(user_list=user_list, movie=movie)

    def _set_rating(self, user, movie, rating, watched_at=None):
        if rating is None or rating < 1 or rating > 10:
            return
        user_movie = self._get_or_create_user_movie(user, movie)
        user_movie.rating = rating
        user_movie.watch_status = UserMovie.WatchStatus.WATCHED
        if watched_at is not None:
            user_movie.watched_at = watched_at
        user_movie.save(update_fields=['rating', 'watch_status', 'watched_at', 'updated_at'])

    def _create_or_get_movie(self, row, movie_by_full_key, movie_by_title_year, person_cache, country_cache, unknown_country):
        movie_defaults = self._movie_from_row(row)
        if movie_defaults is None:
            return None, False
        title = movie_defaults['title']
        year = movie_defaults['year']

        movie, created = Movie.objects.get_or_create(
            title=title,
            year=year,
            defaults=movie_defaults,
        )
        if movie_defaults.get('slug') and not movie.slug:
            movie.slug = movie_defaults['slug']
            movie.save(update_fields=['slug'])

        full_key, fallback_key = self._movie_lookup_keys(title, movie_defaults['original_title'], year)
        movie_by_full_key[full_key] = movie
        movie_by_title_year[fallback_key] = movie

        # genres
        for genre_name in (row.get('Genres') or '').split(','):
            name = genre_name.strip()
            if not self._is_valid_genre(name):
                continue
            genre, _ = Genre.objects.get_or_create(name=name)
            movie.genres.add(genre)

        # countries
        for cn in (row.get('Countries') or '').split(','):
            name = cn.strip()
            if not name:
                continue
            country = self._get_country(name, country_cache, unknown_country)
            movie.countries.add(country)

        # directors
        for director in (row.get('Directors') or '').split(','):
            name = director.strip()
            if not name:
                continue
            person = self._get_or_create_person(name, name, None, person_cache, unknown_country)
            if person:
                MoviePerson.objects.get_or_create(movie=movie, person=person, role='director')

        # actors
        for order, actor in enumerate((row.get('Actors') or '').split(',')):
            name = actor.strip()
            if not name:
                continue
            person = self._get_or_create_person(name, name, None, person_cache, unknown_country)
            if person:
                MoviePerson.objects.get_or_create(
                    movie=movie,
                    person=person,
                    role='actor',
                    defaults={'order': order},
                )

        return movie, created

    # ------------------------------------ #
    #     Import Kinozal HIDE movies       #
    # ------------------------------------ #

    @staticmethod
    def _rss_year_as_int(rss: MovieRSS) -> int | None:
        """Год в Kinozal может быть диапазоном (1982-1994), берём первые 4 цифры."""
        raw = (rss.year or '').strip()
        if not raw:
            return None
        primary = raw[:4]
        return int(primary) if primary.isdigit() else None

    @staticmethod
    def _find_vault_movie(rss: MovieRSS, year: int | None) -> Movie | None:
        """Умное сопоставление Kinozal <-> Vault по title/original_title/year."""
        title = (rss.title or '').strip()
        original_title = (rss.original_title or '').strip()

        movie = Movie.objects.filter(title=title, original_title=original_title, year=year).first()
        if movie:
            return movie

        if title and original_title:
            movie = Movie.objects.filter(title=title, original_title=original_title).first()
            if movie:
                return movie

        if title and year is not None:
            movie = Movie.objects.filter(title=title, year=year).first()
            if movie:
                return movie

        if original_title and year is not None:
            movie = Movie.objects.filter(original_title=original_title, year=year).first()
            if movie:
                return movie

        return None

    def _import_hidden_movies(self, user):
        self.stdout.write("\n--- Kinozal HIDE movies (SKIP) -> Vault ---")
        hidden_movies = MovieRSS.objects.filter(priority=SKIP)
        total = hidden_movies.count()
        self.stdout.write(f"Found {total} hidden (SKIP) movies in Kinozal")

        created = 0
        skipped_existing = 0
        no_year = 0

        for rss in hidden_movies:
            year = self._rss_year_as_int(rss)
            movie = self._find_vault_movie(rss, year)
            if movie:
                skipped_existing += 1
                logger.info(f"[Kinozal-HIDE] already in Vault, skip: {rss.title} ({year or '?'})")
                continue

            if year is None:
                no_year += 1
                logger.warning(f"[Kinozal-HIDE] missing year, skip: {rss.title}")
                continue

            movie = Movie.objects.create(
                title=rss.title,
                original_title=rss.original_title or None,
                year=year,
                imdb_id=rss.imdb_id or None,
                kinopoisk_id=rss.kinopoisk_id or None,
                poster=rss.poster or None,
                description=rss.plot or '',
            )
            UserMovie.objects.create(
                user=user,
                movie=movie,
                watch_status=UserMovie.WatchStatus.SKIP,
            )
            created += 1
            logger.info(f"[Kinozal-HIDE] created in Vault as 'Не буду смотреть': {rss.title} ({year})")

        self.stdout.write(
            self.style.SUCCESS(
                f"Kinozal HIDE import: processed={total}, created={created}, "
                f"skipped_existing={skipped_existing}, no_year={no_year}"
            )
        )

    @transaction.atomic
    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.SUCCESS("Starting Kinorium CSV data import..."))

        user = self._ensure_user()
        self.stdout.write(self.style.SUCCESS(f"Importing data for user '{user.username}' (id={user.id})"))

        csv_dir = Path(settings.BASE_DIR) / 'vault' / 'current_csv'
        movies_csv = csv_dir / 'backup_76444_movie_list.csv'
        votes_csv = csv_dir / 'backup_76444_votes.csv'
        comments_csv = csv_dir / 'backup_76444_comments.csv'
        notes_csv = csv_dir / 'backup_76444_notes.csv'
        persons_csv = csv_dir / 'backup_76444_person_list.csv'

        person_cache = {}
        country_cache = {}
        unknown_country = self._ensure_unknown_country()
        movie_by_full_key = {}
        movie_by_title_year = {}

        stats = {
            'persons_rows': 0,
            'persons_imported': 0,
            'favorites_added': 0,
            'movies_list_rows': 0,
            'movies_created': 0,
            'movies_matched': 0,
            'movies_no_title': 0,
            'statuses_set': 0,
            'favorites_set': 0,
            'custom_list_rows': 0,
            'ratings_set_list': 0,
            'votes_rows': 0,
            'ratings_set_votes': 0,
            'movies_created_from_votes': 0,
            'votes_skipped': 0,
            'comments_rows': 0,
            'comments_note_applied': 0,
            'comments_status_set': 0,
            'movies_created_from_comments': 0,
            'notes_rows': 0,
            'notes_note_applied': 0,
            'movies_created_from_notes': 0,
        }

        failures = []

        def _register_failure(source, row, exc):
            title = (row.get('Title') or row.get('Original Title') or '').strip()
            failures.append((source, title or '<no title>', f"{type(exc).__name__}: {exc}"))
            logger.error(f"[import][{source}] row failed: {title or '<no title>'}", exc_info=True)

        # 1. Favorite persons
        self.stdout.write("\n--- Persons / Favorites ---")
        for row in self._iter_csv(persons_csv):
            try:
                with transaction.atomic():
                    stats['persons_rows'] += 1
                    person = self._get_or_create_person(
                        full_name=row.get('Name'),
                        original_name=row.get('Original Name'),
                        note=row.get('Note'),
                        cache=person_cache,
                        unknown_country=unknown_country,
                    )
                    if person:
                        stats['persons_imported'] += 1
                        _, created_fav = FavoritePerson.objects.get_or_create(user=user, person=person)
                        if created_fav:
                            stats['favorites_added'] += 1
            except Exception as exc:
                _register_failure('persons', row, exc)

        # 2. Movies
        self.stdout.write("\n--- Movies ---")
        for row in self._iter_csv(movies_csv):
            try:
                with transaction.atomic():
                    stats['movies_list_rows'] += 1
                    movie, created = self._create_or_get_movie(
                        row,
                        movie_by_full_key,
                        movie_by_title_year,
                        person_cache,
                        country_cache,
                        unknown_country,
                    )
                    if movie is None:
                        stats['movies_no_title'] += 1
                        continue
                    if created:
                        stats['movies_created'] += 1
                    else:
                        stats['movies_matched'] += 1

                    # statuses / favorites
                    status_str = (row.get('Status') or '').strip()
                    if status_str in STATUS_TO_WATCH_STATUS:
                        self._set_watch_status(user, movie, STATUS_TO_WATCH_STATUS[status_str])
                        stats['statuses_set'] += 1

                    list_title_str = (row.get('ListTitle') or '').strip()
                    if list_title_str == 'Любимые фильмы':
                        self._set_favorite(user, movie)
                        stats['favorites_set'] += 1
                    elif list_title_str and list_title_str not in SYSTEM_LIST_TITLES:
                        self._add_to_custom_list(user, movie, list_title_str)
                        stats['custom_list_rows'] += 1

                    my_rating = parse_int(row.get('My rating'))
                    if my_rating:
                        watched_at = parse_date(row.get('Date'))
                        self._set_rating(user, movie, my_rating, watched_at=watched_at)
                        stats['ratings_set_list'] += 1
            except Exception as exc:
                _register_failure('movie_list', row, exc)

        if stats['movies_no_title']:
            self.stdout.write(
                self.style.WARNING(f"Skipped movies without Title and Original Title: {stats['movies_no_title']}")
            )

        # 3. Votes (ratings) — фильм может быть оценён, но не состоять ни в одном списке,
        #    поэтому создаём его из строки votes, если он не найден.
        self.stdout.write("\n--- Ratings ---")
        for row in self._iter_csv(votes_csv):
            try:
                with transaction.atomic():
                    stats['votes_rows'] += 1
                    rating_val = parse_int(row.get('My rating'))
                    if rating_val is None:
                        continue
                    movie = self._find_movie(row, movie_by_full_key, movie_by_title_year)
                    if not movie:
                        movie, created = self._create_or_get_movie(
                            row,
                            movie_by_full_key,
                            movie_by_title_year,
                            person_cache,
                            country_cache,
                            unknown_country,
                        )
                        if created:
                            stats['movies_created_from_votes'] += 1
                    if not movie:
                        stats['votes_skipped'] += 1
                        continue
                    self._set_rating(user, movie, rating_val)
                    stats['ratings_set_votes'] += 1
            except Exception as exc:
                _register_failure('votes', row, exc)

        # 4. Comments -> user_movie.note + statuses
        self.stdout.write("\n--- Comments to notes ---")
        for row in self._iter_csv(comments_csv):
            try:
                with transaction.atomic():
                    stats['comments_rows'] += 1
                    movie = self._find_movie(row, movie_by_full_key, movie_by_title_year)
                    if not movie:
                        movie, created = self._create_or_get_movie(
                            row,
                            movie_by_full_key,
                            movie_by_title_year,
                            person_cache,
                            country_cache,
                            unknown_country,
                        )
                        if created:
                            stats['movies_created_from_comments'] += 1
                    if not movie:
                        continue
                    comment_text = row.get('Comment')
                    if comment_text:
                        self._append_movie_note(user, movie, comment_text)
                        stats['comments_note_applied'] += 1
                    status_str = (row.get('Status') or '').strip()
                    if status_str in STATUS_TO_WATCH_STATUS:
                        self._set_watch_status(user, movie, STATUS_TO_WATCH_STATUS[status_str])
                        stats['comments_status_set'] += 1
            except Exception as exc:
                _register_failure('comments', row, exc)

        # 5. Notes -> user_movie.note
        self.stdout.write("\n--- Notes to user_movie.note ---")
        for row in self._iter_csv(notes_csv):
            try:
                with transaction.atomic():
                    stats['notes_rows'] += 1
                    movie = self._find_movie(row, movie_by_full_key, movie_by_title_year)
                    if not movie:
                        movie, created = self._create_or_get_movie(
                            row,
                            movie_by_full_key,
                            movie_by_title_year,
                            person_cache,
                            country_cache,
                            unknown_country,
                        )
                        if created:
                            stats['movies_created_from_notes'] += 1
                    if not movie:
                        continue
                    note_text = row.get('Note')
                    if note_text:
                        self._append_movie_note(user, movie, note_text)
                        stats['notes_note_applied'] += 1
            except Exception as exc:
                _register_failure('notes', row, exc)

        # 6. Kinozal HIDE movies (priority=SKIP) -> Vault as 'Не буду смотреть'
        self._import_hidden_movies(user)

        self.stdout.write("\n" + "=" * 52)
        self.stdout.write(self.style.SUCCESS("Import summary"))
        self.stdout.write("=" * 52)
        self.stdout.write(
            f"Persons:          rows={stats['persons_rows']:<5} imported={stats['persons_imported']:<5} "
            f"favorites={stats['favorites_added']}"
        )
        self.stdout.write(
            f"Movies (list):    rows={stats['movies_list_rows']:<5} created={stats['movies_created']:<5} "
            f"matched={stats['movies_matched']}"
        )
        self.stdout.write(
            f"  statuses={stats['statuses_set']}  favorites={stats['favorites_set']}  "
            f"custom_lists={stats['custom_list_rows']}  ratings={stats['ratings_set_list']}"
        )
        self.stdout.write(
            f"Ratings (votes):  rows={stats['votes_rows']:<5} applied={stats['ratings_set_votes']:<5} "
            f"movies_created={stats['movies_created_from_votes']}"
        )
        self.stdout.write(
            f"Comments:         rows={stats['comments_rows']:<5} notes_applied={stats['comments_note_applied']:<5} "
            f"statuses={stats['comments_status_set']}  movies_created={stats['movies_created_from_comments']}"
        )
        self.stdout.write(
            f"Notes:            rows={stats['notes_rows']:<5} applied={stats['notes_note_applied']:<5} "
            f"movies_created={stats['movies_created_from_notes']}"
        )
        if stats['votes_skipped']:
            self.stdout.write(self.style.WARNING(f"Votes skipped (no movie): {stats['votes_skipped']}"))
        if stats['movies_no_title']:
            self.stdout.write(self.style.WARNING(f"Movies skipped (no title): {stats['movies_no_title']}"))

        if failures:
            self.stdout.write("\n" + self.style.ERROR(f"FAILED rows: {len(failures)}"))
            by_source = {}
            for src, title, msg in failures:
                by_source.setdefault(src, []).append((title, msg))
            max_examples = 8
            for src, items in by_source.items():
                self.stdout.write(self.style.ERROR(f"  [{src}] {len(items)} row(s) failed:"))
                for title, msg in items[:max_examples]:
                    self.stdout.write(self.style.WARNING(f"    - {title}: {msg}"))
                if len(items) > max_examples:
                    self.stdout.write(f"    ... and {len(items) - max_examples} more (see logs/debug.log, tag [import])")

        total_movies = Movie.objects.count()
        total_user_movies = UserMovie.objects.count()
        total_user_lists = UserList.objects.count()
        total_genres = Genre.objects.count()
        total_persons = Person.objects.count()
        self.stdout.write("=" * 52)
        self.stdout.write(f"Vault after import: movies={total_movies}, user_movies={total_user_movies}, "
                          f"lists={total_user_lists}, genres={total_genres}, persons={total_persons}")
        self.stdout.write(self.style.SUCCESS("\nImport completed successfully."))
