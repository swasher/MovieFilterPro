from unittest.mock import patch

from django.core.cache import cache
from django.test import SimpleTestCase

from tmdb_adapter.client_singleton import PersonImageBasic
from vault.services.person_images_service import CACHE_KEY_PREFIX, get_person_image_paths


class PersonImagesServiceTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)

    @patch("vault.services.person_images_service.get_tmdb_client")
    @patch("vault.services.person_images_service.get_person_images")
    def test_caches_paths_and_fetches_tmdb_only_once(self, get_images, _client):
        get_images.return_value = [
            PersonImageBasic(file_path="/a.jpg"),
            PersonImageBasic(file_path="/b.jpg"),
        ]

        first = get_person_image_paths(1100)
        second = get_person_image_paths(1100)

        self.assertEqual(first, ["/a.jpg", "/b.jpg"])
        self.assertEqual(second, ["/a.jpg", "/b.jpg"])
        self.assertEqual(get_images.call_count, 1)
        self.assertEqual(cache.get(f"{CACHE_KEY_PREFIX}1100"), ["/a.jpg", "/b.jpg"])

    @patch("vault.services.person_images_service.get_tmdb_client")
    @patch("vault.services.person_images_service.get_person_images")
    def test_caches_empty_list(self, get_images, _client):
        get_images.return_value = []

        self.assertEqual(get_person_image_paths(1), [])
        self.assertEqual(get_person_image_paths(1), [])
        self.assertEqual(get_images.call_count, 1)

    @patch("vault.services.person_images_service.get_tmdb_client")
    @patch("vault.services.person_images_service.get_person_images")
    def test_failure_is_not_cached(self, get_images, _client):
        get_images.side_effect = RuntimeError("tmdb down")

        with self.assertRaises(RuntimeError):
            get_person_image_paths(1)

        self.assertIsNone(cache.get(f"{CACHE_KEY_PREFIX}1"))

    @patch("vault.services.person_images_service.get_tmdb_client")
    @patch("vault.services.person_images_service.get_person_images")
    def test_cached_list_is_returned_as_copy(self, get_images, _client):
        get_images.return_value = [PersonImageBasic(file_path="/a.jpg")]

        first = get_person_image_paths(1)
        first.append("/mutated.jpg")

        self.assertEqual(get_person_image_paths(1), ["/a.jpg"])
