from __future__ import annotations

import json

from ninja import NinjaAPI, Schema
from ninja.errors import HttpError

from .services import torrent_service
from .services.errors import QbtError

api = NinjaAPI(title='qBittorrent API', version='1.0', urls_namespace='qbittorrent-api')


class QbtStatusOut(Schema):
    configured: bool
    connected: bool
    url: str | None = None
    version: str | None = None
    web_api_version: str | None = None
    torrent_count: int | None = None
    error: str | None = None


class QbtTestIn(Schema):
    url: str | None = None
    username: str | None = None
    password: str | None = None


class QbtLinkedMovieOut(Schema):
    id: int
    title: str
    slug: str


class QbtTorrentOut(Schema):
    info_hash: str
    name: str
    state: str
    progress: float
    size: int
    total_size: int
    dlspeed: int
    upspeed: int
    eta: int
    category: str
    tags: list[str] = []
    save_path: str
    content_path: str
    added_on: int | None = None
    completion_on: int | None = None
    linked_movie: QbtLinkedMovieOut | None = None


class QbtTorrentsOut(Schema):
    items: list[QbtTorrentOut]
    total: int
    limit: int
    offset: int


def _require_api_user(request):
    user = getattr(request, 'user', None)
    if user is None or not user.is_authenticated:
        raise HttpError(401, 'Authentication required')
    return user


def _raise_qbt_error(exc: QbtError):
    detail = {'code': exc.code, 'message': exc.message}
    if exc.hint:
        detail['hint'] = exc.hint
    raise HttpError(exc.status_code, json.dumps(detail, ensure_ascii=False))


@api.exception_handler(HttpError)
def qbt_http_error_handler(request, exc: HttpError):
    try:
        detail = json.loads(exc.message)
        if isinstance(detail, dict):
            return api.create_response(request, {'detail': detail}, status=exc.status_code)
    except (TypeError, ValueError, json.JSONDecodeError):
        pass

    return api.create_response(request, {'detail': str(exc)}, status=exc.status_code)


def _serialize_status(status: torrent_service.QbtStatus) -> QbtStatusOut:
    return QbtStatusOut(
        configured=status.configured,
        connected=status.connected,
        url=status.url,
        version=status.version,
        web_api_version=status.web_api_version,
        torrent_count=status.torrent_count,
        error=status.error,
    )


def _serialize_torrent(row: torrent_service.QbtTorrentRow) -> QbtTorrentOut:
    linked_movie = None
    if row.linked_movie is not None:
        linked_movie = QbtLinkedMovieOut(
            id=row.linked_movie.id,
            title=row.linked_movie.title,
            slug=row.linked_movie.slug,
        )

    return QbtTorrentOut(
        info_hash=row.info_hash,
        name=row.name,
        state=row.state,
        progress=row.progress,
        size=row.size,
        total_size=row.total_size,
        dlspeed=row.dlspeed,
        upspeed=row.upspeed,
        eta=row.eta,
        category=row.category,
        tags=row.tags,
        save_path=row.save_path,
        content_path=row.content_path,
        added_on=row.added_on,
        completion_on=row.completion_on,
        linked_movie=linked_movie,
    )


@api.get('/status', response=QbtStatusOut)
def status(request):
    _require_api_user(request)
    return _serialize_status(torrent_service.get_status())


@api.post('/test', response=QbtStatusOut)
def test_connection(request, payload: QbtTestIn | None = None):
    _require_api_user(request)

    url = None
    username = None
    password = None
    if payload is not None:
        url = (payload.url or '').strip() or None
        username = payload.username
        password = payload.password

    try:
        status_data = torrent_service.test_connection(
            url=url,
            username=username,
            password=password,
        )
    except QbtError as exc:
        _raise_qbt_error(exc)

    return _serialize_status(status_data)


@api.get('/torrents', response=QbtTorrentsOut)
def torrents(request, limit: int = 500, offset: int = 0):
    _require_api_user(request)

    bounded_limit = max(1, min(limit, 1000))
    bounded_offset = max(0, offset)

    try:
        rows, total = torrent_service.list_torrents(
            limit=bounded_limit,
            offset=bounded_offset,
        )
    except QbtError as exc:
        _raise_qbt_error(exc)

    return QbtTorrentsOut(
        items=[_serialize_torrent(row) for row in rows],
        total=total,
        limit=bounded_limit,
        offset=bounded_offset,
    )
