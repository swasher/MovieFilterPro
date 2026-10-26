import json
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase

from qbittorrent.models import Torrent
from qbittorrent.services.torrent_service import MovieTorrentsDeleteResult, TorrentDeleteResult
from vault.models import Movie, UserMovie


class MovieTorrentLinkApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='vault-qbt-user', password='secret')
        self.client.force_login(self.user)

        self.linked_movie = Movie.objects.create(title='Linked Movie', year=2024)
        UserMovie.objects.create(
            user=self.user,
            movie=self.linked_movie,
            watch_status=UserMovie.WatchStatus.PLAN,
        )
        Torrent.objects.create(
            movie=self.linked_movie,
            info_hash='a' * 40,
            name='Linked Movie 1080p',
            source_url='https://kinozal.tv/details.php?id=1001',
            content_path='/downloads/Linked Movie',
        )

        self.unlinked_movie = Movie.objects.create(title='Unlinked Movie', year=2023)
        UserMovie.objects.create(
            user=self.user,
            movie=self.unlinked_movie,
            watch_status=UserMovie.WatchStatus.PLAN,
        )

    def test_movies_include_torrent_linked_flag(self):
        response = self.client.get('/api/vault/movies?status=will_watch')

        self.assertEqual(response.status_code, 200)
        payload = {item['slug']: item for item in response.json()}
        self.assertTrue(payload[self.linked_movie.slug]['torrent_linked'])
        self.assertEqual(payload[self.linked_movie.slug]['torrent_info_hash'], 'a' * 40)
        self.assertFalse(payload[self.unlinked_movie.slug]['torrent_linked'])
        self.assertIsNone(payload[self.unlinked_movie.slug]['torrent_info_hash'])

    def test_has_torrent_filter(self):
        linked_response = self.client.get('/api/vault/movies?status=will_watch&has_torrent=true')
        unlinked_response = self.client.get('/api/vault/movies?status=will_watch&has_torrent=false')

        self.assertEqual(linked_response.status_code, 200)
        self.assertEqual(unlinked_response.status_code, 200)
        self.assertEqual([item['slug'] for item in linked_response.json()], [self.linked_movie.slug])
        self.assertEqual([item['slug'] for item in unlinked_response.json()], [self.unlinked_movie.slug])

    def test_movie_detail_includes_torrent_links(self):
        response = self.client.get(f'/api/vault/movies/{self.linked_movie.slug}')

        self.assertEqual(response.status_code, 200)
        torrents = response.json()['torrents']
        self.assertEqual(len(torrents), 1)
        self.assertEqual(torrents[0]['info_hash'], 'a' * 40)
        self.assertEqual(torrents[0]['source_url'], 'https://kinozal.tv/details.php?id=1001')
        self.assertEqual(torrents[0]['content_path'], '/downloads/Linked Movie')


class MovieWatchedCleanupApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='vault-watched-user', password='secret')
        self.client.force_login(self.user)

        self.movie = Movie.objects.create(title='Watched Movie', year=2024)
        UserMovie.objects.create(
            user=self.user,
            movie=self.movie,
            watch_status=UserMovie.WatchStatus.PLAN,
        )
        Torrent.objects.create(
            movie=self.movie,
            info_hash='a' * 40,
            name='Watched Movie 1080p',
        )

    @patch('vault.api.qbt_torrent_service.delete_movie_torrents')
    def test_toggle_watched_with_delete_flag_removes_torrents(self, delete_mock):
        delete_mock.return_value = MovieTorrentsDeleteResult(
            results=[
                TorrentDeleteResult(
                    info_hash='a' * 40,
                    name='Watched Movie 1080p',
                    qbt_deleted=True,
                    archive_deleted=True,
                    record_deleted=True,
                )
            ],
            errors=[],
        )

        response = self.client.post(
            f'/api/vault/movies/{self.movie.slug}/toggle-status',
            data=json.dumps({'status_key': 'watched', 'delete_torrents': True}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['is_active'])
        self.assertEqual(payload['torrents_deleted'], 1)
        self.assertEqual(payload['torrent_delete_errors'], [])
        delete_mock.assert_called_once_with(self.movie, delete_files=True, reason='watched')

    @patch('vault.api.qbt_torrent_service.delete_movie_torrents')
    def test_toggle_watched_without_flag_keeps_torrents(self, delete_mock):
        response = self.client.post(
            f'/api/vault/movies/{self.movie.slug}/toggle-status',
            data=json.dumps({'status_key': 'watched'}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['torrents_deleted'], 0)
        delete_mock.assert_not_called()

    @patch('vault.api.qbt_torrent_service.delete_movie_torrents')
    def test_toggle_off_watched_does_not_delete_torrents(self, delete_mock):
        UserMovie.objects.filter(user=self.user, movie=self.movie).update(
            watch_status=UserMovie.WatchStatus.WATCHED
        )

        response = self.client.post(
            f'/api/vault/movies/{self.movie.slug}/toggle-status',
            data=json.dumps({'status_key': 'watched', 'delete_torrents': True}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()['is_active'])
        delete_mock.assert_not_called()

    @patch('vault.api.qbt_torrent_service.delete_movie_torrents')
    def test_toggle_watched_returns_delete_errors(self, delete_mock):
        delete_mock.return_value = MovieTorrentsDeleteResult(
            results=[
                TorrentDeleteResult(
                    info_hash='a' * 40,
                    name='Watched Movie 1080p',
                    qbt_deleted=False,
                    archive_deleted=False,
                    record_deleted=False,
                    error='qBittorrent недоступен.',
                )
            ],
            errors=['Watched Movie 1080p: qBittorrent недоступен.'],
        )

        response = self.client.post(
            f'/api/vault/movies/{self.movie.slug}/toggle-status',
            data=json.dumps({'status_key': 'watched', 'delete_torrents': True}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['torrents_deleted'], 0)
        self.assertEqual(
            payload['torrent_delete_errors'],
            ['Watched Movie 1080p: qBittorrent недоступен.'],
        )

    @patch('vault.api.qbt_torrent_service.delete_movie_torrents')
    def test_toggle_watched_survives_delete_exception(self, delete_mock):
        delete_mock.side_effect = RuntimeError('boom')

        response = self.client.post(
            f'/api/vault/movies/{self.movie.slug}/toggle-status',
            data=json.dumps({'status_key': 'watched', 'delete_torrents': True}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['is_active'])
        self.assertEqual(payload['torrents_deleted'], 0)
        self.assertEqual(payload['torrent_delete_errors'], ['boom'])
