from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase

from core.models import Country
from vault.models import FavoritePerson, Genre, Movie, MoviePerson, Person, UserMovie
from vault.services.tmdb_movie_matching_service import TMDBCandidate
from vault.services.tmdb_movie_sync_service import TMDBMovieSyncService


class _FakeTMDBClient:
    def __init__(self, movie_details=None, person_details=None):
        self._movie_details = movie_details or {}
        self._person_details = person_details or {}

    def movie(self, movie_id):
        return self._movie_details[movie_id]

    def tv_show(self, tv_id):
        raise KeyError(tv_id)

    def person(self, person_id):
        if person_id not in self._person_details:
            raise KeyError(person_id)
        return self._person_details[person_id]


def _candidate(tmdb_id=321):
    return TMDBCandidate(
        tmdb_id=tmdb_id,
        media_type="movie",
        title="",
        original_title="",
        year=None,
        score=0,
        score_reasons=("test",),
        poster_path=None,
        popularity=None,
        vote_average=None,
    )


def _movie_details_with_people():
    return SimpleNamespace(
        id=321,
        title="Интерстеллар",
        original_title="Interstellar",
        overview="Space travel",
        imdb_id="tt0816692",
        homepage="https://www.interstellar-movie.com",
        release_date=date(2014, 11, 7),
        runtime=169,
        poster_path="/poster.jpg",
        budget=165000000,
        revenue=701729206,
        status="Released",
        videos=[SimpleNamespace(site="YouTube", key="abc123", type="Trailer", official=True)],
        genres=[SimpleNamespace(name="Фантастика"), SimpleNamespace(name="Драма")],
        countries=[
            SimpleNamespace(iso_3166_1="US", name="United States"),
            SimpleNamespace(iso_3166_1="GB", name="United Kingdom"),
        ],
        origin_countries=[],
        cast=[
            SimpleNamespace(
                person_id=1001,
                name="Мэттью МакКонахи",
                original_name="Matthew McConaughey",
                profile_path="/actor1.jpg",
                gender=2,
                character="Cooper",
                order=0,
            )
        ],
        crew=[
            SimpleNamespace(
                person_id=1002,
                name="Кристофер Нолан",
                original_name="Christopher Nolan",
                profile_path="/dir1.jpg",
                gender=2,
                job="Director",
                order=0,
            )
        ],
    )


def _movie_details_without_people():
    return SimpleNamespace(
        id=321,
        title="Интерстеллар",
        original_title="Interstellar",
        overview="Space travel",
        release_date=date(2014, 11, 7),
        runtime=169,
        poster_path="/poster.jpg",
        budget=165000000,
        revenue=701729206,
        status="Released",
        videos=[],
        genres=[SimpleNamespace(name="Фантастика")],
        countries=[SimpleNamespace(iso_3166_1="US", name="United States")],
        origin_countries=[],
        cast=[],
        crew=[],
    )


def _person_details():
    return {
        1001: SimpleNamespace(
            id=1001,
            imdb_id="nm0000190",
            name="Matthew McConaughey",
            profile_path="/actor1.jpg",
            gender=2,
            birthday=date(1969, 11, 4),
            deathday=None,
            biography="Actor",
        ),
        1002: SimpleNamespace(
            id=1002,
            imdb_id="nm0634240",
            name="Christopher Nolan",
            profile_path="/dir1.jpg",
            gender=2,
            birthday=date(1970, 7, 30),
            deathday=None,
            biography="Director",
        ),
    }


class TMDBMovieSyncServiceTests(TestCase):
    @patch("vault.services.tmdb_movie_sync_service.get_tmdb_client")
    def test_sync_updates_movie_genres_countries_people_and_photo(self, get_tmdb_client_mock):
        fake_tmdb = _FakeTMDBClient(
            movie_details={321: _movie_details_with_people()},
            person_details=_person_details(),
        )
        get_tmdb_client_mock.return_value = fake_tmdb

        movie = Movie.objects.create(
            title="Old title",
            original_title="Old original",
            year=2000,
            movie_type=Movie.MovieType.MOVIE,
            status=Movie.Status.RELEASED,
        )
        old_genre = Genre.objects.create(name="Старый жанр")
        old_country = Country.objects.create(name="Old Country", code="OC")
        movie.genres.add(old_genre)
        movie.countries.add(old_country)

        result = TMDBMovieSyncService.sync_movie(
            movie=movie,
            force_rematch=True,
            selected_candidate=_candidate(321),
        )

        movie.refresh_from_db()
        self.assertEqual(result.status, "ok")
        self.assertEqual(movie.source, Movie.Source.TMDB)
        self.assertEqual(movie.tmdb_id, 321)
        self.assertEqual(movie.tmdb_media_type, "movie")
        self.assertEqual(movie.title, "Интерстеллар")
        self.assertEqual(movie.original_title, "Interstellar")
        self.assertEqual(movie.poster, "/poster.jpg")
        self.assertEqual(movie.trailer_url, "https://www.youtube.com/watch?v=abc123")
        self.assertEqual(movie.imdb_id, "tt0816692")
        self.assertEqual(movie.homepage, "https://www.interstellar-movie.com")
        self.assertIsNone(movie.tvdb_id)

        genre_names = set(movie.genres.values_list("name", flat=True))
        self.assertEqual(genre_names, {"Фантастика", "Драма"})

        country_codes = set(movie.countries.values_list("code", flat=True))
        self.assertEqual(country_codes, {"US", "GB"})

        self.assertEqual(movie.movie_persons.filter(role="actor").count(), 1)
        self.assertEqual(movie.movie_persons.filter(role="director").count(), 1)

        actor = Person.objects.get(tmdb_id="1001")
        self.assertEqual(actor.photo, "/actor1.jpg")

    @patch("vault.services.tmdb_movie_sync_service.get_tmdb_client")
    def test_sync_does_not_change_usermovie_state(self, get_tmdb_client_mock):
        fake_tmdb = _FakeTMDBClient(
            movie_details={321: _movie_details_with_people()},
            person_details=_person_details(),
        )
        get_tmdb_client_mock.return_value = fake_tmdb

        user = User.objects.create_user(username="u1", password="x")
        movie = Movie.objects.create(
            title="Old title",
            original_title="Old original",
            year=2000,
            movie_type=Movie.MovieType.MOVIE,
            status=Movie.Status.RELEASED,
        )
        user_movie = UserMovie.objects.create(
            user=user,
            movie=movie,
            watch_status=UserMovie.WatchStatus.PLAN,
            is_favorite=True,
            rating=8,
            note="my note",
        )

        TMDBMovieSyncService.sync_movie(
            movie=movie,
            force_rematch=True,
            selected_candidate=_candidate(321),
        )

        user_movie.refresh_from_db()
        self.assertEqual(user_movie.watch_status, UserMovie.WatchStatus.PLAN)
        self.assertTrue(user_movie.is_favorite)
        self.assertEqual(user_movie.rating, 8)
        self.assertEqual(user_movie.note, "my note")

    @patch("vault.services.tmdb_movie_sync_service.get_tmdb_client")
    def test_orphan_cleanup_deletes_only_safe_orphans(self, get_tmdb_client_mock):
        fake_tmdb = _FakeTMDBClient(
            movie_details={321: _movie_details_without_people()},
            person_details={},
        )
        get_tmdb_client_mock.return_value = fake_tmdb

        unknown_country = Country.objects.create(name="Unknown", code="XX")
        orphan = Person.objects.create(
            tmdb_id="9001",
            imdb_id="im9000001",
            name="Orphan Person",
            original_name="Orphan Person",
            country=unknown_country,
        )
        favorite_orphan = Person.objects.create(
            tmdb_id="9002",
            imdb_id="im9000002",
            name="Favorite Orphan",
            original_name="Favorite Orphan",
            country=unknown_country,
        )
        linked = Person.objects.create(
            tmdb_id="9003",
            imdb_id="im9000003",
            name="Linked Person",
            original_name="Linked Person",
            country=unknown_country,
        )

        user = User.objects.create_user(username="fav_user", password="x")
        FavoritePerson.objects.create(user=user, person=favorite_orphan)

        linked_movie = Movie.objects.create(
            title="Another",
            original_title="Another",
            year=2005,
            movie_type=Movie.MovieType.MOVIE,
            status=Movie.Status.RELEASED,
        )
        MoviePerson.objects.create(movie=linked_movie, person=linked, role="actor", order=0)

        movie = Movie.objects.create(
            title="Target",
            original_title="Target",
            year=2000,
            movie_type=Movie.MovieType.MOVIE,
            status=Movie.Status.RELEASED,
        )

        result = TMDBMovieSyncService.sync_movie(
            movie=movie,
            force_rematch=True,
            selected_candidate=_candidate(321),
        )

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.orphan_persons_deleted, 1)
        self.assertFalse(Person.objects.filter(pk=orphan.pk).exists())
        self.assertTrue(Person.objects.filter(pk=favorite_orphan.pk).exists())
        self.assertTrue(Person.objects.filter(pk=linked.pk).exists())
