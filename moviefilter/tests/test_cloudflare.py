"""
Тесты обхода Cloudflare в транспортном слое Kinozal.

Проверяем три слоя:
- детектор челленджа (включая анти-false-positive на `challenge-platform`);
- сборку requests.Response из Scrapling Response и перенос cf_clearance;
- встраивание эскалации в KinozalClient.get_html_response.
"""

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import requests
from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase

from moviefilter.kinozal import KinozalClient
from moviefilter.kinozal.cloudflare import (
    CloudflareBlockedError,
    _scrapling_response_cookies,
    _to_requests_response,
    cloudflare_bypass,
    cookie_domain,
    detect_challenge,
)
from moviefilter.models import UserPreferences

CHALLENGE_HTML = b"<html><head><title>Just a moment...</title></head><body>cf-turnstile-response</body></html>"

# Нормальная страница за Cloudflare: скрипт challenge-platform остаётся в HTML
# и после прохождения проверки, поэтому НЕ должен считаться маркером челленджа.
NORMAL_HTML = (
    b"<html><head><title>Torrent treker Kinozal.GURU</title>"
    b"<script src='/cdn-cgi/challenge-platform/h/b/orchestrate/chl_page/v1'></script></head>"
    b"<body><a href='details.php?id=1'>film</a></body></html>"
)


class CloudflareDetectorTests(SimpleTestCase):
    def test_challenge_title_marker_detected(self):
        html = b"<html><head><title>Just a moment...</title></head><body>x</body></html>"
        reasons = detect_challenge(html, 200)
        self.assertTrue(reasons)

    def test_challenge_body_marker_detected(self):
        reasons = detect_challenge(CHALLENGE_HTML, 200)
        self.assertTrue(any("cf-turnstile-response" in r for r in reasons))

    def test_small_403_is_challenge(self):
        reasons = detect_challenge(b"forbidden", 403)
        self.assertTrue(reasons)

    def test_challenge_platform_script_is_not_false_positive(self):
        reasons = detect_challenge(NORMAL_HTML, 200)
        self.assertEqual(reasons, [])

    def test_cookie_domain_strips_www(self):
        self.assertEqual(cookie_domain("https://kinozal.guru/browse.php"), ".kinozal.guru")
        self.assertEqual(cookie_domain("https://www.kinozal.guru/"), ".kinozal.guru")
        self.assertIsNone(cookie_domain("https://"))


class ResponseAdapterTests(SimpleTestCase):
    def test_to_requests_response_maps_fields(self):
        scrapling = SimpleNamespace(
            status=200,
            url="https://kinozal.guru/",
            reason="OK",
            body=b"<html>ok</html>",
            headers={"content-type": "text/html"},
        )
        resp = _to_requests_response(scrapling, 12.5)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.ok)
        self.assertEqual(resp.content, b"<html>ok</html>")
        self.assertEqual(resp.url, "https://kinozal.guru/")
        self.assertIsInstance(resp.elapsed, timedelta)

    def test_to_requests_response_raise_for_status(self):
        scrapling = SimpleNamespace(status=503, url="x", reason="Unavailable", body=b"", headers={})
        resp = _to_requests_response(scrapling, 1.0)
        with self.assertRaises(requests.HTTPError):
            resp.raise_for_status()

    def test_scrapling_cookies_normalizes_forms(self):
        self.assertEqual(_scrapling_response_cookies(SimpleNamespace(cookies=None)), ())
        self.assertEqual(
            _scrapling_response_cookies(SimpleNamespace(cookies={"name": "a", "value": "1"})),
            ({"name": "a", "value": "1"},),
        )
        self.assertEqual(
            _scrapling_response_cookies(SimpleNamespace(cookies=[{"name": "a"}, "junk", {"name": "b"}])),
            ({"name": "a"}, {"name": "b"}),
        )


class CloudflareBypassTests(SimpleTestCase):
    def setUp(self):
        # Синглтон глобален — сбрасываем состояние между тестами.
        cloudflare_bypass._cache.clear()

    def _scrapling_response(self, cookies=(), status=200, body=b"<html><title>Torrent treker</title></html>"):
        return SimpleNamespace(
            status=status,
            url="https://kinozal.guru/",
            reason="OK" if status == 200 else "Forbidden",
            body=body,
            headers={"content-type": "text/html"},
            cookies=tuple(cookies),
            request_headers={"user-agent": "Mozilla/5.0 (X11; Linux x86_64) Chrome/156.0.0.0 Safari/537.36"},
        )

    @patch("moviefilter.kinozal.cloudflare.log")
    @patch("scrapling.fetchers.StealthyFetcher.fetch")
    def test_escape_stores_clearance_and_returns_requests_response(self, fetch_mock, log_mock):
        fetch_mock.return_value = self._scrapling_response(
            cookies=(
                {"name": "cf_clearance", "value": "abc123", "domain": ".kinozal.guru", "path": "/"},
                {"name": "cf_bm", "value": "xyz", "domain": ".kinozal.guru", "path": "/"},
            )
        )

        session = requests.Session()
        resp = cloudflare_bypass.escape(
            "https://kinozal.guru/browse.php",
            session,
            auth_cookies=[{"name": "uid", "value": "u", "domain": ".kinozal.guru", "path": "/"}],
        )

        self.assertIsInstance(resp, requests.Response)
        self.assertEqual(resp.status_code, 200)
        # Кэш и активная сессия получили cf_clearance.
        self.assertEqual(
            cloudflare_bypass._cache[".kinozal.guru"]["cookies"]["cf_clearance"], "abc123"
        )
        self.assertEqual(session.cookies.get("cf_clearance", domain=".kinozal.guru"), "abc123")
        # Браузеру переданы solve_cloudflare и куки авторизации, но НЕ фиксированный UA.
        _, kwargs = fetch_mock.call_args
        self.assertTrue(kwargs["solve_cloudflare"])
        self.assertNotIn("useragent", kwargs)
        self.assertEqual(kwargs["cookies"][0]["name"], "uid")
        # requests-сессия переключена на реальный UA браузера.
        self.assertEqual(session.headers["User-Agent"], "Mozilla/5.0 (X11; Linux x86_64) Chrome/156.0.0.0 Safari/537.36")

    @patch("moviefilter.kinozal.cloudflare.log")
    @patch("scrapling.fetchers.StealthyFetcher.fetch")
    def test_escape_raises_cloudflare_blocked_and_does_not_cache(self, fetch_mock, log_mock):
        # Cloudflare отдал куку, но контент всё равно остался челленджем — clearance мусорный.
        fetch_mock.return_value = self._scrapling_response(
            cookies=(
                {"name": "cf_clearance", "value": "junk", "domain": ".kinozal.guru", "path": "/"},
            ),
            status=403,
            body=b"<html><head><title>Just a moment...</title></head><body>cf-turnstile-response</body></html>",
        )

        with self.assertRaises(CloudflareBlockedError):
            cloudflare_bypass.escape("https://kinozal.guru/browse.php", requests.Session())

        self.assertNotIn(".kinozal.guru", cloudflare_bypass._cache)

    @patch("moviefilter.kinozal.cloudflare.log")
    @patch("scrapling.fetchers.StealthyFetcher.fetch")
    def test_escape_raises_request_exception_on_browser_failure(self, fetch_mock, log_mock):
        fetch_mock.side_effect = TimeoutError("Page.goto timeout")
        with self.assertRaises(requests.RequestException):
            cloudflare_bypass.escape("https://kinozal.guru/", requests.Session())

    def test_apply_clearance_noop_without_cache(self):
        session = requests.Session()
        self.assertFalse(cloudflare_bypass.apply_clearance(session, "https://kinozal.guru/"))
        self.assertEqual(len(session.cookies), 0)


class KinozalClientCloudflareIntegrationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="cf-user", password="secret")
        UserPreferences.objects.create(
            user=self.user,
            kinozal_domain="kinozal.tv",
            cookie_uid="uid123",
            cookie_pass="pass123",
        )

    def _challenge_response(self):
        resp = requests.Response()
        resp.status_code = 403
        resp._content = b"<html><title>Just a moment...</title></html>"
        resp.url = "https://kinozal.tv/browse.php"
        return resp

    def _ok_response(self):
        resp = requests.Response()
        resp.status_code = 200
        resp._content = b"<html><title>Razdachi</title></html>"
        resp.url = "https://kinozal.tv/browse.php"
        resp.reason = "OK"
        return resp

    @patch("moviefilter.kinozal.kinozal_client.log")
    def test_get_html_response_escalates_on_challenge(self, log_mock):
        client = KinozalClient()
        ok_response = self._ok_response()

        with patch.object(client.session, "get", return_value=self._challenge_response()) as get_mock, \
             patch.object(cloudflare_bypass, "escape", return_value=ok_response) as escape_mock:
            response = client.get_html_response("https://kinozal.tv/browse.php")

        self.assertEqual(response, ok_response)
        escape_mock.assert_called_once()

    @patch("moviefilter.kinozal.kinozal_client.log")
    def test_get_html_response_no_escalation_without_challenge(self, log_mock):
        client = KinozalClient()
        ok_response = self._ok_response()

        with patch.object(client.session, "get", return_value=ok_response), \
             patch.object(cloudflare_bypass, "escape") as escape_mock:
            response = client.get_html_response("https://kinozal.tv/browse.php")

        self.assertEqual(response, ok_response)
        escape_mock.assert_not_called()
