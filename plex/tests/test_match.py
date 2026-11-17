from types import SimpleNamespace

from django.test import TestCase

from vault.models import Movie

from plex.models import PlexLibraryItem
from plex.services.plex_link_sync_service import (
    build_match_indexes,
    match_item,
    parse_guids,
)


def _movie(**kwargs):
    defaults = {
        'title': 'Test',
        'movie_type': Movie.MovieType.MOVIE,
        'tmdb_media_type': Movie.TMDBMediaType.MOVIE,
    }
    defaults.update(kwargs)
    return Movie.objects.create(**defaults)


def _item(media_type='movie', **kwargs):
    data = {
        'media_type': media_type,
        'guid_tmdb': '',
        'guid_imdb': '',
        'guid_tvdb': '',
    }
    data.update(kwargs)
    return data


class ParseGuidsTests(TestCase):
    def test_new_agent_guids(self):
        parsed = parse_guids(['imdb://tt0111161', 'tmdb://27205', 'tvdb://73739'])
        self.assertEqual(parsed, {'imdb': 'tt0111161', 'tmdb': '27205', 'tvdb': '73739'})

    def test_legacy_agent_guids_with_lang(self):
        parsed = parse_guids([
            'com.plexapp.agents.imdb://tt0111161?lang=en',
            'com.plexapp.agents.themoviedb://27205?lang=en',
            'com.plexapp.agents.thetvdb://73739?lang=en',
        ])
        self.assertEqual(parsed, {'imdb': 'tt0111161', 'tmdb': '27205', 'tvdb': '73739'})

    def test_guid_objects_use_id_attribute(self):
        # plexapi Guid.__repr__ обрезает длинные legacy-идентификаторы — берём .id
        objects = [
            SimpleNamespace(id='com.plexapp.agents.imdb://tt0111161?lang=en'),
            SimpleNamespace(id='tmdb://27205'),
        ]
        parsed = parse_guids(objects)
        self.assertEqual(parsed, {'imdb': 'tt0111161', 'tmdb': '27205'})

    def test_ignores_internal_and_malformed(self):
        parsed = parse_guids([
            'plex://movie/5d776b7c4f5d4d0020f0d9c0',
            'garbage',
            'tmdb://not-a-number',
            None,
        ])
        self.assertEqual(parsed, {})

    def test_imdb_lowercased(self):
        parsed = parse_guids(['imdb://TT0111161'])
        self.assertEqual(parsed['imdb'], 'tt0111161')


class MatchItemTests(TestCase):
    def setUp(self):
        self.movie = _movie(title='Matrix', tmdb_id=603, imdb_id='tt0133093')
        self.series = _movie(
            title='Breaking Bad',
            movie_type=Movie.MovieType.SERIES,
            tmdb_media_type=Movie.TMDBMediaType.TV,
            tmdb_id=1396,
            tvdb_id=81189,
        )
        self.indexes = build_match_indexes([self.movie, self.series])

    def test_movie_matched_by_tmdb(self):
        movie_id, method = match_item(_item(guid_tmdb='603'), self.indexes)
        self.assertEqual((movie_id, method), (self.movie.id, 'tmdb'))

    def test_movie_matched_by_imdb(self):
        movie_id, method = match_item(_item(guid_imdb='tt0133093'), self.indexes)
        self.assertEqual((movie_id, method), (self.movie.id, 'imdb'))

    def test_series_matched_by_tvdb_first(self):
        movie_id, method = match_item(_item(media_type='show', guid_tvdb='81189', guid_tmdb='1396'), self.indexes)
        self.assertEqual((movie_id, method), (self.series.id, 'tvdb'))

    def test_series_matched_by_tmdb_without_tvdb(self):
        movie_id, method = match_item(_item(media_type='show', guid_tmdb='1396'), self.indexes)
        self.assertEqual((movie_id, method), (self.series.id, 'tmdb'))

    def test_media_type_guard(self):
        # TMDB ID сериала не должен связаться с Plex-фильмом и наоборот
        movie_id, method = match_item(_item(media_type='movie', guid_tmdb='1396'), self.indexes)
        self.assertEqual((movie_id, method), (None, ''))

        movie_id, method = match_item(_item(media_type='show', guid_tmdb='603'), self.indexes)
        self.assertEqual((movie_id, method), (None, ''))

    def test_conflicting_imdb_ids_are_not_linked(self):
        duplicate = _movie(title='Matrix Duplicate', imdb_id='tt0133093')
        indexes = build_match_indexes([self.movie, duplicate])
        movie_id, method = match_item(_item(guid_imdb='tt0133093'), indexes)
        self.assertEqual((movie_id, method), (None, ''))

    def test_unmatched_item(self):
        movie_id, method = match_item(_item(guid_tmdb='999999'), self.indexes)
        self.assertEqual((movie_id, method), (None, ''))


class PlexLinkPersistTests(TestCase):
    """Проверяем матчинг/реконсиляцию через _persist_snapshot без обращения к Plex."""

    def setUp(self):
        self.movie = _movie(title='Matrix', tmdb_id=603)
        self.series = _movie(
            title='Breaking Bad',
            movie_type=Movie.MovieType.SERIES,
            tmdb_media_type=Movie.TMDBMediaType.TV,
            tvdb_id=81189,
        )

    def _snapshot(self, *entries):
        from plex.services.plex_link_sync_service import PlexLinkSyncService
        from django.utils import timezone

        now = timezone.now()
        data = [dict(entry) for entry in entries]
        PlexLinkSyncService._persist_snapshot(data, synced_at=now)
        return now

    def _entry(self, rating_key, media_type='movie', **kwargs):
        entry = {
            'rating_key': rating_key,
            'media_type': media_type,
            'section': 'Movies' if media_type == 'movie' else 'TV Shows',
            'title': 'Title',
            'original_title': '',
            'year': 2020,
            'file_path': '',
            'file_name': '',
            'guids': [],
            'guid_tmdb': '',
            'guid_imdb': '',
            'guid_tvdb': '',
        }
        entry.update(kwargs)
        return entry

    def test_persist_links_movies_and_counts(self):
        now = self._snapshot(
            self._entry('1', guid_tmdb='603'),
            self._entry('2', media_type='show', guid_tvdb='81189'),
            self._entry('3', guid_tmdb='999'),
        )

        self.assertEqual(PlexLibraryItem.objects.count(), 3)
        self.assertEqual(PlexLibraryItem.objects.get(rating_key='1').vault_movie_id, self.movie.id)
        self.assertEqual(PlexLibraryItem.objects.get(rating_key='2').vault_movie_id, self.series.id)
        self.assertIsNone(PlexLibraryItem.objects.get(rating_key='3').vault_movie_id)
        self.assertTrue(PlexLibraryItem.objects.filter(last_seen_at=now).exists())

    def test_reconcile_deletes_missing_items(self):
        self._snapshot(
            self._entry('1', guid_tmdb='603'),
            self._entry('2', guid_tmdb='999'),
        )
        self._snapshot(self._entry('1', guid_tmdb='603'))

        self.assertEqual(
            list(PlexLibraryItem.objects.values_list('rating_key', flat=True)),
            ['1'],
        )

    def test_new_tmdb_id_relinks_on_next_sync(self):
        self.movie.delete()
        self._snapshot(self._entry('1', guid_tmdb='603'))
        self.assertIsNone(PlexLibraryItem.objects.get(rating_key='1').vault_movie_id)

        movie = _movie(title='Matrix', tmdb_id=603)
        self._snapshot(self._entry('1', guid_tmdb='603'))
        self.assertEqual(PlexLibraryItem.objects.get(rating_key='1').vault_movie_id, movie.id)
