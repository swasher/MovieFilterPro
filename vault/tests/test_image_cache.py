import os
import threading
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import requests
from django.test import SimpleTestCase

from vault.services.image_cache import (
    CACHE_STATUS_MISSING,
    CACHE_STATUS_PENDING,
    CACHE_STATUS_READY,
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


class BlockingFakeSession(FakeSession):
    """Сессия, которая «зависает» в get(), пока тест не отпустит её."""

    def __init__(self, response):
        super().__init__(response)
        self.started = threading.Event()
        self.release = threading.Event()

    def get(self, url, **kwargs):
        self.calls += 1
        self.started.set()
        self.release.wait(timeout=5)
        return self.response


class ImageCacheTests(SimpleTestCase):
    image_path = "/poster.jpg"
    source_url = "https://image.tmdb.org/t/p/w500/poster.jpg"

    def _marker(self, cache: ImageCache, suffix: str) -> Path:
        target = cache.cache_path(self.image_path, self.source_url)
        return target.with_name(target.name + suffix)

    @staticmethod
    def _wait_for(predicate, timeout: float = 5.0) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return True
            time.sleep(0.01)
        return predicate()

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

    def test_get_or_schedule_returns_cached_file_without_download(self):
        with TemporaryDirectory() as temp_dir:
            cache = ImageCache(Path(temp_dir))
            target = cache.cache_path(self.image_path, self.source_url)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"image-bytes")
            session = FakeSession(FakeResponse())

            with patch.object(cache, "_get_session", return_value=session):
                status, cached = cache.get_or_schedule(self.image_path, self.source_url)

            self.assertEqual(status, CACHE_STATUS_READY)
            self.assertIsNotNone(cached)
            self.assertEqual(cached.path.read_bytes(), b"image-bytes")
            self.assertEqual(session.calls, 0)

    def test_get_or_schedule_returns_pending_and_downloads_in_background(self):
        with TemporaryDirectory() as temp_dir:
            cache = ImageCache(Path(temp_dir))
            session = FakeSession(FakeResponse())
            target = cache.cache_path(self.image_path, self.source_url)

            with patch.object(cache, "_get_session", return_value=session):
                status, cached = cache.get_or_schedule(self.image_path, self.source_url)

                self.assertEqual(status, CACHE_STATUS_PENDING)
                self.assertIsNone(cached)
                self.assertTrue(self._wait_for(target.exists))

                status, cached = cache.get_or_schedule(self.image_path, self.source_url)

            self.assertEqual(status, CACHE_STATUS_READY)
            self.assertEqual(cached.path.read_bytes(), b"image-bytes")
            self.assertEqual(session.calls, 1)

    def test_get_or_schedule_caches_404_from_background_download(self):
        with TemporaryDirectory() as temp_dir:
            cache = ImageCache(Path(temp_dir))
            session = FakeSession(FakeResponse(status_code=404))
            missing_marker = self._marker(cache, MISSING_MARKER_SUFFIX)

            with patch.object(cache, "_get_session", return_value=session):
                status, _ = cache.get_or_schedule(self.image_path, self.source_url)
                self.assertEqual(status, CACHE_STATUS_PENDING)
                self.assertTrue(self._wait_for(missing_marker.exists))

                status, cached = cache.get_or_schedule(self.image_path, self.source_url)

            self.assertEqual(status, CACHE_STATUS_MISSING)
            self.assertIsNone(cached)
            self.assertEqual(session.calls, 1)

    def test_get_or_schedule_does_not_retry_while_failed_marker_is_active(self):
        with TemporaryDirectory() as temp_dir:
            cache = ImageCache(Path(temp_dir), failed_ttl_seconds=30)
            failed_marker = self._marker(cache, FAILED_MARKER_SUFFIX)
            failed_marker.parent.mkdir(parents=True, exist_ok=True)
            failed_marker.touch()
            session = FakeSession(FakeResponse())

            with patch.object(cache, "_get_session", return_value=session):
                status, cached = cache.get_or_schedule(self.image_path, self.source_url)

            self.assertEqual(status, CACHE_STATUS_PENDING)
            self.assertIsNone(cached)
            self.assertEqual(session.calls, 0)

    def test_caches_share_one_session_per_thread(self):
        with TemporaryDirectory() as temp_dir:
            first = ImageCache(Path(temp_dir) / "first")
            second = ImageCache(Path(temp_dir) / "second")

            self.assertIs(first._get_session(), second._get_session())

    def test_get_or_schedule_deduplicates_in_flight_downloads(self):
        with TemporaryDirectory() as temp_dir:
            cache = ImageCache(Path(temp_dir))
            session = BlockingFakeSession(FakeResponse())
            target = cache.cache_path(self.image_path, self.source_url)

            with patch.object(cache, "_get_session", return_value=session):
                first_status, _ = cache.get_or_schedule(self.image_path, self.source_url)
                self.assertEqual(first_status, CACHE_STATUS_PENDING)
                self.assertTrue(session.started.wait(timeout=5))

                second_status, _ = cache.get_or_schedule(self.image_path, self.source_url)
                self.assertEqual(second_status, CACHE_STATUS_PENDING)
                self.assertEqual(session.calls, 1)

                session.release.set()
                self.assertTrue(self._wait_for(target.exists))
