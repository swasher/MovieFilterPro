from datetime import date
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from tmdb_adapter.client_singleton import PersonBasic
from vault.models import Person, PersonAlias


def _person_basic():
    return PersonBasic(
        id=12345,
        name="Test Person",
        imdb_id="nm12345",
        birthday=date(1970, 1, 2),
        deathday=None,
        place_of_birth="Test City, Test Country",
        known_for_department="Acting",
        also_known_as=["Alias One", "Alias Two"],
        profile_path="/profile.jpg",
        gender=3,
        biography="Test biography",
        popularity=1.5,
    )


class BackfillPersonDetailsTests(TestCase):
    def setUp(self):
        self.person = Person.objects.create(
            tmdb_id="12345",
            imdb_id="nm12345",
            name="Test Person",
            original_name="Test Person",
        )

    @patch("vault.management.commands.backfill_person_details.TmdbRateLimiter.wait")
    @patch("vault.management.commands.backfill_person_details.get_person_basic")
    @patch("vault.management.commands.backfill_person_details.get_tmdb_client")
    def test_backfill_updates_missing_fields_and_aliases(
        self,
        get_tmdb_client_mock,
        get_person_basic_mock,
        wait_mock,
    ):
        get_tmdb_client_mock.return_value = object()
        get_person_basic_mock.return_value = _person_basic()
        PersonAlias.objects.create(
            person=self.person,
            name="Manual Alias",
            source="manual",
        )

        call_command(
            "backfill_person_details",
            limit=10,
            stdout=StringIO(),
        )

        self.person.refresh_from_db()
        self.assertEqual(self.person.place_of_birth, "Test City, Test Country")
        self.assertEqual(self.person.known_for_department, "Acting")
        self.assertEqual(self.person.gender, "N")
        self.assertEqual(self.person.birth_date, date(1970, 1, 2))
        self.assertEqual(self.person.biography, "Test biography")
        self.assertEqual(self.person.photo, "/profile.jpg")
        self.assertEqual(self.person.popularity, 1.5)
        self.assertIsNotNone(self.person.person_details_synced_at)
        self.assertEqual(
            set(self.person.aliases.values_list("name", flat=True)),
            {"Alias One", "Alias Two", "Manual Alias"},
        )
        wait_mock.assert_called_once()

    @patch("vault.management.commands.backfill_person_details.TmdbRateLimiter.wait")
    @patch("vault.management.commands.backfill_person_details.get_person_basic")
    @patch("vault.management.commands.backfill_person_details.get_tmdb_client")
    def test_dry_run_does_not_save(
        self,
        get_tmdb_client_mock,
        get_person_basic_mock,
        wait_mock,
    ):
        get_tmdb_client_mock.return_value = object()
        get_person_basic_mock.return_value = _person_basic()

        call_command(
            "backfill_person_details",
            limit=10,
            dry_run=True,
            stdout=StringIO(),
        )

        self.person.refresh_from_db()
        self.assertEqual(self.person.place_of_birth, "")
        self.assertEqual(self.person.known_for_department, "")
        self.assertEqual(self.person.gender, "")
        self.assertIsNone(self.person.person_details_synced_at)
        self.assertFalse(self.person.aliases.exists())

    @patch("vault.management.commands.backfill_person_details.get_tmdb_client")
    def test_non_numeric_tmdb_id_is_skipped(self, get_tmdb_client_mock):
        get_tmdb_client_mock.return_value = object()
        person = Person.objects.create(
            tmdb_id="k000000001",
            imdb_id="nm00000001",
            name="CSV Person",
            original_name="CSV Person",
        )

        call_command(
            "backfill_person_details",
            person_id=person.id,
            stdout=StringIO(),
        )

        person.refresh_from_db()
        self.assertIsNone(person.person_details_synced_at)

    @patch("vault.management.commands.backfill_person_details.TmdbRateLimiter.wait")
    @patch("vault.management.commands.backfill_person_details.get_person_basic")
    @patch("vault.management.commands.backfill_person_details.get_tmdb_client")
    def test_successful_backfill_is_not_reprocessed(
        self,
        get_tmdb_client_mock,
        get_person_basic_mock,
        wait_mock,
    ):
        get_tmdb_client_mock.return_value = object()
        get_person_basic_mock.return_value = _person_basic()

        call_command("backfill_person_details", limit=10, stdout=StringIO())
        call_command("backfill_person_details", limit=10, stdout=StringIO())

        self.assertEqual(get_person_basic_mock.call_count, 1)
