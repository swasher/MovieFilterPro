from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from core.models import UserPreferences
from vault.models import Movie

from plex.models import PlexLinkState, PlexLibraryItem
from plex.services.plex_link_sync_service import (
    PLEX_LINK_RETRY_SECONDS,
    PlexLinkSyncService,
)


class FakePart:
    def __init__(self, file):
        self.file = file


class FakeMedia:
    def __init__(self, file):
        self.parts = [FakePart(file)]


class FakeItem:
    def __init__(self, rating_key, title, year, guid_ids, media_type='movie', file=None):
        self.ratingKey = rating_key
        self.title = title
        self.originalTitle = None
        self.year = year
        self.guids = [SimpleNamespace(id=guid) for guid in guid_ids]
        self.media = [FakeMedia(file)] if file else []

    def __repr__(self):
        return f'<FakeItem {self.ratingKey}>'


class FakeSection:
    def __init__(self, title, section_type, items):
        self.title = title
        self.type = section_type
        self._items = items

    def all(self):
        return self._items


class FakeLibrary:
    def __init__(self, sections):
        self._sections = sections

    def sections(self):
        return self._sections


class FakeServer:
    def __init__(self, sections):
        self.library = FakeLibrary(sections)


def configure_plex():
    prefs = UserPreferences.get()
    prefs.plex_address = 'http://plex.local:32400'
    prefs.plex_token = 'token'
    prefs.save()
    return prefs


class PlexLinkSyncServiceTests(TestCase):
    def setUp(self):
        self.movie = Movie.objects.create(title='Matrix', tmdb_id=603, imdb_id='tt0133093')
        self.series = Movie.objects.create(
            title='Breaking Bad',
            movie_type=Movie.MovieType.SERIES,
            tmdb_media_type=Movie.TMDBMediaType.TV,
            tvdb_id=81189,
        )

    def _server(self):
        return FakeServer([
            FakeSection('Movies', 'movie', [
                FakeItem(101, 'Matrix', 1999, ['tmdb://603'], file='/movies/matrix.mkv'),
                FakeItem(102, 'Unknown Movie', 2021, ['tmdb://999999']),
            ]),
            FakeSection('TV Shows', 'show', [
                FakeItem(201, 'Breaking Bad', 2008, ['tvdb://81189', 'tmdb://1396']),
            ]),
            FakeSection('Music', 'artist', [
                FakeItem(301, 'Some Artist', 2000, []),
            ]),
        ])

    @patch.object(PlexLinkSyncService, '_connect')
    def test_sync_populates_cache_and_links(self, connect_mock):
        configure_plex()
        connect_mock.return_value = self._server()

        state = PlexLinkSyncService.sync()

        self.assertFalse(state.is_syncing)
        self.assertIsNotNone(state.last_synced_at)
        self.assertEqual(state.items_total, 3)  # music-секция пропущена
        self.assertEqual(state.matched_total, 2)
        self.assertEqual(state.unmatched_total, 1)

        matrix = PlexLibraryItem.objects.get(rating_key='101')
        self.assertEqual(matrix.vault_movie_id, self.movie.id)
        self.assertEqual(matrix.match_method, 'tmdb')
        self.assertEqual(matrix.file_name, 'matrix.mkv')

        series = PlexLibraryItem.objects.get(rating_key='201')
        self.assertEqual(series.vault_movie_id, self.series.id)
        self.assertEqual(series.match_method, 'tvdb')

        self.assertIsNone(PlexLibraryItem.objects.get(rating_key='102').vault_movie_id)

    @patch.object(PlexLinkSyncService, '_connect')
    def test_sync_removes_items_missing_from_plex(self, connect_mock):
        configure_plex()
        connect_mock.return_value = self._server()
        PlexLinkSyncService.sync()

        connect_mock.return_value = FakeServer([
            FakeSection('Movies', 'movie', [FakeItem(101, 'Matrix', 1999, ['tmdb://603'])]),
        ])
        PlexLinkSyncService.sync()

        self.assertEqual(
            list(PlexLibraryItem.objects.values_list('rating_key', flat=True)),
            ['101'],
        )

    def test_sync_without_preferences_clears_cache(self):
        PlexLibraryItem.objects.create(
            rating_key='old',
            media_type=PlexLibraryItem.MediaType.MOVIE,
            title='Old',
            last_seen_at=timezone.now(),
            vault_movie=self.movie,
        )
        state = PlexLinkState.get()
        state.items_total = 1
        state.save()

        result = PlexLinkSyncService.sync()

        self.assertEqual(PlexLibraryItem.objects.count(), 0)
        self.assertEqual(result.items_total, 0)
        self.assertIsNone(result.last_synced_at)
        self.assertEqual(result.last_error, '')

    @patch.object(PlexLinkSyncService, '_connect')
    def test_sync_error_keeps_previous_cache(self, connect_mock):
        configure_plex()
        connect_mock.return_value = self._server()
        PlexLinkSyncService.sync()
        items_before = PlexLibraryItem.objects.count()

        connect_mock.side_effect = RuntimeError('connection refused')
        state = PlexLinkSyncService.sync()

        self.assertEqual(PlexLibraryItem.objects.count(), items_before)
        self.assertFalse(state.is_syncing)
        self.assertIn('connection refused', state.last_error)
        self.assertIsNotNone(state.last_synced_at)

    @patch.object(PlexLinkSyncService, '_connect')
    def test_sync_skips_when_already_running(self, connect_mock):
        configure_plex()
        state = PlexLinkState.get()
        state.is_syncing = True
        state.save()

        PlexLinkSyncService.sync()

        connect_mock.assert_not_called()
        self.assertTrue(PlexLinkState.get().is_syncing)


class PlexLinkFreshnessTests(TestCase):
    @patch('plex.tasks.sync_plex_link')
    def test_ensure_fresh_enqueues_when_stale(self, task_mock):
        configure_plex()

        self.assertTrue(PlexLinkSyncService.ensure_fresh_async())
        task_mock.assert_called_once()

    @patch('plex.tasks.sync_plex_link')
    def test_ensure_fresh_skips_when_fresh(self, task_mock):
        configure_plex()
        state = PlexLinkState.get()
        state.last_synced_at = timezone.now()
        state.save()

        self.assertFalse(PlexLinkSyncService.ensure_fresh_async())
        task_mock.assert_not_called()

    @patch('plex.tasks.sync_plex_link')
    def test_ensure_fresh_respects_retry_window(self, task_mock):
        configure_plex()
        state = PlexLinkState.get()
        state.last_attempt_at = timezone.now()
        state.save()

        self.assertFalse(PlexLinkSyncService.ensure_fresh_async())
        task_mock.assert_not_called()

    @patch('plex.tasks.sync_plex_link')
    def test_ensure_fresh_allows_retry_after_window(self, task_mock):
        configure_plex()
        state = PlexLinkState.get()
        state.last_attempt_at = timezone.now() - timedelta(seconds=PLEX_LINK_RETRY_SECONDS + 5)
        state.save()

        self.assertTrue(PlexLinkSyncService.ensure_fresh_async())
        task_mock.assert_called_once()

    @patch('plex.tasks.sync_plex_link')
    def test_ensure_fresh_skips_when_not_configured(self, task_mock):
        self.assertFalse(PlexLinkSyncService.ensure_fresh_async())
        task_mock.assert_not_called()
