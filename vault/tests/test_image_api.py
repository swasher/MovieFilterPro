from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from asgiref.sync import async_to_sync
from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings

from vault.services.image_cache import CACHE_STATUS_MISSING
from vault.services.image_service import FILE_STREAM_CHUNK_SIZE, ImageService


def _read_streaming_body(response) -> bytes:
    """Дочитывает async-streaming ответ в синхронном тесте."""

    async def collect() -> bytes:
        chunks = []
        async for chunk in response:
            chunks.append(chunk)
        return b"".join(chunks)

    return async_to_sync(collect)()


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
        self.assertEqual(_read_streaming_body(response), b"image-bytes")
        self.assertEqual(response["Content-Type"], "image/jpeg")
        self.assertIn("immutable", response["Cache-Control"])
        self.assertTrue(response["ETag"])
        # Файл отдаётся async-итератором, а не целиком через FileResponse.
        self.assertTrue(response.is_async)
        self.assertEqual(response["Content-Length"], str(len(b"image-bytes")))

    def test_serves_nested_path(self):
        self._seed_cached_image("poster", "w500", "nested/poster.jpg")

        response = self.client.get("/api/vault/images/poster/w500/nested/poster.jpg")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(_read_streaming_body(response), b"image-bytes")

    def test_streams_large_file_in_chunks(self):
        payload = b"x" * (FILE_STREAM_CHUNK_SIZE * 3 + 123)
        self._seed_cached_image("poster", "w500", "big.jpg", content=payload)

        response = self.client.get("/api/vault/images/poster/w500/big.jpg")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Length"], str(len(payload)))
        self.assertEqual(_read_streaming_body(response), payload)

    @patch(
        "vault.services.image_cache.ImageCache.get_or_schedule",
        return_value=(CACHE_STATUS_MISSING, None),
    )
    def test_serves_kind_specific_placeholder_when_image_is_unavailable(self, _mock):
        response = self.client.get("/api/vault/images/profile/w500/missing.jpg")

        # Заглушка отдаётся сразу (200), без лишнего редиректа на /static.
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/svg+xml")
        self.assertEqual(response["Cache-Control"], "private, max-age=3600")
        self.assertIn(b"<svg", _read_streaming_body(response))

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
