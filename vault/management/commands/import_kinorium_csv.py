import csv
import re
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from slugify import slugify

from core.models import Country
from vault.models import (
    Comment,
    FavoritePerson,
    Genre,
    Movie,
    MovieNote,
    MoviePerson,
    Person,
    Rating,
    UserList,
    UserListMovie,
)


STATUS_TO_LIST_TYPE = {
    'Буду смотреть': 'will_watch',
    'Просмотрен': 'watched',
    'Не буду смотреть': 'wont_watch',
}

TYPE_TO_MOVIE_TYPE = {
    'Фильм': Movie.MovieType.MOVIE,
    'Сериал': Movie.MovieType.SERIES,
    'Мультфильм': Movie.MovieType.CARTOON,
    'Аниме': Movie.MovieType.ANIME,
    'ТВ шоу': Movie.MovieType.SHOW,
}


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
        title = row.get('Title') or ''
        original_title = row.get('Original Title') or ''
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

        base_slug = slugify(title) if title else None
        slug = unique_slug(base_slug) if base_slug else None

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
            'budget': parse_decimal(row.get('Budget')),
            'box_office': parse_decimal(row.get('Box world') or row.get('Box USA') or row.get('Box RU')),
            'imdb_rating': parse_decimal(row.get('IMDb rating')),
            'imdb_votes': parse_int(row.get('IMDb cnt')),
            'source': Movie.Source.KINORIUM,
        }

    @transaction.atomic
    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.SUCCESS("Starting Kinorium CSV data import..."))

        user = self._ensure_user()
        self.stdout.write(self.style.SUCCESS(f"Importing data for user '{user.username}' (id={user.id})"))
        UserList.create_system_lists(user)

        csv_dir = Path(settings.BASE_DIR) / 'vault' / 'current_csv'
        movies_csv = csv_dir / 'backup_76444_movie_list.csv'
        votes_csv = csv_dir / 'backup_76444_votes.csv'
        comments_csv = csv_dir / 'backup_76444_comments.csv'
        notes_csv = csv_dir / 'backup_76444_notes.csv'
        persons_csv = csv_dir / 'backup_76444_person_list.csv'

        person_cache = {}
        country_cache = {}
        unknown_country = self._ensure_unknown_country()
        movie_by_title_year = {}

        # 1. Favorite persons
        self.stdout.write("\n--- Persons / Favorites ---")
        for row in self._iter_csv(persons_csv):
            person = self._get_or_create_person(
                full_name=row.get('Name'),
                original_name=row.get('Original Name'),
                note=row.get('Note'),
                cache=person_cache,
                unknown_country=unknown_country,
            )
            if person:
                FavoritePerson.objects.get_or_create(user=user, person=person)

        # 2. Movies
        self.stdout.write("\n--- Movies ---")
        for row in self._iter_csv(movies_csv):
            movie_defaults = self._movie_from_row(row)
            title = movie_defaults['title']
            year = movie_defaults['year']

            movie, created = Movie.objects.get_or_create(
                title=title,
                year=year,
                defaults=movie_defaults,
            )
            if created and movie_defaults.get('slug') and not movie.slug:
                movie.slug = movie_defaults['slug']
                movie.save(update_fields=['slug'])

            movie_by_title_year[(title, year)] = movie

            # genres
            for genre_name in (row.get('Genres') or '').split(','):
                name = genre_name.strip()
                if not name:
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

            # statuses / favorites
            status_str = (row.get('Status') or '').strip()
            if status_str in STATUS_TO_LIST_TYPE:
                list_type = STATUS_TO_LIST_TYPE[status_str]
                user_list = UserList.objects.get(user=user, list_type=list_type)
                UserListMovie.objects.get_or_create(user_list=user_list, movie=movie)

            list_title_str = (row.get('ListTitle') or '').strip()
            if list_title_str == 'Любимые фильмы':
                fav_list = UserList.objects.get(user=user, list_type='favorites')
                UserListMovie.objects.get_or_create(user_list=fav_list, movie=movie)

            my_rating = parse_int(row.get('My rating'))
            if my_rating:
                Rating.objects.update_or_create(user=user, movie=movie, defaults={'rating': my_rating})

        # 3. Votes (ratings)
        self.stdout.write("\n--- Ratings ---")
        for row in self._iter_csv(votes_csv):
            rating_val = parse_int(row.get('My rating'))
            if rating_val is None:
                continue
            title = row.get('Title') or ''
            year = parse_int(row.get('Year'))
            movie = movie_by_title_year.get((title, year))
            if not movie:
                continue
            Rating.objects.update_or_create(user=user, movie=movie, defaults={'rating': rating_val})

        # 4. Comments + statuses
        self.stdout.write("\n--- Comments ---")
        for row in self._iter_csv(comments_csv):
            title = row.get('Title') or ''
            year = parse_int(row.get('Year'))
            movie = movie_by_title_year.get((title, year))
            if not movie:
                continue
            comment_text = row.get('Comment')
            if comment_text:
                Comment.objects.get_or_create(user=user, movie=movie, defaults={'text': comment_text})
            status_str = (row.get('Status') or '').strip()
            if status_str in STATUS_TO_LIST_TYPE:
                list_type = STATUS_TO_LIST_TYPE[status_str]
                user_list = UserList.objects.get(user=user, list_type=list_type)
                UserListMovie.objects.get_or_create(user_list=user_list, movie=movie)

        # 5. Notes
        self.stdout.write("\n--- Notes ---")
        for row in self._iter_csv(notes_csv):
            title = row.get('Title') or ''
            year = parse_int(row.get('Year'))
            movie = movie_by_title_year.get((title, year))
            if not movie:
                continue
            note_text = row.get('Note')
            if note_text:
                MovieNote.objects.get_or_create(user=user, movie=movie, defaults={'text': note_text})

        self.stdout.write(self.style.SUCCESS("\nImport completed successfully."))
