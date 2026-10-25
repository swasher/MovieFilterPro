from django.contrib.auth.models import User
from django.test import TestCase

from qbittorrent.models import Torrent
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
        self.assertFalse(payload[self.unlinked_movie.slug]['torrent_linked'])

    def test_has_torrent_filter(self):
        linked_response = self.client.get('/api/vault/movies?status=will_watch&has_torrent=true')
        unlinked_response = self.client.get('/api/vault/movies?status=will_watch&has_torrent=false')

        self.assertEqual(linked_response.status_code, 200)
        self.assertEqual(unlinked_response.status_code, 200)
        self.assertEqual([item['slug'] for item in linked_response.json()], [self.linked_movie.slug])
        self.assertEqual([item['slug'] for item in unlinked_response.json()], [self.unlinked_movie.slug])
