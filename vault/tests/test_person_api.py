from types import SimpleNamespace
from unittest.mock import patch

from django.test import Client, SimpleTestCase, TestCase

from tmdb_adapter.client_singleton import PersonImageBasic, get_person_images
from vault.models import Person, PersonAlias


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
            source="tmdb",
        )
        PersonAlias.objects.create(
            person=self.stallone,
            name="Sylvester Gardenzio Stallone",
            source="tmdb",
        )
        PersonAlias.objects.create(
            person=self.schwarzenegger,
            name="Arnie",
            source="tmdb",
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


class PersonImagesAdapterTests(SimpleTestCase):
    def test_parses_profiles_and_applies_limit(self):
        tmdb = SimpleNamespace(
            _api=SimpleNamespace(
                people_get_images=lambda person_id: {
                    "profiles": [
                        {
                            "file_path": "/first.jpg",
                            "width": "100",
                            "height": "150",
                            "aspect_ratio": 0.667,
                            "vote_average": 5.5,
                            "vote_count": "2",
                            "iso_639_1": None,
                        },
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
        self.assertEqual(images[0].width, 100)
        self.assertEqual(images[0].height, 150)
        self.assertEqual(images[0].vote_count, 2)
        self.assertEqual(images[0].iso_639_1, "")


class PersonImagesApiTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.person = Person.objects.create(
            tmdb_id="12345",
            imdb_id="nm12345",
            name="Test Person",
            original_name="Test Person",
            photo="/profile1.jpg",
        )

    @patch("vault.services.tmdb_rate_limiter.TmdbRateLimiter.wait")
    @patch("tmdb_adapter.client_singleton.get_person_images")
    @patch("tmdb_adapter.client_singleton.get_tmdb_client")
    def test_returns_images_from_tmdb(
        self,
        get_tmdb_client_mock,
        get_person_images_mock,
        wait_mock,
    ):
        get_tmdb_client_mock.return_value = object()
        get_person_images_mock.return_value = [
            PersonImageBasic(
                file_path="/profile1.jpg",
                width=1000,
                height=1500,
                aspect_ratio=0.667,
                vote_average=5.5,
                vote_count=3,
                iso_639_1="",
            ),
            PersonImageBasic(
                file_path="/profile2.jpg",
                width=800,
                height=1200,
                aspect_ratio=0.667,
                vote_average=4.5,
                vote_count=2,
                iso_639_1="",
            ),
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
        self.assertEqual(get_person_images_mock.call_args.kwargs["limit"], 6)
        wait_mock.assert_called_once()

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

    @patch("vault.services.tmdb_rate_limiter.TmdbRateLimiter.wait")
    @patch("tmdb_adapter.client_singleton.get_person_images")
    @patch("tmdb_adapter.client_singleton.get_tmdb_client")
    def test_tmdb_error_returns_empty_with_error(
        self,
        get_tmdb_client_mock,
        get_person_images_mock,
        wait_mock,
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
        wait_mock.assert_called_once()
