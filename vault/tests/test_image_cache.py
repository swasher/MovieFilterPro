import os
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import requests
from django.test import SimpleTestCase

from vault.services.image_cache import (
    FAILED_MARKER_SUFFIX,
    MISSING_MARKER_SUFFIX,
    ImageCache,
)


class FakeResponse:
    def __init__(self, status_code=200, content=b"image-bytes", headers=None):
        self.status_code = status_code
        self.headers = headers or {"Content-Type": "image/jpeg"}
        self._content = content

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(response=self)

    def iter_content(self, chunk_size=8192):
        yield self._content

    def close(self):
        pass


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.calls = 0

    def get(self, url, **kwargs):
        self.calls += 1
        return self.response


class ImageCacheTests(SimpleTestCase):
    image_path = "/poster.jpg"
    source_url = "https://image.tmdb.org/t/p/w500/poster.jpg"

    def _marker(self, cache: ImageCache, suffix: str) -> Path:
        target = cache.cache_path(self.image_path, self.source_url)
        return target.with_name(target.name + suffix)

    def test_downloads_file_and_serves_it_from_cache(self):
        with TemporaryDirectory() as temp_dir:
            cache = ImageCache(Path(temp_dir))
            session = FakeSession(FakeResponse())

            with patch.object(cache, "_get_session", return_value=session):
                first = cache.get(self.image_path, self.source_url)
                second = cache.get(self.image_path, self.source_url)

            self.assertIsNotNone(first)
            self.assertIsNotNone(second)
            self.assertEqual(first.path.read_bytes(), b"image-bytes")
            self.assertEqual(first.content_type, "image/jpeg")
            self.assertEqual(session.calls, 1)
            self.assertEqual(list(Path(temp_dir).glob("*.tmp")), [])

    def test_404_creates_missing_marker_and_does_not_retry(self):
        with TemporaryDirectory() as temp_dir:
            cache = ImageCache(Path(temp_dir))
            session = FakeSession(FakeResponse(status_code=404))

            with patch.object(cache, "_get_session", return_value=session):
                first = cache.get(self.image_path, self.source_url)
                second = cache.get(self.image_path, self.source_url)

            self.assertIsNone(first)
            self.assertIsNone(second)
            self.assertEqual(session.calls, 1)
            self.assertTrue(self._marker(cache, MISSING_MARKER_SUFFIX).exists())
            self.assertFalse(cache.cache_path(self.image_path, self.source_url).exists())

    def test_server_error_marks_failed_and_allows_retry_after_ttl(self):
        with TemporaryDirectory() as temp_dir:
            cache = ImageCache(Path(temp_dir), failed_ttl_seconds=30)
            failed_session = FakeSession(FakeResponse(status_code=500))

            with patch.object(cache, "_get_session", return_value=failed_session):
                self.assertIsNone(cache.get(self.image_path, self.source_url))
                self.assertIsNone(cache.get(self.image_path, self.source_url))

            self.assertEqual(failed_session.calls, 1)
            failed_marker = self._marker(cache, FAILED_MARKER_SUFFIX)
            self.assertTrue(failed_marker.exists())

            old_time = time.time() - 60
            os.utime(failed_marker, (old_time, old_time))

            success_session = FakeSession(FakeResponse())
            with patch.object(cache, "_get_session", return_value=success_session):
                result = cache.get(self.image_path, self.source_url)

            self.assertIsNotNone(result)
            self.assertEqual(result.path.read_bytes(), b"image-bytes")
            self.assertEqual(success_session.calls, 1)

    def test_old_missing_marker_version_is_ignored(self):
        with TemporaryDirectory() as temp_dir:
            cache = ImageCache(Path(temp_dir))
            missing_marker = self._marker(cache, MISSING_MARKER_SUFFIX)
            missing_marker.parent.mkdir(parents=True, exist_ok=True)
            missing_marker.write_text("old-version", encoding="utf-8")

            session = FakeSession(FakeResponse())
            with patch.object(cache, "_get_session", return_value=session):
                result = cache.get(self.image_path, self.source_url)

            self.assertIsNotNone(result)
            self.assertEqual(result.path.read_bytes(), b"image-bytes")
            self.assertFalse(missing_marker.exists())

    def test_non_image_response_is_not_cached(self):
        with TemporaryDirectory() as temp_dir:
            cache = ImageCache(Path(temp_dir))
            session = FakeSession(FakeResponse(headers={"Content-Type": "text/html"}))

            with patch.object(cache, "_get_session", return_value=session):
                result = cache.get(self.image_path, self.source_url)

            self.assertIsNone(result)
            self.assertFalse(cache.cache_path(self.image_path, self.source_url).exists())
            self.assertTrue(self._marker(cache, FAILED_MARKER_SUFFIX).exists())
