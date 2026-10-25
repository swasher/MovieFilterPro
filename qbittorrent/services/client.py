from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

import qbittorrentapi
import requests

from moviefilter.models import UserPreferences

from .errors import QbtError

QBT_TIMEOUT = (5, 20)

QBT_URL_HINT = (
    'URL должен быть доступен с backend. В Docker это обычно имя сервиса '
    '(например, http://qbittorrent:8080), а не localhost.'
)


def normalize_qbt_url(raw_url: str | None) -> str:
    value = (raw_url or '').strip()
    if not value:
        return ''

    if '://' not in value:
        value = f'http://{value}'

    parsed = urlsplit(value)
    if parsed.scheme not in {'http', 'https'} or not parsed.netloc:
        raise QbtError(
            'qbt_invalid_url',
            'Некорректный URL qBittorrent.',
            hint='Ожидается адрес вида http://nas:8080.',
            status_code=400,
        )

    path = parsed.path.rstrip('/')
    if path.endswith('/api/v2'):
        path = path[: -len('/api/v2')].rstrip('/')

    return urlunsplit((parsed.scheme, parsed.netloc, path, '', ''))


def build_client(
    *,
    preferences: UserPreferences | None = None,
    url: str | None = None,
    username: str | None = None,
    password: str | None = None,
) -> qbittorrentapi.Client:
    preferences = preferences or UserPreferences.get()

    resolved_url = normalize_qbt_url(url if url is not None else preferences.qbt_url)
    if not resolved_url:
        raise QbtError(
            'qbt_not_configured',
            'qBittorrent не настроен.',
            hint='Заполни URL, логин и пароль в Preferences → qBittorrent.',
            status_code=400,
        )

    resolved_username = (username if username is not None else preferences.qbt_username or '').strip()
    resolved_password = password if password is not None else (preferences.qbt_password or '')

    return qbittorrentapi.Client(
        host=resolved_url,
        username=resolved_username or None,
        password=resolved_password or None,
        REQUESTS_ARGS={'timeout': QBT_TIMEOUT},
    )


def qbt_error_from_exception(exc: Exception, *, action: str) -> QbtError:
    if isinstance(exc, requests.exceptions.Timeout):
        return QbtError(
            'qbt_timeout',
            f'qBittorrent не ответил вовремя ({action}).',
            hint=QBT_URL_HINT,
            status_code=504,
        )

    if isinstance(exc, qbittorrentapi.LoginFailed):
        return QbtError(
            'qbt_auth_failed',
            'qBittorrent отклонил логин или пароль.',
            hint='Проверь логин/пароль в Preferences → qBittorrent.',
            status_code=502,
        )

    if isinstance(exc, qbittorrentapi.Forbidden403Error):
        return QbtError(
            'qbt_forbidden',
            'qBittorrent запретил доступ (403).',
            hint='Проверь бан IP, настройки аутентификации и Host header в qBittorrent.',
            status_code=502,
        )

    if isinstance(exc, qbittorrentapi.Unauthorized401Error):
        return QbtError(
            'qbt_unauthorized',
            'qBittorrent отклонил запрос (401).',
            hint='Проверь Host header validation / Server domains в qBittorrent.',
            status_code=502,
        )

    if isinstance(exc, qbittorrentapi.Conflict409Error):
        return QbtError(
            'qbt_conflict',
            'qBittorrent вернул конфликт (409).',
            hint='Возможно, торрент уже добавлен или категория недоступна.',
            status_code=409,
        )

    if isinstance(exc, qbittorrentapi.UnsupportedMediaType415Error):
        return QbtError(
            'qbt_invalid_torrent',
            'qBittorrent не принял torrent-файл.',
            status_code=400,
        )

    if isinstance(exc, qbittorrentapi.NotFound404Error):
        return QbtError(
            'qbt_torrent_not_found',
            'Раздача не найдена в qBittorrent.',
            status_code=404,
        )

    if isinstance(exc, qbittorrentapi.APIConnectionError):
        return QbtError(
            'qbt_unreachable',
            f'Не удалось связаться с qBittorrent ({action}).',
            hint=QBT_URL_HINT,
            status_code=502,
        )

    return QbtError(
        'qbt_error',
        f'Ошибка qBittorrent ({action}): {exc}',
        status_code=502,
    )
