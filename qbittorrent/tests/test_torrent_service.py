import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import bencodepy
import qbittorrentapi
from django.contrib.auth.models import User
from django.test import TestCase

from moviefilter.models import UserPreferences
from qbittorrent.models import Torrent
from qbittorrent.services import torrent_service
from qbittorrent.services.errors import QbtError
from vault.models import Movie


def _torrent_bytes(name=b'Test Movie') -> bytes:
    info = {
        b'name': name,
        b'length': 1,
        b'piece length': 1,
        b'pieces': b'0' * 20,
    }
    return bencodepy.encode({b'info': info, b'comment': b'https://kinozal.tv/details.php?id=1'})


def _info_hash(name=b'Test Movie') -> str:
    info = {
        b'name': name,
        b'length': 1,
        b'piece length': 1,
        b'pieces': b'0' * 20,
    }
    return hashlib.sha1(bencodepy.encode(info)).hexdigest()


class FakeTorrentInfo:
    def __init__(self, info_hash: str):
        self.hash = info_hash
        self.name = 'Test Movie'
        self.save_path = '/downloads'
        self.content_path = '/downloads/Test Movie'


class FakeClient:
    def __init__(
        self,
        *,
        info_hash: str,
        add_response: dict | None = None,
        info_items: list | None = None,
        add_error: Exception | None = None,
    ):
        self.info_hash = info_hash
        self.add_response = add_response
        self.info_items = info_items
        self.add_error = add_error
        self.add_kwargs = None
        self.export_called = False

    def torrents_add(self, **kwargs):
        self.add_kwargs = kwargs
        if self.add_error is not None:
            raise self.add_error
        return self.add_response

    def torrents_info(self, torrent_hashes=None, **kwargs):
        if self.info_items is None:
            return []
        if torrent_hashes is None:
            return self.info_items
        if torrent_hashes in (self.info_hash, _info_hash()):
            return self.info_items
        return []

    def torrents_export(self, torrent_hash=None, **kwargs):
        self.export_called = True
        return b'd4:info0:e'

    def torrents_count(self):
        return 1

    def app_version(self):
        return '5.1.4'

    def app_web_api_version(self):
        return '2.11.3'


class TorrentServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='qbt-user', password='secret')
        self.temp_dir = TemporaryDirectory()
        self.preferences = UserPreferences.objects.create(
            user=self.user,
            qbt_url='http://qbittorrent:8080',
            qbt_username='admin',
            qbt_password='qbt-pass',
            torrents_backup_folder=self.temp_dir.name,
            kinozal_domain='kinozal.tv',
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    @patch('qbittorrent.services.torrent_service.build_client')
    def test_validate_ready_checks_backup_folder_and_client(self, build_client_mock):
        build_client_mock.return_value = FakeClient(info_hash=_info_hash())

        torrent_service.validate_ready()

        build_client_mock.assert_called_once()

    def test_validate_ready_requires_backup_folder(self):
        self.preferences.torrents_backup_folder = ''
        self.preferences.save()

        with self.assertRaises(QbtError) as context:
            torrent_service.validate_ready()

        self.assertEqual(context.exception.code, 'qbt_backup_folder_not_configured')

    @patch('qbittorrent.services.torrent_service.build_client')
    def test_add_torrent_creates_row_and_archive(self, build_client_mock):
        info_hash = _info_hash()
        client = FakeClient(
            info_hash=info_hash,
            add_response={'added_torrent_ids': [info_hash], 'success_count': 1},
            info_items=[FakeTorrentInfo(info_hash)],
        )
        build_client_mock.return_value = client

        result = torrent_service.add_torrent_from_kinozal(
            torrent_bytes=_torrent_bytes(),
            torrent_id=1001,
            source_url='https://kinozal.tv/details.php?id=1001',
        )

        self.assertTrue(result.created)
        self.assertTrue(result.archive_saved)
        torrent = Torrent.objects.get(info_hash=info_hash)
        self.assertEqual(torrent.name, 'Test Movie')
        self.assertEqual(torrent.source_url, 'https://kinozal.tv/details.php?id=1001')
        self.assertEqual(torrent.torrent_file, f'{info_hash}.torrent')
        self.assertTrue((Path(self.temp_dir.name) / f'{info_hash}.torrent').exists())
        self.assertEqual(client.add_kwargs['tags'], 'mfp')
        self.assertTrue(client.add_kwargs['is_sequential_download'])
        self.assertEqual(client.add_kwargs['torrent_files'], _torrent_bytes())

    @patch('qbittorrent.services.torrent_service.build_client')
    def test_add_torrent_requires_qbt_configuration(self, build_client_mock):
        self.preferences.qbt_url = ''
        self.preferences.save()

        with self.assertRaises(QbtError) as context:
            torrent_service.add_torrent_from_kinozal(
                torrent_bytes=_torrent_bytes(),
                torrent_id=1001,
            )

        self.assertEqual(context.exception.code, 'qbt_not_configured')
        build_client_mock.assert_not_called()

    @patch.object(torrent_service, 'ADD_VERIFY_DELAY_SECONDS', 0)
    @patch('qbittorrent.services.torrent_service.build_client')
    def test_add_torrent_raises_when_qbt_does_not_confirm(self, build_client_mock):
        info_hash = _info_hash()
        client = FakeClient(info_hash=info_hash, add_response=None, info_items=None)
        build_client_mock.return_value = client

        with self.assertRaises(QbtError) as context:
            torrent_service.add_torrent_from_kinozal(
                torrent_bytes=_torrent_bytes(),
                torrent_id=1001,
            )

        self.assertEqual(context.exception.code, 'qbt_add_not_confirmed')
        self.assertFalse(Torrent.objects.exists())

    @patch('qbittorrent.services.torrent_service.build_client')
    def test_add_torrent_reuses_existing_row(self, build_client_mock):
        info_hash = _info_hash()
        existing = Torrent.objects.create(info_hash=info_hash, name='Old name')
        client = FakeClient(
            info_hash=info_hash,
            add_response={'added_torrent_ids': [info_hash], 'success_count': 1},
            info_items=[FakeTorrentInfo(info_hash)],
        )
        build_client_mock.return_value = client

        result = torrent_service.add_torrent_from_kinozal(
            torrent_bytes=_torrent_bytes(),
            torrent_id=1001,
        )

        self.assertFalse(result.created)
        existing.refresh_from_db()
        self.assertEqual(existing.name, 'Test Movie')

    @patch('qbittorrent.services.torrent_service.build_client')
    def test_add_torrent_handles_qbt_conflict(self, build_client_mock):
        info_hash = _info_hash()
        client = FakeClient(
            info_hash=info_hash,
            add_error=qbittorrentapi.Conflict409Error(),
            info_items=[FakeTorrentInfo(info_hash)],
        )
        build_client_mock.return_value = client

        result = torrent_service.add_torrent_from_kinozal(
            torrent_bytes=_torrent_bytes(),
            torrent_id=1001,
        )

        self.assertTrue(result.created)
        self.assertTrue(Torrent.objects.filter(info_hash=info_hash).exists())

    @patch('qbittorrent.services.torrent_service.build_client')
    def test_list_torrents_merges_vault_movie(self, build_client_mock):
        info_hash = _info_hash()
        movie = Movie.objects.create(title='Test Movie', year=2024)
        Torrent.objects.create(movie=movie, info_hash=info_hash, name='Test Movie')
        client = FakeClient(
            info_hash=info_hash,
            info_items=[FakeTorrentInfo(info_hash)],
        )
        build_client_mock.return_value = client

        rows, total = torrent_service.list_torrents()

        self.assertEqual(total, 1)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].linked_movie, movie)

    def test_link_torrent_to_movie(self):
        info_hash = _info_hash()
        torrent = Torrent.objects.create(info_hash=info_hash, name='Test Movie')
        movie = Movie.objects.create(title='Test Movie', year=2024)

        linked = torrent_service.link_torrent_to_movie(torrent.id, movie)

        self.assertTrue(linked)
        torrent.refresh_from_db()
        self.assertEqual(torrent.movie, movie)

    @patch('qbittorrent.services.torrent_service.build_client')
    def test_test_connection_returns_version(self, build_client_mock):
        client = FakeClient(info_hash=_info_hash())
        build_client_mock.return_value = client

        status = torrent_service.test_connection()

        self.assertTrue(status.connected)
        self.assertEqual(status.version, '5.1.4')
        self.assertEqual(status.torrent_count, 1)
