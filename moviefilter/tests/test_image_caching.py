import os
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

import requests
from django.test import SimpleTestCase, override_settings
from requests.cookies import RequestsCookieJar

from movie_filter_pro.settings import HIGH
from moviefilter import image_caching
from moviefilter.image_caching import (
    CACHE_STATUS_MISSING,
    CACHE_STATUS_PENDING,
    FASTPIC_HOME_URL,
    MISSING_MARKER_VERSION,
    MISSING_RETRY_SECONDS,
    download_and_cache_image,
    get_cached_image_state,
    get_cached_image_url,
    get_placeholder_image_url,
)


class FakeResponse:
    def __init__(self, status_code=200, content=b"", headers=None):
        self.status_code = status_code
        self.headers = headers or {}
        self._content = content

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(response=self)

    def iter_content(self, chunk_size=8192):
        yield self._content

    def close(self):
        pass


class FakeFastpicSession:
    """Повторяет поведение fastpic: без cookie картинка отвечает 404."""

    def __init__(
        self,
        *,
        homepage_status=200,
        image_status=200,
        image_content=b"poster",
        required_cookie_value=None,
    ):
        self.cookies = RequestsCookieJar()
        self.headers = {}
        self.homepage_status = homepage_status
        self.image_status = image_status
        self.image_content = image_content
        self.required_cookie_value = required_cookie_value
        self.requested_urls = []

    def mount(self, *args, **kwargs):
        pass

    def get(self, url, **kwargs):
        self.requested_urls.append(url)
        if url == FASTPIC_HOME_URL:
            if self.homepage_status < 400:
                self.cookies.set("fp_n_uid", "session-token", domain=".fastpic.org", path="/")
            return FakeResponse(self.homepage_status)

        cookie = self.cookies.get("fp_n_uid")
        if not cookie:
            return FakeResponse(404)
        if self.required_cookie_value and cookie != self.required_cookie_value:
            return FakeResponse(404)
        return FakeResponse(self.image_status, self.image_content)


def _build_paths(image_url, movie_pk):
    cached_filename, cached_filepath, missing_marker_path, failed_marker_path = (
        image_caching._build_cached_paths(image_url, movie_pk)
    )
    return cached_filename, cached_filepath, missing_marker_path, failed_marker_path


class ImageCachingTests(SimpleTestCase):
    def test_returns_placeholder_when_image_is_missing(self):
        image_url = "https://kinozal.guru/i/poster/9/5/1304395.jpg"

        with TemporaryDirectory() as temp_dir:
            cache_root = Path(temp_dir)
            response = Mock()
            response.raise_for_status.side_effect = requests.exceptions.HTTPError(
                response=Mock(status_code=404)
            )

            with override_settings(
                CACHE_ROOT=cache_root,
                CACHE_URL="/media/cached_images/",
                STATIC_URL="/static/",
            ):
                with patch("moviefilter.image_caching.requests.Session") as session_mock:
                    session_mock.return_value.get.return_value = response
                    download_and_cache_image(image_url, 42, HIGH)

                poster_url = get_cached_image_url(image_url, 42, HIGH)

        self.assertEqual(poster_url, get_placeholder_image_url())

    def test_fastpic_download_primes_session_before_request(self):
        image_url = "https://i126.fastpic.org/big/2025/1125/44/poster.jpg"

        with TemporaryDirectory() as temp_dir:
            cache_root = Path(temp_dir)
            session = FakeFastpicSession()

            with override_settings(CACHE_ROOT=cache_root, CACHE_URL="/media/cached_images/"):
                image_caching._fastpic_cookies.clear()
                self.addCleanup(image_caching._fastpic_cookies.clear)
                with patch("moviefilter.image_caching.requests.Session", return_value=session):
                    download_and_cache_image(image_url, 7, HIGH)

                _, cached_filepath, _, _ = _build_paths(image_url, 7)
                self.assertEqual(cached_filepath.read_bytes(), b"poster")

        self.assertEqual(session.headers.get("User-Agent"), image_caching.IMAGE_REQUEST_USER_AGENT)
        self.assertEqual(
            session.requested_urls,
            [FASTPIC_HOME_URL, image_url],
        )

    def test_fastpic_cookies_are_reused_between_downloads(self):
        image_url = "https://i126.fastpic.org/big/2025/1125/44/poster.jpg"

        with TemporaryDirectory() as temp_dir:
            cache_root = Path(temp_dir)

            with override_settings(CACHE_ROOT=cache_root, CACHE_URL="/media/cached_images/"):
                image_caching._fastpic_cookies.clear()
                self.addCleanup(image_caching._fastpic_cookies.clear)

                first_session = FakeFastpicSession()
                with patch("moviefilter.image_caching.requests.Session", return_value=first_session):
                    download_and_cache_image(image_url, 7, HIGH)

                second_session = FakeFastpicSession()
                with patch("moviefilter.image_caching.requests.Session", return_value=second_session):
                    download_and_cache_image("https://i126.fastpic.org/big/2025/1125/44/other.jpg", 8, HIGH)

        self.assertNotIn(FASTPIC_HOME_URL, second_session.requested_urls)
        self.assertEqual(second_session.requested_urls, ["https://i126.fastpic.org/big/2025/1125/44/other.jpg"])

    def test_stale_fastpic_cookie_is_refreshed(self):
        image_url = "https://i126.fastpic.org/big/2025/1125/44/poster.jpg"

        with TemporaryDirectory() as temp_dir:
            cache_root = Path(temp_dir)
            session = FakeFastpicSession(required_cookie_value="session-token")

            with override_settings(CACHE_ROOT=cache_root, CACHE_URL="/media/cached_images/"):
                image_caching._fastpic_cookies.clear()
                image_caching._fastpic_cookies["fp_n_uid"] = "stale-token"
                self.addCleanup(image_caching._fastpic_cookies.clear)
                with patch("moviefilter.image_caching.requests.Session", return_value=session):
                    download_and_cache_image(image_url, 7, HIGH)

                _, cached_filepath, _, _ = _build_paths(image_url, 7)
                self.assertEqual(cached_filepath.read_bytes(), b"poster")

        self.assertEqual(
            session.requested_urls,
            [image_url, FASTPIC_HOME_URL, image_url],
        )

    def test_fastpic_missing_image_is_marked_as_missing_after_priming(self):
        image_url = "https://i126.fastpic.org/big/2025/1125/44/poster.jpg"

        with TemporaryDirectory() as temp_dir:
            cache_root = Path(temp_dir)
            session = FakeFastpicSession(image_status=404)

            with override_settings(CACHE_ROOT=cache_root, CACHE_URL="/media/cached_images/"):
                image_caching._fastpic_cookies.clear()
                self.addCleanup(image_caching._fastpic_cookies.clear)
                with patch("moviefilter.image_caching.requests.Session", return_value=session):
                    download_and_cache_image(image_url, 7, HIGH)

                _, cached_filepath, missing_marker_path, failed_marker_path = _build_paths(image_url, 7)
                self.assertFalse(cached_filepath.exists())
                self.assertTrue(missing_marker_path.exists())
                self.assertFalse(failed_marker_path.exists())

    def test_fastpic_404_without_cookie_is_not_treated_as_missing(self):
        image_url = "https://i126.fastpic.org/big/2025/1125/44/poster.jpg"

        with TemporaryDirectory() as temp_dir:
            cache_root = Path(temp_dir)
            session = FakeFastpicSession(homepage_status=500)

            with override_settings(CACHE_ROOT=cache_root, CACHE_URL="/media/cached_images/"):
                image_caching._fastpic_cookies.clear()
                self.addCleanup(image_caching._fastpic_cookies.clear)
                with patch("moviefilter.image_caching.requests.Session", return_value=session):
                    download_and_cache_image(image_url, 7, HIGH)

                _, cached_filepath, missing_marker_path, failed_marker_path = _build_paths(image_url, 7)
                self.assertFalse(cached_filepath.exists())
                self.assertFalse(missing_marker_path.exists())
                self.assertTrue(failed_marker_path.exists())

    def test_legacy_missing_marker_is_ignored_and_removed(self):
        image_url = "https://i126.fastpic.org/big/2025/1125/44/poster.jpg"

        with TemporaryDirectory() as temp_dir:
            cache_root = Path(temp_dir)

            with override_settings(CACHE_ROOT=cache_root, CACHE_URL="/media/cached_images/"):
                _, _, missing_marker_path, _ = _build_paths(image_url, 7)
                missing_marker_path.write_bytes(b"")

                with patch("moviefilter.image_caching.threading.Thread") as thread_mock:
                    status, cached_filepath = get_cached_image_state(image_url, 7, HIGH)

                self.assertEqual(status, CACHE_STATUS_PENDING)
                self.assertIsNone(cached_filepath)
                self.assertFalse(missing_marker_path.exists())
                thread_mock.assert_called_once()

    def test_fresh_missing_marker_returns_missing(self):
        image_url = "https://i126.fastpic.org/big/2025/1125/44/poster.jpg"

        with TemporaryDirectory() as temp_dir:
            cache_root = Path(temp_dir)

            with override_settings(CACHE_ROOT=cache_root, CACHE_URL="/media/cached_images/"):
                _, _, missing_marker_path, _ = _build_paths(image_url, 7)
                missing_marker_path.write_text(MISSING_MARKER_VERSION, encoding="utf-8")

                with patch("moviefilter.image_caching.threading.Thread") as thread_mock:
                    status, cached_filepath = get_cached_image_state(image_url, 7, HIGH)

                self.assertEqual(status, CACHE_STATUS_MISSING)
                self.assertIsNone(cached_filepath)
                thread_mock.assert_not_called()

    def test_expired_missing_marker_is_retried(self):
        image_url = "https://i126.fastpic.org/big/2025/1125/44/poster.jpg"

        with TemporaryDirectory() as temp_dir:
            cache_root = Path(temp_dir)

            with override_settings(CACHE_ROOT=cache_root, CACHE_URL="/media/cached_images/"):
                _, _, missing_marker_path, _ = _build_paths(image_url, 7)
                missing_marker_path.write_text(MISSING_MARKER_VERSION, encoding="utf-8")
                expired_at = time.time() - MISSING_RETRY_SECONDS - 60
                os.utime(missing_marker_path, (expired_at, expired_at))

                with patch("moviefilter.image_caching.threading.Thread") as thread_mock:
                    status, cached_filepath = get_cached_image_state(image_url, 7, HIGH)

                self.assertEqual(status, CACHE_STATUS_PENDING)
                self.assertIsNone(cached_filepath)
                self.assertFalse(missing_marker_path.exists())
                thread_mock.assert_called_once()
