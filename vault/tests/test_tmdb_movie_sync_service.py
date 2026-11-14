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
        self.language = "RU"
        self._api = SimpleNamespace(people_get_details=self._people_get_details)

    def movie(self, movie_id):
        return self._movie_details[movie_id]

    def tv_show(self, tv_id):
        raise KeyError(tv_id)

    def _people_get_details(self, person_id, language=None):
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
        1001: {
            "id": 1001,
            "imdb_id": "nm0000190",
            "name": "Matthew McConaughey",
            "profile_path": "/actor1.jpg",
            "gender": 2,
            "birthday": "1969-11-04",
            "deathday": None,
            "place_of_birth": "Houston, Texas, USA",
            "known_for_department": "Acting",
            "also_known_as": [
                "Matty McConaughey",
                "matty mcconaughey",
                "Matthew McConaughey",
                "",
            ],
            "biography": "Actor",
            "popularity": 1.0,
        },
        1002: {
            "id": 1002,
            "imdb_id": "nm0634240",
            "name": "Christopher Nolan",
            "profile_path": "/dir1.jpg",
            "gender": 2,
            "birthday": "1970-07-30",
            "deathday": None,
            "place_of_birth": "London, England, UK",
            "known_for_department": "Directing",
            "also_known_as": [],
            "biography": "Director",
            "popularity": 1.0,
        },
    }


class TMDBMovieSyncServiceTests(TestCase):
    @patch("vault.services.tmdb_rate_limiter.TmdbRateLimiter.wait")
    @patch("vault.services.tmdb_movie_sync_service.get_english_title", return_value="Interstellar")
    def test_resolve_title_en_fetches_english_for_english_original(self, get_english_title_mock, _wait_mock):
        movie = Movie(tmdb_id=321)
        details = SimpleNamespace(
            title="Интерстеллар",
            original_title="Interstellar",
            original_language="en",
        )

        self.assertEqual(
            TMDBMovieSyncService._resolve_title_en(movie, details, "movie"),
            "Interstellar",
        )
        get_english_title_mock.assert_called_once_with(321, "movie")

    @patch("vault.services.tmdb_rate_limiter.TmdbRateLimiter.wait")
    @patch("vault.services.tmdb_movie_sync_service.get_english_title", return_value="Mongrel")
    def test_resolve_title_en_fetches_english_for_non_english(self, get_english_title_mock, _wait_mock):
        movie = Movie(tmdb_id=123)
        details = SimpleNamespace(
            title="Дворняга",
            original_title="白衣蒼狗",
            original_language="zh",
        )

        self.assertEqual(
            TMDBMovieSyncService._resolve_title_en(movie, details, "movie"),
            "Mongrel",
        )
        get_english_title_mock.assert_called_once_with(123, "movie")

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
        self.assertEqual(actor.birth_date, date(1969, 11, 4))
        self.assertEqual(actor.place_of_birth, "Houston, Texas, USA")
        self.assertEqual(actor.known_for_department, "Acting")
        self.assertIsNotNone(actor.person_details_synced_at)
        self.assertEqual(
            set(actor.aliases.values_list("name", flat=True)),
            {"Matty McConaughey"},
        )

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

        orphan = Person.objects.create(
            tmdb_id="9001",
            imdb_id="im9000001",
            name="Orphan Person",
            original_name="Orphan Person",
        )
        favorite_orphan = Person.objects.create(
            tmdb_id="9002",
            imdb_id="im9000002",
            name="Favorite Orphan",
            original_name="Favorite Orphan",
        )
        linked = Person.objects.create(
            tmdb_id="9003",
            imdb_id="im9000003",
            name="Linked Person",
            original_name="Linked Person",
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

    @patch("vault.services.tmdb_movie_sync_service.get_tmdb_client")
    def test_sync_reuses_favorited_person_matched_by_name(self, get_tmdb_client_mock):
        """Fetch не должен плодить дубли персон: избранный актёр из CSV-импорта
        (синтетические tmdb_id/imdb_id) должен переиспользоваться по имени."""
        fake_tmdb = _FakeTMDBClient(
            movie_details={321: _movie_details_with_people()},
            person_details=_person_details(),
        )
        get_tmdb_client_mock.return_value = fake_tmdb

        old_person = Person.objects.create(
            tmdb_id="k000000001",
            imdb_id="im00000001",
            name="Мэттью МакКонахи",
            original_name="Мэттью МакКонахи",
        )
        movie = Movie.objects.create(
            title="Интерстеллар",
            original_title="Interstellar",
            year=2014,
            movie_type=Movie.MovieType.MOVIE,
            status=Movie.Status.RELEASED,
        )
        MoviePerson.objects.create(movie=movie, person=old_person, role="actor", order=0)

        user = User.objects.create_user(username="fav_actor_user", password="x")
        FavoritePerson.objects.create(user=user, person=old_person)

        result = TMDBMovieSyncService.sync_movie(
            movie=movie,
            force_rematch=True,
            selected_candidate=_candidate(321),
        )

        self.assertEqual(result.status, "ok")
        old_person.refresh_from_db()
        self.assertEqual(old_person.tmdb_id, "1001")
        self.assertEqual(old_person.imdb_id, "nm0000190")
        self.assertTrue(
            FavoritePerson.objects.filter(user=user, person=old_person).exists()
        )
        linked = movie.movie_persons.filter(role="actor").first()
        self.assertIsNotNone(linked)
        self.assertEqual(linked.person_id, old_person.pk)

    def test_map_person_gender_supports_all_tmdb_values(self):
        self.assertEqual(TMDBMovieSyncService._map_person_gender(0), "")
        self.assertEqual(TMDBMovieSyncService._map_person_gender(1), "F")
        self.assertEqual(TMDBMovieSyncService._map_person_gender(2), "M")
        self.assertEqual(TMDBMovieSyncService._map_person_gender(3), "N")
        self.assertEqual(TMDBMovieSyncService._map_person_gender(None), "")

    def test_match_source_label_maps_score_reasons(self):
        def label(reasons):
            candidate = TMDBCandidate(
                tmdb_id=1,
                media_type="movie",
                title="",
                original_title="",
                year=None,
                score=90,
                score_reasons=reasons,
                poster_path=None,
                popularity=None,
                vote_average=None,
            )
            return TMDBMovieSyncService._match_source_label(candidate)

        self.assertEqual(label(("plot_literal_match",)), "дословное совпадение описаний")
        self.assertEqual(label(("smart_search_plot_match",)), "умный поиск: совпадение сюжетов")
        self.assertEqual(label(("groq_plot_match",)), "совпадение сюжетов через GROQ")
        self.assertEqual(
            label(("ai_plot_match", "ai_plot_verified")), "подтверждено локальным AI"
        )
        self.assertEqual(label(("manual_choice",)), "ручной выбор")
        self.assertEqual(label(("stored_tmdb_id",)), "сохраненная привязка")
        self.assertEqual(label(("imdb_id_lookup",)), "поиск по IMDb ID")
        self.assertEqual(
            label(("title_exact", "year_exact", "media_type_match")),
            "уверенное совпадение названия",
        )
        self.assertEqual(label(("test",)), "")
        self.assertEqual(label(()), "")
        self.assertEqual(TMDBMovieSyncService._match_source_label(None), "")


class TVCastOrderingTests(TestCase):
    """TMDB order у сериалов бесполезен: порядок каста считаем по числу серий."""

    @staticmethod
    def _credit(person_id, name, order, popularity, character):
        return SimpleNamespace(
            person_id=person_id,
            name=name,
            original_name=name,
            profile_path=None,
            gender=2,
            character=character,
            order=order,
            popularity=popularity,
        )

    @staticmethod
    def _aggregate(person_id, episode_count):
        return SimpleNamespace(person_id=person_id, episode_count=episode_count)

    @staticmethod
    def _movie(movie_type=Movie.MovieType.MINISERIES, media_type="tv"):
        return Movie.objects.create(
            title="Убийство на краю света",
            original_title="A Murder at the End of the World",
            year=2023,
            movie_type=movie_type,
            tmdb_media_type=media_type,
        )

    def _sync_persons(self, movie, cast, aggregate_cast):
        details = SimpleNamespace(
            cast=cast,
            crew=[],
            created_by=[],
            aggregate_cast=aggregate_cast,
        )
        fake_tmdb = _FakeTMDBClient(movie_details={}, person_details={})
        TMDBMovieSyncService._sync_movie_persons(movie=movie, details=details, tmdb=fake_tmdb)
        return list(
            movie.movie_persons.filter(role="actor").order_by("order", "id")
        )

    def test_series_lead_with_bad_tmdb_order_goes_first(self):
        """Главный актёр приходит из TMDB с order=12 и не должен быть последним."""
        movie = self._movie()
        rows = self._sync_persons(
            movie,
            cast=[
                self._credit(1, "Эмма Коррин", 0, 1.9, "Darby Hart"),
                self._credit(2, "Брит Марлинг", 1, 1.3, "Lee Andersen"),
                self._credit(3, "Клайв Оуэн", 12, 4.3, "Andy Ronson"),
            ],
            aggregate_cast=[
                self._aggregate(1, 7),
                self._aggregate(2, 7),
                self._aggregate(3, 7),
            ],
        )

        self.assertEqual(
            [row.person.name for row in rows],
            ["Клайв Оуэн", "Эмма Коррин", "Брит Марлинг"],
        )
        self.assertEqual([row.order for row in rows], [0, 1, 2])

    def test_series_actor_with_more_episodes_ranks_above_popular_guest(self):
        movie = self._movie()
        rows = self._sync_persons(
            movie,
            cast=[
                self._credit(1, "Звездный гость", 0, 9.0, "Guest"),
                self._credit(2, "Главный актёр", 5, 1.0, "Lead"),
            ],
            aggregate_cast=[
                self._aggregate(1, 1),
                self._aggregate(2, 7),
            ],
        )

        self.assertEqual([row.person.name for row in rows], ["Главный актёр", "Звездный гость"])

    def test_series_without_aggregate_credits_falls_back_to_popularity(self):
        movie = self._movie()
        rows = self._sync_persons(
            movie,
            cast=[
                self._credit(1, "Первый по TMDB", 0, 1.0, "A"),
                self._credit(2, "Популярный", 5, 5.0, "B"),
            ],
            aggregate_cast=[],
        )

        self.assertEqual([row.person.name for row in rows], ["Популярный", "Первый по TMDB"])

    def test_movies_still_use_tmdb_order(self):
        movie = self._movie(movie_type=Movie.MovieType.MOVIE, media_type="movie")
        rows = self._sync_persons(
            movie,
            cast=[
                self._credit(1, "Первый по TMDB", 0, 1.0, "A"),
                self._credit(2, "Популярный", 1, 5.0, "B"),
            ],
            aggregate_cast=[self._aggregate(2, 1)],
        )

        self.assertEqual([row.person.name for row in rows], ["Первый по TMDB", "Популярный"])
