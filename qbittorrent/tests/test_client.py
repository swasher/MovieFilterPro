from types import SimpleNamespace
from unittest.mock import patch

import qbittorrentapi
import requests
from django.test import SimpleTestCase

from qbittorrent.services.client import (
    build_client,
    normalize_qbt_url,
    qbt_error_from_exception,
)


def _preferences(**overrides):
    values = {
        'qbt_url': 'qnap:18687',
        'qbt_api_key': 'qbt_test_key',
        'qbt_skip_cert_verify': True,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _api_connection_error(cause: BaseException | None = None):
    try:
        if cause is None:
            raise qbittorrentapi.APIConnectionError('Failed to connect to qBittorrent.')
        try:
            raise cause
        except BaseException as exc:  # noqa: BLE001 - нужно воспроизвести chaining
            raise qbittorrentapi.APIConnectionError('Failed to connect to qBittorrent.') from exc
    except qbittorrentapi.APIConnectionError as exc:
        return exc


class NormalizeQbtUrlTests(SimpleTestCase):
    def test_adds_default_scheme(self):
        self.assertEqual(normalize_qbt_url('qnap:18687'), 'http://qnap:18687')

    def test_strips_api_suffix_and_trailing_slash(self):
        self.assertEqual(
            normalize_qbt_url('https://qnap:18687/api/v2/'),
            'https://qnap:18687',
        )

    def test_rejects_invalid_url(self):
        with self.assertRaises(Exception) as ctx:
            normalize_qbt_url('ftp://qnap:18687')
        self.assertEqual(ctx.exception.code, 'qbt_invalid_url')


class BuildClientTests(SimpleTestCase):
    @patch('qbittorrent.services.client.qbittorrentapi.Client')
    def test_uses_api_key_and_skips_certificate_when_enabled(self, client_mock):
        build_client(preferences=_preferences())

        kwargs = client_mock.call_args.kwargs
        self.assertEqual(kwargs['host'], 'http://qnap:18687')
        self.assertEqual(kwargs['api_key'], 'qbt_test_key')
        self.assertIs(kwargs['VERIFY_WEBUI_CERTIFICATE'], False)
        self.assertNotIn('username', kwargs)
        self.assertNotIn('password', kwargs)

    @patch('qbittorrent.services.client.qbittorrentapi.Client')
    def test_verifies_certificate_by_default(self, client_mock):
        build_client(preferences=_preferences(qbt_skip_cert_verify=False))

        self.assertIs(client_mock.call_args.kwargs['VERIFY_WEBUI_CERTIFICATE'], True)

    @patch('qbittorrent.services.client.qbittorrentapi.Client')
    def test_requires_api_key(self, client_mock):
        with self.assertRaises(Exception) as ctx:
            build_client(preferences=_preferences(qbt_api_key=''))

        self.assertEqual(ctx.exception.code, 'qbt_not_configured')
        client_mock.assert_not_called()


class QbtErrorMappingTests(SimpleTestCase):
    def test_ssl_error_has_dedicated_message(self):
        exc = _api_connection_error(
            requests.exceptions.SSLError(
                'CERTIFICATE_VERIFY_FAILED: self-signed certificate'
            )
        )

        error = qbt_error_from_exception(exc, action='проверка подключения')

        self.assertEqual(error.code, 'qbt_ssl_error')
        self.assertIn('самоподписанным', error.message)
        self.assertIn('Не проверять TLS-сертификат', error.hint or '')

    def test_plain_connection_error_stays_unreachable(self):
        error = qbt_error_from_exception(
            _api_connection_error(requests.exceptions.ConnectionError('refused')),
            action='проверка подключения',
        )

        self.assertEqual(error.code, 'qbt_unreachable')
