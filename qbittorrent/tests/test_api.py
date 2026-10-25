from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase

from qbittorrent.services.torrent_service import QbtTorrentRow, QbtStatus


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

    def test_requires_authentication(self):
        self.client.logout()

        response = self.client.get('/api/qbittorrent/status')

        self.assertEqual(response.status_code, 401)
