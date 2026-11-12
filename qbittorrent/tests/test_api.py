import json
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from qbittorrent.models import Torrent
from qbittorrent.services.errors import QbtError
from qbittorrent.services.torrent_service import (
    MovieTorrentsDeleteResult,
    QbtProgressRow,
    QbtTorrentRow,
    QbtStatus,
    TorrentAddResult,
    TorrentDeleteResult,
)
from vault.models import Movie


class QbittorrentApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='qbt-api-user', password='secret')
        self.client.force_login(self.user)

    @patch('qbittorrent.api.torrent_service.get_status')
    def test_status_returns_configuration_state(self, get_status_mock):
        get_status_mock.return_value = QbtStatus(configured=False, connected=False)

        response = self.client.get('/api/qbittorrent/status')

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()['configured'])
        self.assertFalse(response.json()['connected'])

    @patch('qbittorrent.api.torrent_service.list_torrents')
    def test_torrents_returns_items(self, list_torrents_mock):
        movie = SimpleNamespace(id=1, title='Test Movie', slug='test-movie')
        list_torrents_mock.return_value = (
            [
                QbtTorrentRow(
                    info_hash='a' * 40,
                    name='Test Movie',
                    state='downloading',
                    progress=0.5,
                    size=100,
                    total_size=100,
                    dlspeed=10,
                    upspeed=0,
                    eta=10,
                    category='',
                    tags=['mfp'],
                    save_path='/downloads',
                    content_path='/downloads/Test Movie',
                    added_on=1,
                    completion_on=None,
                    torrent=None,
                    linked_movie=movie,
                )
            ],
            1,
        )

        response = self.client.get('/api/qbittorrent/torrents')

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['total'], 1)
        self.assertEqual(payload['items'][0]['info_hash'], 'a' * 40)
        self.assertEqual(payload['items'][0]['linked_movie']['slug'], 'test-movie')

    @patch('qbittorrent.api.torrent_service.get_progress')
    def test_progress_returns_items(self, get_progress_mock):
        get_progress_mock.return_value = (
            True,
            [
                QbtProgressRow(
                    info_hash='a' * 40,
                    state='downloading',
                    progress=0.42,
                    dlspeed=10,
                    upspeed=1,
                    eta=30,
                    size=100,
                )
            ],
        )

        response = self.client.post(
            '/api/qbittorrent/progress',
            data=json.dumps({'hashes': ['a' * 40]}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['available'])
        self.assertEqual(payload['items'][0]['progress'], 0.42)

    @patch('qbittorrent.api.torrent_service.attach_torrent_to_movie')
    def test_link_torrent_to_movie(self, attach_mock):
        movie = Movie.objects.create(title='Test Movie', year=2024)
        attach_mock.return_value = (SimpleNamespace(info_hash='a' * 40), 'archive warning')

        response = self.client.post(
            f'/api/qbittorrent/torrents/{"a" * 40}/link',
            data={'movie_id': movie.id},
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['movie']['slug'], movie.slug)
        self.assertEqual(payload['warning'], 'archive warning')
        attach_mock.assert_called_once_with('a' * 40, movie)

    def test_link_torrent_movie_not_found(self):
        response = self.client.post(
            f'/api/qbittorrent/torrents/{"a" * 40}/link',
            data={'movie_id': 999999},
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 404)

    @patch('qbittorrent.api.torrent_service.delete_torrent')
    def test_delete_torrent_removes_record(self, delete_mock):
        movie = Movie.objects.create(title='Test Movie', year=2024)
        torrent = Torrent.objects.create(
            movie=movie,
            info_hash='a' * 40,
            name='Test Movie',
        )
        delete_mock.return_value = TorrentDeleteResult(
            info_hash='a' * 40,
            name='Test Movie',
            qbt_deleted=True,
            archive_deleted=True,
            record_deleted=True,
        )

        response = self.client.post(
            f'/api/qbittorrent/torrents/{"a" * 40}/delete',
            data=json.dumps({'delete_files': True}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['record_deleted'])
        self.assertTrue(payload['qbt_deleted'])
        delete_mock.assert_called_once_with(torrent, delete_files=True, reason='manual')

    def test_delete_torrent_not_found(self):
        response = self.client.post(
            f'/api/qbittorrent/torrents/{"a" * 40}/delete',
            data=json.dumps({'delete_files': True}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 404)

    @patch('qbittorrent.api.torrent_service.delete_movie_torrents')
    def test_delete_movie_torrents_returns_summary(self, delete_mock):
        movie = Movie.objects.create(title='Test Movie', year=2024)
        delete_mock.return_value = MovieTorrentsDeleteResult(
            results=[
                TorrentDeleteResult(
                    info_hash='a' * 40,
                    name='First',
                    qbt_deleted=True,
                    archive_deleted=True,
                    record_deleted=True,
                ),
                TorrentDeleteResult(
                    info_hash='b' * 40,
                    name='Second',
                    qbt_deleted=False,
                    archive_deleted=False,
                    record_deleted=False,
                    error='qBittorrent недоступен.',
                ),
            ],
            errors=['Second: qBittorrent недоступен.'],
        )

        response = self.client.post(
            f'/api/qbittorrent/movies/{movie.id}/torrents/delete',
            data=json.dumps({'delete_files': True}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['deleted_count'], 1)
        self.assertEqual(payload['errors'], ['Second: qBittorrent недоступен.'])
        self.assertEqual(len(payload['deleted']), 2)
        delete_mock.assert_called_once_with(movie, delete_files=True, reason='manual')

    def test_delete_movie_torrents_movie_not_found(self):
        response = self.client.post(
            '/api/qbittorrent/movies/999999/torrents/delete',
            data=json.dumps({'delete_files': True}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 404)

    @patch('qbittorrent.api.torrent_service.add_torrent_from_file')
    def test_upload_torrent_adds_and_links_movie(self, add_mock):
        movie = Movie.objects.create(title='Test Movie', year=2024)
        add_mock.return_value = TorrentAddResult(
            torrent=SimpleNamespace(info_hash='a' * 40, name='Test Movie'),
            created=True,
            archive_saved=True,
        )
        upload = SimpleUploadedFile('movie.torrent', b'd4:info0:e')

        response = self.client.post(
            f'/api/qbittorrent/movies/{movie.id}/torrents/upload',
            data={'file': upload},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['info_hash'], 'a' * 40)
        self.assertEqual(payload['name'], 'Test Movie')
        self.assertEqual(payload['movie']['slug'], movie.slug)

        add_mock.assert_called_once()
        kwargs = add_mock.call_args.kwargs
        self.assertEqual(kwargs['movie'], movie)
        self.assertEqual(kwargs['tag'], f'mfp:{movie.id}')
        self.assertEqual(kwargs['torrent_bytes'], b'd4:info0:e')

    def test_upload_torrent_movie_not_found(self):
        response = self.client.post(
            '/api/qbittorrent/movies/999999/torrents/upload',
            data={'file': SimpleUploadedFile('movie.torrent', b'd4:info0:e')},
        )

        self.assertEqual(response.status_code, 404)

    def test_upload_torrent_rejects_empty_file(self):
        movie = Movie.objects.create(title='Test Movie', year=2024)

        response = self.client.post(
            f'/api/qbittorrent/movies/{movie.id}/torrents/upload',
            data={'file': SimpleUploadedFile('movie.torrent', b'')},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['detail']['code'], 'qbt_torrent_empty')

    @patch('qbittorrent.api.MAX_TORRENT_UPLOAD_BYTES', 4)
    def test_upload_torrent_rejects_too_large_file(self):
        movie = Movie.objects.create(title='Test Movie', year=2024)

        response = self.client.post(
            f'/api/qbittorrent/movies/{movie.id}/torrents/upload',
            data={'file': SimpleUploadedFile('movie.torrent', b'1234567890')},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['detail']['code'], 'qbt_torrent_too_large')

    @patch('qbittorrent.api.torrent_service.add_torrent_from_file')
    def test_upload_torrent_returns_qbt_error(self, add_mock):
        movie = Movie.objects.create(title='Test Movie', year=2024)
        add_mock.side_effect = QbtError(
            'qbt_torrent_already_linked',
            'Раздача уже привязана к другому фильму Vault.',
            status_code=409,
        )

        response = self.client.post(
            f'/api/qbittorrent/movies/{movie.id}/torrents/upload',
            data={'file': SimpleUploadedFile('movie.torrent', b'd4:info0:e')},
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()['detail']['code'], 'qbt_torrent_already_linked')

    def test_requires_authentication(self):
        self.client.logout()

        response = self.client.get('/api/qbittorrent/status')

        self.assertEqual(response.status_code, 401)
