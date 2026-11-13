from __future__ import annotations

import json

from ninja import File, NinjaAPI, Schema
from ninja.errors import HttpError
from ninja.files import UploadedFile

from vault.models import Movie

from .models import Torrent
from .services import torrent_service
from .services.errors import QbtError

api = NinjaAPI(title='qBittorrent API', version='1.0', urls_namespace='qbittorrent-api')

MAX_TORRENT_UPLOAD_BYTES = 10 * 1024 * 1024


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
    api_key: str | None = None
    skip_cert_verify: bool | None = None


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
    source_url: str | None = None
    added_on: int | None = None
    completion_on: int | None = None
    linked_movie: QbtLinkedMovieOut | None = None


class QbtTorrentsOut(Schema):
    items: list[QbtTorrentOut]
    total: int
    limit: int
    offset: int


class QbtProgressOut(Schema):
    info_hash: str
    state: str
    progress: float
    dlspeed: int
    upspeed: int
    eta: int
    size: int


class QbtProgressIn(Schema):
    hashes: list[str] = []


class QbtProgressResponse(Schema):
    available: bool
    items: list[QbtProgressOut] = []


class QbtLinkIn(Schema):
    movie_id: int


class QbtLinkOut(Schema):
    message: str
    info_hash: str
    movie: QbtLinkedMovieOut
    warning: str | None = None


class QbtDeleteIn(Schema):
    delete_files: bool = True


class QbtTorrentDeleteOut(Schema):
    message: str
    info_hash: str
    name: str
    qbt_deleted: bool
    archive_deleted: bool
    record_deleted: bool
    error: str | None = None


class QbtMovieTorrentsDeleteOut(Schema):
    message: str
    deleted: list[QbtTorrentDeleteOut] = []
    deleted_count: int = 0
    errors: list[str] = []


class QbtMovieTorrentUploadOut(Schema):
    message: str
    info_hash: str
    name: str
    archive_saved: bool = False
    warning: str | None = None
    movie: QbtLinkedMovieOut


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
        source_url=row.torrent.source_url if row.torrent is not None and row.torrent.source_url else None,
        added_on=row.added_on,
        completion_on=row.completion_on,
        linked_movie=linked_movie,
    )


def _serialize_torrent_delete(
    result: torrent_service.TorrentDeleteResult,
    *,
    message: str,
) -> QbtTorrentDeleteOut:
    return QbtTorrentDeleteOut(
        message=message,
        info_hash=result.info_hash,
        name=result.name,
        qbt_deleted=result.qbt_deleted,
        archive_deleted=result.archive_deleted,
        record_deleted=result.record_deleted,
        error=result.error,
    )


@api.get('/status', response=QbtStatusOut)
def status(request):
    _require_api_user(request)
    return _serialize_status(torrent_service.get_status())


@api.post('/test', response=QbtStatusOut)
def test_connection(request, payload: QbtTestIn | None = None):
    _require_api_user(request)

    url = None
    api_key = None
    skip_cert_verify = None
    if payload is not None:
        url = (payload.url or '').strip() or None
        api_key = payload.api_key
        skip_cert_verify = payload.skip_cert_verify

    try:
        status_data = torrent_service.test_connection(
            url=url,
            api_key=api_key,
            skip_cert_verify=skip_cert_verify,
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


@api.post('/progress', response=QbtProgressResponse)
def progress(request, payload: QbtProgressIn):
    _require_api_user(request)

    requested_hashes = [
        value.strip()
        for value in payload.hashes
        if value.strip()
    ][:200]
    available, rows = torrent_service.get_progress(requested_hashes)

    return QbtProgressResponse(
        available=available,
        items=[
            QbtProgressOut(
                info_hash=row.info_hash,
                state=row.state,
                progress=row.progress,
                dlspeed=row.dlspeed,
                upspeed=row.upspeed,
                eta=row.eta,
                size=row.size,
            )
            for row in rows
        ],
    )


@api.post('/torrents/{info_hash}/delete', response=QbtTorrentDeleteOut)
def delete_torrent(request, info_hash: str, payload: QbtDeleteIn | None = None):
    _require_api_user(request)

    normalized = (info_hash or '').strip().lower()
    torrent = (
        Torrent.objects.filter(info_hash=normalized)
        .select_related('movie')
        .first()
    )
    if torrent is None:
        raise HttpError(404, 'Torrent not found')

    delete_files = True if payload is None else payload.delete_files
    result = torrent_service.delete_torrent(
        torrent,
        delete_files=delete_files,
        reason='manual',
    )

    if result.record_deleted:
        if result.error:
            message = 'Раздача удалена, но остались предупреждения.'
        elif delete_files:
            message = 'Раздача, файлы и архив удалены.'
        else:
            message = 'Раздача и архив удалены.'
    else:
        message = result.error or 'Не удалось удалить раздачу.'

    return _serialize_torrent_delete(result, message=message)


@api.post('/movies/{movie_id}/torrents/delete', response=QbtMovieTorrentsDeleteOut)
def delete_movie_torrents(request, movie_id: int, payload: QbtDeleteIn | None = None):
    _require_api_user(request)

    movie = Movie.objects.filter(pk=movie_id).first()
    if movie is None:
        raise HttpError(404, 'Movie not found')

    delete_files = True if payload is None else payload.delete_files
    result = torrent_service.delete_movie_torrents(
        movie,
        delete_files=delete_files,
        reason='manual',
    )

    deleted = [
        _serialize_torrent_delete(
            item,
            message='Раздача удалена.' if item.record_deleted else (item.error or 'Не удалось удалить раздачу.'),
        )
        for item in result.results
    ]

    if not result.results:
        message = 'У фильма нет привязанных раздач.'
    elif result.errors:
        message = f'Удалено раздач: {result.deleted_count} из {len(result.results)}.'
    else:
        message = f'Удалено раздач: {result.deleted_count}.'

    return QbtMovieTorrentsDeleteOut(
        message=message,
        deleted=deleted,
        deleted_count=result.deleted_count,
        errors=result.errors,
    )


@api.post('/torrents/{info_hash}/link', response=QbtLinkOut)
def link_torrent(request, info_hash: str, payload: QbtLinkIn):
    _require_api_user(request)

    movie = Movie.objects.filter(pk=payload.movie_id).first()
    if movie is None:
        raise HttpError(404, 'Movie not found')

    try:
        torrent, warning = torrent_service.attach_torrent_to_movie(info_hash, movie)
    except QbtError as exc:
        _raise_qbt_error(exc)

    return QbtLinkOut(
        message=f'Раздача привязана к фильму «{movie.title}».',
        info_hash=torrent.info_hash,
        movie=QbtLinkedMovieOut(
            id=movie.id,
            title=movie.title,
            slug=movie.slug,
        ),
        warning=warning,
    )


def _error_detail(code: str, message: str) -> str:
    return json.dumps({'code': code, 'message': message}, ensure_ascii=False)


@api.post('/movies/{movie_id}/torrents/upload', response=QbtMovieTorrentUploadOut)
def upload_movie_torrent(request, movie_id: int, file: File[UploadedFile]):
    user = _require_api_user(request)

    movie = Movie.objects.filter(pk=movie_id).first()
    if movie is None:
        raise HttpError(404, 'Movie not found')

    declared_size = getattr(file, 'size', None)
    if declared_size is not None and declared_size > MAX_TORRENT_UPLOAD_BYTES:
        raise HttpError(
            400,
            _error_detail('qbt_torrent_too_large', 'Файл больше 10 МБ.'),
        )

    torrent_bytes = file.read()
    if not torrent_bytes:
        raise HttpError(400, _error_detail('qbt_torrent_empty', 'Файл пустой.'))
    if len(torrent_bytes) > MAX_TORRENT_UPLOAD_BYTES:
        raise HttpError(
            400,
            _error_detail('qbt_torrent_too_large', 'Файл больше 10 МБ.'),
        )

    try:
        add_result = torrent_service.add_torrent_from_file(
            torrent_bytes=torrent_bytes,
            movie=movie,
            tag=f'mfp:{movie.id}',
            original_filename=getattr(file, 'name', None),
        )
    except QbtError as exc:
        _raise_qbt_error(exc)

    torrent = add_result.torrent
    if add_result.created:
        message = f'Торрент добавлен в qBittorrent и привязан к фильму «{movie.title}».'
    else:
        message = f'Раздача уже была в базе. Привязка к фильму «{movie.title}» подтверждена.'

    return QbtMovieTorrentUploadOut(
        message=message,
        info_hash=torrent.info_hash,
        name=torrent.name,
        archive_saved=add_result.archive_saved,
        warning=add_result.warning,
        movie=QbtLinkedMovieOut(
            id=movie.id,
            title=movie.title,
            slug=movie.slug,
        ),
    )
