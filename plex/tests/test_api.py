from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from core.models import UserPreferences
from vault.models import Movie

from plex.models import PlexLinkState, PlexLibraryItem


def configure_plex():
    prefs = UserPreferences.get()
    prefs.plex_address = 'http://plex.local:32400'
    prefs.plex_token = 'token'
    prefs.save()
    return prefs


class VaultPlexFlagApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='vault-plex-user', password='secret')
        self.client.force_login(self.user)

        self.linked = Movie.objects.create(title='Linked Movie', year=2024)
        self.unlinked = Movie.objects.create(title='Unlinked Movie', year=2023)
        PlexLibraryItem.objects.create(
            rating_key='10',
            media_type=PlexLibraryItem.MediaType.MOVIE,
            section='Movies',
            title='Linked Movie',
            year=2024,
            file_path='/movies/linked.mkv',
            file_name='linked.mkv',
            match_method='tmdb',
            vault_movie=self.linked,
            last_seen_at=timezone.now(),
        )

    def test_movies_include_in_plex_flag(self):
        response = self.client.get('/api/vault/movies')

        self.assertEqual(response.status_code, 200)
        payload = {item['slug']: item for item in response.json()}
        self.assertTrue(payload[self.linked.slug]['in_plex'])
        self.assertFalse(payload[self.unlinked.slug]['in_plex'])

    def test_has_plex_filter(self):
        linked_response = self.client.get('/api/vault/movies?has_plex=true')
        unlinked_response = self.client.get('/api/vault/movies?has_plex=false')

        self.assertEqual(linked_response.status_code, 200)
        self.assertEqual(unlinked_response.status_code, 200)
        self.assertEqual([item['slug'] for item in linked_response.json()], [self.linked.slug])
        self.assertEqual([item['slug'] for item in unlinked_response.json()], [self.unlinked.slug])

    def test_movie_detail_includes_plex_block(self):
        response = self.client.get(f'/api/vault/movies/{self.linked.slug}')

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['in_plex'])
        self.assertEqual(payload['plex']['section'], 'Movies')
        self.assertEqual(payload['plex']['file_name'], 'linked.mkv')
        self.assertEqual(payload['plex']['match_method'], 'tmdb')

    def test_movie_detail_without_plex_link(self):
        response = self.client.get(f'/api/vault/movies/{self.unlinked.slug}')

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload['in_plex'])
        self.assertIsNone(payload['plex'])


class PlexLinkApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='plex-link-user', password='secret')

    def test_status_requires_auth(self):
        response = self.client.get('/api/plex/link/status')
        self.assertEqual(response.status_code, 401)

    def test_status_reports_not_configured(self):
        self.client.force_login(self.user)

        state = PlexLinkState.get()
        state.items_total = 5
        state.matched_total = 3
        state.unmatched_total = 2
        state.save()

        response = self.client.get('/api/plex/link/status')

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload['configured'])
        self.assertEqual(payload['items_total'], 5)
        self.assertEqual(payload['matched_total'], 3)
        self.assertEqual(payload['unmatched_total'], 2)

    def test_sync_rejects_when_not_configured(self):
        self.client.force_login(self.user)

        response = self.client.post('/api/plex/link/sync')

        self.assertEqual(response.status_code, 400)

    @patch('plex.tasks.sync_plex_link')
    def test_sync_enqueues_when_configured(self, task_mock):
        self.client.force_login(self.user)
        configure_plex()

        response = self.client.post('/api/plex/link/sync')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'accepted': True, 'already_running': False})
        task_mock.assert_called_once()

    @patch('plex.tasks.sync_plex_link')
    def test_sync_reports_already_running(self, task_mock):
        self.client.force_login(self.user)
        configure_plex()
        state = PlexLinkState.get()
        state.is_syncing = True
        state.save()

        response = self.client.post('/api/plex/link/sync')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'accepted': False, 'already_running': True})
        task_mock.assert_not_called()


class FakePlexMovie:
    def __init__(self, rating_key, title, year, guids, file=None):
        self.ratingKey = rating_key
        self.title = title
        self.originalTitle = None
        self.year = year
        self.guids = [SimpleNamespace(id=guid) for guid in guids]
        self.media = [SimpleNamespace(parts=[SimpleNamespace(file=file)])] if file else []


class FakePlexSection:
    def __init__(self, movies):
        self._movies = movies

    def search(self):
        return self._movies


class FakePlexServer:
    def __init__(self, section):
        self.library = SimpleNamespace(section=lambda name: section)


class PlexSectionMoviesApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='plex-movies-user', password='secret')
        self.client.force_login(self.user)

        self.movie = Movie.objects.create(title='Matrix', tmdb_id=603)
        PlexLibraryItem.objects.create(
            rating_key='101',
            media_type=PlexLibraryItem.MediaType.MOVIE,
            section='Movies',
            title='Matrix',
            year=1999,
            match_method='tmdb',
            vault_movie=self.movie,
            last_seen_at=timezone.now(),
        )

    @patch('plex.api._get_plex_server')
    def test_section_movies_include_vault_link(self, server_mock):
        section = FakePlexSection([
            FakePlexMovie(101, 'Matrix', 1999, ['tmdb://603'], file='/movies/matrix.mkv'),
            FakePlexMovie(102, 'Unknown', 2021, ['tmdb://999999']),
        ])
        server_mock.return_value = FakePlexServer(section)

        response = self.client.get('/api/plex/sections/Movies/movies')

        self.assertEqual(response.status_code, 200)
        payload = {item['title']: item for item in response.json()}
        self.assertEqual(payload['Matrix']['vault_movie_id'], self.movie.id)
        self.assertEqual(payload['Matrix']['vault_movie_slug'], self.movie.slug)
        self.assertEqual(payload['Matrix']['match_method'], 'tmdb')
        self.assertIsNone(payload['Unknown']['vault_movie_id'])
