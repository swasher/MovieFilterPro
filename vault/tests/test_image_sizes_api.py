"""URL изображений в API выбирают размер под контекст.

Карточки списков должны просить уменьшенные файлы (w342/w185), а не те же
w500, что и страницы-детали: каждый размер — отдельный файл дискового кеша,
поэтому лишний размер означает лишнюю загрузку и лишние байты.
"""

from django.test import Client, TestCase

from vault.models import Movie, MoviePerson, Person
from vault.services.image_service import ImageService


class MovieImageSizeTests(TestCase):
    def setUp(self):
        self.client = Client()
        ImageService.invalidate_cache_settings()
        self.addCleanup(ImageService.invalidate_cache_settings)

        self.movie = Movie.objects.create(
            title="Size Test Movie",
            poster="/poster.jpg",
            backdrop_path="/backdrop.jpg",
        )
        self.actor = Person.objects.create(
            tmdb_id="91001",
            imdb_id="nm9100101",
            name="Тестовый Актёр",
            original_name="Test Actor",
            photo="/actor.jpg",
        )
        MoviePerson.objects.create(
            movie=self.movie,
            person=self.actor,
            role="actor",
            order=0,
        )

    def test_movie_list_uses_card_poster_size(self):
        response = self.client.get("/api/vault/movies")

        self.assertEqual(response.status_code, 200)
        items = response.json()
        self.assertEqual(len(items), 1)
        self.assertEqual(
            items[0]["poster_url"],
            "/api/vault/images/poster/w342/poster.jpg",
        )

    def test_movie_detail_uses_detail_sizes(self):
        response = self.client.get(f"/api/vault/movies/{self.movie.slug}")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(
            payload["poster_url"],
            "/api/vault/images/poster/w500/poster.jpg",
        )
        self.assertEqual(
            payload["poster_full_url"],
            "/api/vault/images/poster/original/poster.jpg",
        )
        self.assertEqual(
            payload["backdrop_url"],
            "/api/vault/images/backdrop/w1280/backdrop.jpg",
        )
        self.assertEqual(
            payload["actors"][0]["photo_url"],
            "/api/vault/images/profile/w185/actor.jpg",
        )

    def test_person_list_uses_card_photo_size(self):
        response = self.client.get("/api/vault/persons")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload), 1)
        self.assertEqual(
            payload[0]["photo_url"],
            "/api/vault/images/profile/w185/actor.jpg",
        )

    def test_person_detail_keeps_detail_photo_size(self):
        response = self.client.get(f"/api/vault/persons/{self.actor.id}")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(
            payload["photo_url"],
            "/api/vault/images/profile/w500/actor.jpg",
        )
        self.assertEqual(
            payload["photo_full_url"],
            "/api/vault/images/profile/original/actor.jpg",
        )
