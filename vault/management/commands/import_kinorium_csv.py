

import os
import pandas as pd
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.contrib.auth.models import User
from vault.models import (
    Person, FavoritePerson, Movie, Genre, Country, Rating,
    UserList, UserListMovie, Comment, MovieNote, MoviePerson
)
from django.conf import settings
import re

# A mapping from Kinorium status names to our system list types
STATUS_TO_LIST_TYPE = {
    'Буду смотреть': 'will_watch',
    'Просмотрен': 'watched',
    'Не буду смотреть': 'wont_watch',
}

def parse_actors(actors_str):
    """Parses a string of actors like 'Actor1, Actor2, Actor3'."""
    if not isinstance(actors_str, str):
        return []
    return [{'name': name.strip()} for name in actors_str.split(', ')]

class Command(BaseCommand):
    help = 'Imports movie data from Kinorium CSV files into the vault models.'

    def _get_dataframe(self, file_path):
        """Reads a tab-separated UTF-16 CSV file into a DataFrame."""
        if not os.path.exists(file_path):
            self.stdout.write(self.style.WARNING(f"{os.path.basename(file_path)} not found, skipping."))
            return None
        try:
            return pd.read_csv(file_path, sep='\t', encoding='utf-16')
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Could not read {os.path.basename(file_path)}: {e}"))
            return None

    @transaction.atomic
    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.SUCCESS("Starting Kinorium CSV data import..."))

        try:
            user = User.objects.get(id=1)
            self.stdout.write(self.style.SUCCESS(f"Data will be imported for user: {user.username}"))
        except User.DoesNotExist:
            raise CommandError("User with id=1 does not exist. Please create a user first.")

        UserList.create_system_lists(user)
        self.stdout.write(self.style.SUCCESS("Verified system lists for the user."))

        # --- Caches ---
        person_cache = {}
        genre_cache = {}
        country_cache = {c.name: c.id for c in Country.objects.all()}
        movie_id_cache = {}  # {backup_id: movie_instance}
        movie_title_year_cache = {}  # {(title, year): movie_instance}

        # --- File Paths ---
        csv_dir = os.path.join(settings.BASE_DIR, 'current_csv')
        person_list_file = os.path.join(csv_dir, 'backup_76444_person_list.csv')
        movie_list_file = os.path.join(csv_dir, 'backup_76444_movie_list.csv')
        votes_file = os.path.join(csv_dir, 'backup_76444_votes.csv')
        comments_file = os.path.join(csv_dir, 'backup_76444_comments.csv')
        notes_file = os.path.join(csv_dir, 'backup_76444_notes.csv')

        # 1. --- Import Favorite Persons ---
        self.stdout.write("\n--- Processing Favorite Persons (person_list.csv)... ---")
        df_persons = self._get_dataframe(person_list_file)
        if df_persons is not None:
            for _, row in df_persons.iterrows():
                person_name = row['Name'] if pd.notna(row['Name']) else row.get('Original Name')
                if not person_name:
                    continue

                if person_name not in person_cache:
                    first_name, last_name = (person_name.split(' ', 1) + [''])[:2]
                    person, created = Person.objects.get_or_create(
                        first_name=first_name.strip(), last_name=last_name.strip(),
                        defaults={'biography': row.get('Note', '')}
                    )
                    person_cache[person_name] = person
                    if created: self.stdout.write(f"  Created Person: {person}")
                
                FavoritePerson.objects.get_or_create(user=user, person=person_cache[person_name])
                self.stdout.write(f"    Added {person_name} to favorites.")

        # 2. --- Import Movies and related data ---
        self.stdout.write("\n--- Processing Movies (movie_list.csv)... ---")
        df_movies = self._get_dataframe(movie_list_file)
        if df_movies is None:
            raise CommandError("movie_list.csv is essential and could not be read.")

        for _, row in df_movies.iterrows():
            backup_id = row['backup_id']
            title = row['Title']

            # Обработка года и диапазона (например, "2022-2024")
            raw_year = str(row['Year']).strip() if pd.notna(row['Year']) else ''
            year = None
            year_end = None

            if '-' in raw_year:
                try:
                    start_part, end_part = raw_year.split('-')
                    year = int(start_part.strip())
                    if end_part.strip().isdigit():
                        year_end = int(end_part.strip())
                except ValueError:
                    pass
            elif raw_year:
                try:
                    year = int(float(raw_year))
                except ValueError:
                    pass

            if pd.isna(title):
                continue
            
            movie, created = Movie.objects.get_or_create(
                title=title,
                year=year,
                defaults={
                    'original_title': row.get('Original Title', ''),
                    'description': row.get('Note', ''),
                    'duration': int(row['Runtime']) if pd.notna(row['Runtime']) else None,
                    'year_end': year_end,
                }
            )
            if created:
                self.stdout.write(f"Created Movie: {movie.title} ({movie.year})")
            
            movie_id_cache[backup_id] = movie
            if (title, year) not in movie_title_year_cache:
                movie_title_year_cache[(title, year)] = movie

            if not created:
                continue

            for genre_name in str(row.get('Genres', '')).split(', '):
                if genre_name:
                    genre, _ = Genre.objects.get_or_create(name=genre_name.strip())
                    movie.genres.add(genre)

            for country_name in str(row.get('Countries', '')).split(', '):
                country_name = country_name.strip()
                if country_name:
                    if country_name in country_cache:
                        movie.countries.add(country_cache[country_name])
                    else:
                        self.stdout.write(self.style.WARNING(f"Страна '{country_name}' не найдена в БД (фильм: {title})"))
            
            for director_name in str(row.get('Directors', '')).split(', '):
                if director_name:
                    first, last = (director_name.strip().split(' ', 1) + [''])[:2]
                    person, _ = Person.objects.get_or_create(first_name=first, last_name=last)
                    MoviePerson.objects.get_or_create(movie=movie, person=person, role='director')

            for i, actor_info in enumerate(parse_actors(row.get('Actors'))):
                actor_name = actor_info['name']
                if actor_name:
                    first, last = (actor_name.strip().split(' ', 1) + [''])[:2]
                    person, _ = Person.objects.get_or_create(first_name=first, last_name=last)
                    MoviePerson.objects.get_or_create(movie=movie, person=person, role='actor', defaults={'order': i})

            status_str = row.get('Status')
            if pd.notna(status_str) and status_str in STATUS_TO_LIST_TYPE:
                list_type = STATUS_TO_LIST_TYPE[status_str]
                user_list = UserList.objects.get(user=user, list_type=list_type)
                UserListMovie.objects.get_or_create(user_list=user_list, movie=movie)

            list_title_str = row.get('ListTitle')
            if pd.notna(list_title_str) and list_title_str == 'Любимые фильмы':
                user_list = UserList.objects.get(user=user, list_type='favorites')
                UserListMovie.objects.get_or_create(user_list=user_list, movie=movie)

        # 3. --- Import Ratings (votes.csv) ---
        self.stdout.write("\n--- Processing Ratings (votes.csv)... ---")
        df_votes = self._get_dataframe(votes_file)
        if df_votes is not None:
            for _, row in df_votes.iterrows():
                backup_id = row.get('backup_id')
                rating_val = row.get('My rating')
                if backup_id in movie_id_cache and pd.notna(rating_val):
                    movie = movie_id_cache[backup_id]
                    Rating.objects.update_or_create(
                        user=user, movie=movie, defaults={'rating': int(rating_val)}
                    )
                    self.stdout.write(f"  Added rating '{rating_val}/10' for: {movie.title}")

        # 4. --- Import Comments & Statuses (comments.csv) ---
        self.stdout.write("\n--- Processing Comments (comments.csv)... ---")
        df_comments = self._get_dataframe(comments_file)
        if df_comments is not None:
            for _, row in df_comments.iterrows():
                title = row.get('Title')
                raw_year = str(row['Year']).strip() if pd.notna(row['Year']) else ''
                year = None
                year_end = None

                if '-' in raw_year:
                    try:
                        start_part, end_part = raw_year.split('-')
                        year = int(start_part.strip())
                        if end_part.strip().isdigit():
                            year_end = int(end_part.strip())
                    except ValueError:
                        pass
                elif raw_year:
                    try:
                        year = int(float(raw_year))
                    except ValueError:
                        pass

                movie = movie_title_year_cache.get((title, year))
                if not movie:
                    continue

                if year_end and not movie.year_end:
                    movie.year_end = year_end
                    movie.save()

                if 'Comment' in row and pd.notna(row['Comment']):
                    Comment.objects.get_or_create(user=user, movie=movie, text=row['Comment'])
                    self.stdout.write(f"  Added comment for: {movie.title}")

                if 'Status' in row and pd.notna(row['Status']) and row['Status'] in STATUS_TO_LIST_TYPE:
                    list_type = STATUS_TO_LIST_TYPE[row['Status']]
                    user_list = UserList.objects.get(user=user, list_type=list_type)
                    UserListMovie.objects.get_or_create(user_list=user_list, movie=movie)
                    self.stdout.write(f"  Set status '{user_list.name}' for: {movie.title}")

        # 5. --- Import Movie Notes (notes.csv) ---
        self.stdout.write("\n--- Processing Movie Notes (notes.csv)... ---")
        df_notes = self._get_dataframe(notes_file)
        if df_notes is not None:
            for _, row in df_notes.iterrows():
                title = row.get('Title')

                raw_year = str(row['Year']).strip() if pd.notna(row['Year']) else ''
                year = None
                year_end = None

                if '-' in raw_year:
                    try:
                        start_part, end_part = raw_year.split('-')
                        year = int(start_part.strip())
                        if end_part.strip().isdigit():
                            year_end = int(end_part.strip())
                    except ValueError:
                        pass
                elif raw_year:
                    try:
                        year = int(float(raw_year))
                    except ValueError:
                        pass

                movie = movie_title_year_cache.get((title, year))
                if not movie:
                    continue

                if year_end and not movie.year_end:
                    movie.year_end = year_end
                    movie.save()

                if 'Note' in row and pd.notna(row['Note']):
                    MovieNote.objects.get_or_create(user=user, movie=movie, defaults={'text': row['Note']})
                    self.stdout.write(f"  Added note for: {movie.title}")

        self.stdout.write(self.style.SUCCESS("\nImport completed successfully!"))
