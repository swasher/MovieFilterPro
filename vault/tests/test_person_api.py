from django.test import Client, TestCase

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
