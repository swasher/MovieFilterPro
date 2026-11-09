from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import Client, SimpleTestCase, TestCase

from tmdb_adapter.client_singleton import PersonImageBasic, get_person_images
from vault.models import FavoritePerson, Movie, MoviePerson, Person, PersonAlias, StarPerson


class PersonAliasSearchTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.stallone = Person.objects.create(
            tmdb_id="90001",
            imdb_id="nm9000001",
            name="Сильвестр Сталлоне",
            original_name="Sylvester Stallone",
        )
        self.schwarzenegger = Person.objects.create(
            tmdb_id="90002",
            imdb_id="nm9000002",
            name="Арнольд Шварценеггер",
            original_name="Arnold Schwarzenegger",
        )
        PersonAlias.objects.create(
            person=self.stallone,
            name="Sly Stallone",
        )
        PersonAlias.objects.create(
            person=self.stallone,
            name="Sylvester Gardenzio Stallone",
        )
        PersonAlias.objects.create(
            person=self.schwarzenegger,
            name="Arnie",
        )

    def test_search_finds_person_by_alias(self):
        response = self.client.get("/api/vault/persons", {"q": "Sly"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [item["id"] for item in response.json()],
            [self.stallone.id],
        )

    def test_search_by_alias_is_case_insensitive_and_has_no_duplicates(self):
        response = self.client.get("/api/vault/persons", {"q": "gardenzio"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [item["id"] for item in response.json()],
            [self.stallone.id],
        )

    def test_search_by_name_still_works(self):
        response = self.client.get("/api/vault/persons", {"q": "Арнольд"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [item["id"] for item in response.json()],
            [self.schwarzenegger.id],
        )

    def test_person_detail_returns_aliases(self):
        response = self.client.get(f"/api/vault/persons/{self.stallone.id}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["also_known_as"],
            ["Sly Stallone", "Sylvester Gardenzio Stallone"],
        )


class PersonPopularityRankingTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.lead = Person.objects.create(
            tmdb_id="91001",
            imdb_id="nm9100001",
            name="Главная роль",
            original_name="Lead Role",
            popularity=1.0,
        )
        self.trending = Person.objects.create(
            tmdb_id="91002",
            imdb_id="nm9100002",
            name="Тренд TMDB",
            original_name="TMDB Trend",
            popularity=999.0,
        )
        self.movie_a = Movie.objects.create(title="Movie A", tmdb_vote_count=1000)
        self.movie_b = Movie.objects.create(title="Movie B", tmdb_vote_count=500)
        self.movie_c = Movie.objects.create(title="Movie C", tmdb_vote_count=10)
        MoviePerson.objects.create(movie=self.movie_a, person=self.lead, role="actor", order=0)
        MoviePerson.objects.create(movie=self.movie_b, person=self.lead, role="actor", order=4)
        # Высокая популярность TMDB, но в главных ролях только малобюджетный фильм.
        MoviePerson.objects.create(movie=self.movie_c, person=self.trending, role="actor", order=0)
        # Дальше топ-5 титров — голоса этого фильма не должны учитываться.
        MoviePerson.objects.create(movie=self.movie_a, person=self.trending, role="actor", order=5)

    def test_home_popular_group_uses_lead_role_votes(self):
        response = self.client.get("/api/vault/persons/home")

        self.assertEqual(response.status_code, 200)
        popular = next(group for group in response.json()["groups"] if group["id"] == "popular")
        self.assertEqual(popular["see_all_href"], "/persons?order=-lead_votes")
        self.assertEqual(
            [person["id"] for person in popular["persons"]],
            [self.lead.id, self.trending.id],
        )

    def test_person_list_sort_by_lead_votes(self):
        response = self.client.get("/api/vault/persons", {"order": "-lead_votes"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [person["id"] for person in response.json()],
            [self.lead.id, self.trending.id],
        )


class PersonImagesAdapterTests(SimpleTestCase):
    def test_parses_profiles_and_applies_limit(self):
        tmdb = SimpleNamespace(
            _api=SimpleNamespace(
                people_get_images=lambda person_id: {
                    "profiles": [
                        {"file_path": "/first.jpg"},
                        {"file_path": "/second.jpg"},
                        {"file_path": None},
                        "not-a-dict",
                    ]
                }
            )
        )

        images = get_person_images(tmdb, 1, limit=1)

        self.assertEqual(len(images), 1)
        self.assertEqual(images[0].file_path, "/first.jpg")


class PersonImagesApiTests(TestCase):
    def setUp(self):
        self.client = Client()
        # Кеш списка фото живёт в LocMem и не откатывается транзакцией.
        cache.clear()
        self.addCleanup(cache.clear)
        self.person = Person.objects.create(
            tmdb_id="12345",
            imdb_id="nm12345",
            name="Test Person",
            original_name="Test Person",
            photo="/profile1.jpg",
        )

    @patch("vault.services.tmdb_rate_limiter.TmdbRateLimiter.wait")
    @patch("vault.services.person_images_service.get_person_images")
    @patch("vault.services.person_images_service.get_tmdb_client")
    def test_returns_images_from_tmdb(
        self,
        get_tmdb_client_mock,
        get_person_images_mock,
        wait_mock,
    ):
        get_tmdb_client_mock.return_value = object()
        get_person_images_mock.return_value = [
            PersonImageBasic(file_path="/profile1.jpg"),
            PersonImageBasic(file_path="/profile2.jpg"),
        ]

        response = self.client.get(
            f"/api/vault/persons/{self.person.id}/images",
            {"limit": "5"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIsNone(payload["error"])
        self.assertEqual(len(payload["items"]), 1)
        self.assertEqual(payload["items"][0]["file_path"], "/profile2.jpg")
        self.assertTrue(payload["items"][0]["url"].endswith("/w500/profile2.jpg"))
        self.assertTrue(payload["items"][0]["thumb_url"].endswith("/w185/profile2.jpg"))
        self.assertNotIn("is_primary", payload["items"][0])
        # Список кешируется целиком (до 20 файлов), limit применяется на выдаче.
        self.assertEqual(get_person_images_mock.call_args.kwargs["limit"], 20)
        # Интерактивное чтение намеренно не идёт через глобальный лимитер.
        wait_mock.assert_not_called()

    def test_non_numeric_tmdb_id_returns_empty(self):
        person = Person.objects.create(
            tmdb_id="k000000001",
            imdb_id="nm00000001",
            name="CSV Person",
            original_name="CSV Person",
        )

        response = self.client.get(f"/api/vault/persons/{person.id}/images")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"items": [], "error": None})

    @patch("vault.services.person_images_service.get_person_images")
    @patch("vault.services.person_images_service.get_tmdb_client")
    def test_tmdb_error_returns_empty_with_error(
        self,
        get_tmdb_client_mock,
        get_person_images_mock,
    ):
        get_tmdb_client_mock.return_value = object()
        get_person_images_mock.side_effect = RuntimeError("tmdb down")

        response = self.client.get(
            f"/api/vault/persons/{self.person.id}/images",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["items"], [])
        self.assertTrue(payload["error"])


class PersonStarApiTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username="star-api-user", password="secret")
        self.client.force_login(self.user)
        self.person = Person.objects.create(
            tmdb_id="90100",
            imdb_id="nm9010000",
            name="Звезда Тестовая",
            original_name="Test Star",
        )

    def test_toggle_star_does_not_touch_favorite(self):
        response = self.client.post(f"/api/vault/persons/{self.person.id}/toggle-star")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["is_star"])
        self.assertTrue(StarPerson.objects.filter(user=self.user, person=self.person).exists())
        self.assertFalse(FavoritePerson.objects.filter(user=self.user, person=self.person).exists())

        response = self.client.post(f"/api/vault/persons/{self.person.id}/toggle-star")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["is_star"])
        self.assertFalse(StarPerson.objects.filter(user=self.user, person=self.person).exists())

    def test_star_filter_and_detail(self):
        StarPerson.objects.create(user=self.user, person=self.person)

        list_response = self.client.get("/api/vault/persons", {"is_star": "true"})
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual([item["id"] for item in list_response.json()], [self.person.id])
        self.assertTrue(list_response.json()[0]["is_star"])

        detail_response = self.client.get(f"/api/vault/persons/{self.person.id}")
        self.assertEqual(detail_response.status_code, 200)
        self.assertTrue(detail_response.json()["is_star"])
        self.assertFalse(detail_response.json()["is_favorite"])
