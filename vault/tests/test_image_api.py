from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings

from vault.services.image_cache import CACHE_STATUS_MISSING
from vault.services.image_service import ImageService


class VaultImageEndpointTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username="image-user", password="secret")
        self.client.force_login(self.user)

        self.temp_dir = TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.settings_override = override_settings(CACHE_ROOT=Path(self.temp_dir.name))
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)

    def _seed_cached_image(self, kind: str, size: str, image_path: str, content: bytes = b"image-bytes"):
        cache = ImageService._get_cache(kind, size)
        target = cache.cache_path(image_path, ImageService.source_url(size, image_path))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        return target

    def test_serves_cached_image_with_long_lived_cache_headers(self):
        self._seed_cached_image("poster", "w500", "poster.jpg")

        response = self.client.get("/api/vault/images/poster/w500/poster.jpg")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content), b"image-bytes")
        self.assertEqual(response["Content-Type"], "image/jpeg")
        self.assertIn("immutable", response["Cache-Control"])
        self.assertTrue(response["ETag"])

    def test_serves_nested_path(self):
        self._seed_cached_image("poster", "w500", "nested/poster.jpg")

        response = self.client.get("/api/vault/images/poster/w500/nested/poster.jpg")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content), b"image-bytes")

    @patch(
        "vault.services.image_cache.ImageCache.get_or_schedule",
        return_value=(CACHE_STATUS_MISSING, None),
    )
    def test_redirects_to_kind_specific_placeholder_when_image_is_unavailable(self, _mock):
        response = self.client.get("/api/vault/images/profile/w500/missing.jpg")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/static/img/profile-placeholder.svg")
        self.assertEqual(response["Cache-Control"], "no-store")

    @patch("vault.services.image_cache.ImageCache._schedule_download")
    def test_redirects_to_tmdb_source_while_cache_is_cold(self, schedule_mock):
        response = self.client.get("/api/vault/images/poster/w500/poster.jpg")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response["Location"],
            "https://image.tmdb.org/t/p/w500/poster.jpg",
        )
        self.assertEqual(response["Cache-Control"], "no-store")
        schedule_mock.assert_called_once()

    def test_rejects_unknown_size(self):
        response = self.client.get("/api/vault/images/poster/w999/poster.jpg")

        self.assertEqual(response.status_code, 404)

    def test_rejects_unknown_kind(self):
        response = self.client.get("/api/vault/images/actor/w500/poster.jpg")

        self.assertEqual(response.status_code, 404)

    def test_rejects_path_traversal(self):
        response = self.client.get("/api/vault/images/poster/w500/..%2Fsecret.jpg")

        self.assertEqual(response.status_code, 404)

    def test_requires_authentication(self):
        self.client.logout()

        response = self.client.get("/api/vault/images/poster/w500/poster.jpg")

        self.assertEqual(response.status_code, 401)
