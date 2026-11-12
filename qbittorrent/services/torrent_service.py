from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

import qbittorrentapi

from moviefilter.models import UserPreferences
from vault.models import Movie

from ..models import Torrent, TorrentEvent
from .client import (
    QBT_SETUP_HINT,
    build_client,
    normalize_qbt_url,
    qbt_error_from_exception,
)
from .errors import QbtError
from .metadata import TorrentMetadataError, parse_torrent_metadata
from .paths import (
    archive_exists,
    delete_torrent_archive,
    ensure_backup_folder,
    resolve_backup_folder,
    write_torrent_archive,
)

logger = logging.getLogger('qbittorrent')

ADD_VERIFY_ATTEMPTS = 6
ADD_VERIFY_DELAY_SECONDS = 0.5


@dataclass(slots=True, frozen=True)
class QbtStatus:
    configured: bool
    connected: bool
    url: str | None = None
    version: str | None = None
    web_api_version: str | None = None
    torrent_count: int | None = None
    error: str | None = None


@dataclass(slots=True, frozen=True)
class TorrentAddResult:
    torrent: Torrent
    created: bool
    archive_saved: bool
    warning: str | None = None


@dataclass(slots=True, frozen=True)
class QbtTorrentRow:
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
    tags: list[str]
    save_path: str
    content_path: str
    added_on: int | None
    completion_on: int | None
    torrent: Torrent | None
    linked_movie: Movie | None


@dataclass(slots=True, frozen=True)
class QbtProgressRow:
    info_hash: str
    state: str
    progress: float
    dlspeed: int
    upspeed: int
    eta: int
    size: int


@dataclass(slots=True, frozen=True)
class TorrentDeleteResult:
    info_hash: str
    name: str
    qbt_deleted: bool
    archive_deleted: bool
    record_deleted: bool
    error: str | None = None


@dataclass(slots=True, frozen=True)
class MovieTorrentsDeleteResult:
    results: list[TorrentDeleteResult]
    errors: list[str]

    @property
    def deleted_count(self) -> int:
        return sum(1 for item in self.results if item.record_deleted)


def _preferences() -> UserPreferences:
    return UserPreferences.get()


def _safe_str(value: Any) -> str:
    return str(value).strip() if value is not None else ''


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _safe_optional_int(value: Any) -> int | None:
    if value in (None, ''):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _tags_list(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    raw = _safe_str(value)
    if not raw:
        return []
    return [item.strip() for item in raw.split(',') if item.strip()]


def _log_event(
    event_type: str,
    message: str,
    *,
    level: str = TorrentEvent.Level.INFO,
    torrent: Torrent | None = None,
    movie: Movie | None = None,
    payload: dict | None = None,
) -> None:
    try:
        TorrentEvent.objects.create(
            torrent=torrent,
            movie=movie,
            level=level,
            event_type=event_type,
            message=message,
            payload=payload,
        )
    except Exception:  # noqa: BLE001 - журнал не должен ломать основной сценарий
        logger.exception('Не удалось записать TorrentEvent: %s', event_type)


def _configured_url(preferences: UserPreferences) -> str:
    try:
        return normalize_qbt_url(preferences.qbt_url)
    except QbtError:
        return ''


def validate_ready() -> None:
    """Проверяет настройки qbt и backup-папку до скачивания .torrent с Kinozal."""
    preferences = _preferences()
    if not _configured_url(preferences):
        raise QbtError(
            'qbt_not_configured',
            'qBittorrent не настроен.',
            hint=QBT_SETUP_HINT,
            status_code=400,
        )

    configured_folder = (preferences.torrents_backup_folder or '').strip()
    if not configured_folder:
        raise QbtError(
            'qbt_backup_folder_not_configured',
            'Не настроена папка backup для .torrent.',
            hint='Укажи папку в Preferences → qBittorrent (в Docker обычно /app/backup_torrents).',
            status_code=400,
        )

    try:
        ensure_backup_folder(resolve_backup_folder(configured_folder))
    except (ValueError, OSError) as exc:
        raise QbtError(
            'qbt_backup_folder_invalid',
            'Папка backup для .torrent недоступна.',
            hint=str(exc),
            status_code=400,
        ) from exc

    try:
        client = build_client(preferences=preferences)
        client.app_version()
    except Exception as exc:  # noqa: BLE001
        raise qbt_error_from_exception(exc, action='проверка подключения') from exc


def get_status() -> QbtStatus:
    preferences = _preferences()
    url = _configured_url(preferences)
    if not url:
        return QbtStatus(configured=False, connected=False)

    try:
        client = build_client(preferences=preferences)
        version = _safe_str(client.app_version())
        web_api_version = _safe_str(client.app_web_api_version())
        return QbtStatus(
            configured=True,
            connected=True,
            url=url,
            version=version or None,
            web_api_version=web_api_version or None,
            torrent_count=client.torrents_count(),
        )
    except QbtError as exc:
        return QbtStatus(configured=True, connected=False, url=url, error=exc.message)
    except Exception as exc:  # noqa: BLE001
        mapped = qbt_error_from_exception(exc, action='проверка подключения')
        return QbtStatus(configured=True, connected=False, url=url, error=mapped.message)


def test_connection(
    *,
    url: str | None = None,
    api_key: str | None = None,
    skip_cert_verify: bool | None = None,
) -> QbtStatus:
    preferences = _preferences()
    resolved_url = normalize_qbt_url(url if url is not None else preferences.qbt_url)
    if not resolved_url:
        raise QbtError(
            'qbt_not_configured',
            'qBittorrent не настроен.',
            hint=QBT_SETUP_HINT,
            status_code=400,
        )

    try:
        client = build_client(
            preferences=preferences,
            url=resolved_url,
            api_key=api_key,
            skip_cert_verify=skip_cert_verify,
        )
        return QbtStatus(
            configured=True,
            connected=True,
            url=resolved_url,
            version=_safe_str(client.app_version()) or None,
            web_api_version=_safe_str(client.app_web_api_version()) or None,
            torrent_count=client.torrents_count(),
        )
    except QbtError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise qbt_error_from_exception(exc, action='проверка подключения') from exc


def _extract_added_hash(result: Any) -> str:
    if isinstance(result, str):
        if result.strip().lower() == 'fails.':
            raise QbtError(
                'qbt_add_failed',
                'qBittorrent не принял раздачу.',
                status_code=502,
            )
        return ''

    if hasattr(result, 'get'):
        ids = result.get('added_torrent_ids') or []
        if isinstance(ids, str):
            return ids
        if ids:
            return _safe_str(ids[0])
    return ''


def _wait_for_torrent(client: qbittorrentapi.Client, info_hash: str):
    last_error: Exception | None = None
    for attempt in range(ADD_VERIFY_ATTEMPTS):
        try:
            items = client.torrents_info(torrent_hashes=info_hash)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
        else:
            if items:
                return items[0]
        if attempt < ADD_VERIFY_ATTEMPTS - 1:
            time.sleep(ADD_VERIFY_DELAY_SECONDS)

    if last_error is not None:
        raise qbt_error_from_exception(last_error, action='проверка добавленной раздачи') from last_error
    return None


def _resolve_source_url(
    metadata_comment: str,
    preferences: UserPreferences,
    torrent_id: int | None = None,
) -> str:
    comment = (metadata_comment or '').strip()
    if comment.startswith(('http://', 'https://')):
        return comment

    # Для вручную загруженного .torrent kinozal_id нет — ссылку не выдумываем.
    if torrent_id is None:
        return ''

    domain = (preferences.kinozal_domain or '').strip()
    if not domain:
        return ''
    return f'https://{domain}/details.php?id={torrent_id}'


def _save_archive(
    client: qbittorrentapi.Client,
    preferences: UserPreferences,
    info_hash: str,
    torrent_bytes: bytes,
) -> tuple[str, str | None]:
    configured_folder = (preferences.torrents_backup_folder or '').strip()
    if not configured_folder:
        return '', 'Папка backup для .torrent не настроена в Preferences → qBittorrent.'

    try:
        folder = resolve_backup_folder(configured_folder)
    except ValueError as exc:
        return '', f'Некорректная папка backup: {exc}'

    try:
        return write_torrent_archive(folder, info_hash, torrent_bytes), None
    except Exception as exc:  # noqa: BLE001
        logger.warning('Не удалось сохранить .torrent напрямую: %s', exc, exc_info=True)

    try:
        exported = client.torrents_export(torrent_hash=info_hash)
        return write_torrent_archive(folder, info_hash, exported), None
    except Exception as exc:  # noqa: BLE001
        logger.warning('Не удалось получить .torrent через torrents_export: %s', exc, exc_info=True)
        return '', f'Не удалось сохранить .torrent: {exc}'


def _add_event_payload(
    *,
    movie: Movie | None = None,
    kinozal_torrent_id: int | None = None,
    extra: dict | None = None,
) -> dict:
    payload: dict = {}
    if kinozal_torrent_id is not None:
        payload['torrent_id'] = kinozal_torrent_id
    if movie is not None:
        payload['movie_id'] = movie.id
    if extra:
        payload.update(extra)
    return payload


def _assert_movie_link_available(info_hash: str, movie: Movie | None) -> None:
    """Не даём перепривязать раздачу, которая уже принадлежит другому фильму."""
    if movie is None:
        return

    existing = Torrent.objects.filter(info_hash=info_hash).only('movie_id').first()
    if existing is not None and existing.movie_id is not None and existing.movie_id != movie.id:
        raise QbtError(
            'qbt_torrent_already_linked',
            'Раздача уже привязана к другому фильму Vault.',
            status_code=409,
        )


def _add_torrent(
    *,
    torrent_bytes: bytes,
    movie: Movie | None = None,
    source_url: str | None = None,
    tag: str | None = None,
    kinozal_torrent_id: int | None = None,
    source: str = 'kinozal',
) -> TorrentAddResult:
    """Общий пайплайн: qBittorrent -> архив .torrent -> запись Torrent."""
    preferences = _preferences()
    if not _configured_url(preferences):
        raise QbtError(
            'qbt_not_configured',
            'qBittorrent не настроен.',
            hint=QBT_SETUP_HINT,
            status_code=400,
        )

    try:
        metadata = parse_torrent_metadata(torrent_bytes)
    except TorrentMetadataError as exc:
        raise QbtError('qbt_invalid_torrent', str(exc), status_code=400) from exc

    _assert_movie_link_available(metadata.info_hash, movie)

    client = build_client(preferences=preferences)

    try:
        add_result = client.torrents_add(
            torrent_files=torrent_bytes,
            tags=(tag or 'mfp').strip() or 'mfp',
            is_sequential_download=True,
        )
    except qbittorrentapi.Conflict409Error:
        add_result = None
    except Exception as exc:  # noqa: BLE001
        _log_event(
            'torrent_add_failed',
            f'Не удалось добавить раздачу в qBittorrent: {exc}',
            level=TorrentEvent.Level.ERROR,
            movie=movie,
            payload=_add_event_payload(
                movie=movie,
                kinozal_torrent_id=kinozal_torrent_id,
                extra={'error_type': type(exc).__name__},
            ),
        )
        raise qbt_error_from_exception(exc, action='добавление раздачи') from exc

    info_hash = (_extract_added_hash(add_result) or metadata.info_hash).lower()
    if not info_hash:
        raise QbtError(
            'qbt_hash_missing',
            'Не удалось определить infohash раздачи.',
            status_code=502,
        )

    info = _wait_for_torrent(client, info_hash)
    if info is None and info_hash != metadata.info_hash:
        info = _wait_for_torrent(client, metadata.info_hash)
        if info is not None:
            info_hash = metadata.info_hash

    if info is None:
        _log_event(
            'torrent_add_not_confirmed',
            'qBittorrent принял запрос, но раздача не появилась в списке.',
            level=TorrentEvent.Level.ERROR,
            movie=movie,
            payload=_add_event_payload(
                movie=movie,
                kinozal_torrent_id=kinozal_torrent_id,
                extra={'info_hash': info_hash},
            ),
        )
        raise QbtError(
            'qbt_add_not_confirmed',
            'qBittorrent не подтвердил добавление раздачи.',
            hint='Проверь список раздач в qBittorrent. Возможно, сработала защита qBittorrent.',
            status_code=502,
        )

    qbt_hash = _safe_str(getattr(info, 'hash', '')).lower()
    if qbt_hash:
        info_hash = qbt_hash

    # qBittorrent мог вернуть другой hash (v2/hybrid) — проверяем привязку ещё раз.
    _assert_movie_link_available(info_hash, movie)

    name = _safe_str(getattr(info, 'name', '')) or metadata.name or info_hash
    save_path = _safe_str(getattr(info, 'save_path', ''))
    content_path = _safe_str(getattr(info, 'content_path', ''))
    resolved_source_url = (source_url or '').strip() or _resolve_source_url(
        metadata.comment,
        preferences,
        kinozal_torrent_id,
    )

    defaults = {
        'name': name,
        'save_path': save_path,
        'content_path': content_path,
        'last_error': '',
    }
    if resolved_source_url:
        defaults['source_url'] = resolved_source_url
    if movie is not None:
        defaults['movie'] = movie

    torrent, created = Torrent.objects.update_or_create(
        info_hash=info_hash,
        defaults=defaults,
    )

    archive_saved = False
    if (preferences.torrents_backup_folder or '').strip() and torrent.torrent_file:
        try:
            archive_saved = archive_exists(
                resolve_backup_folder(preferences.torrents_backup_folder or ''),
                torrent.torrent_file,
            )
        except (ValueError, OSError):
            archive_saved = False

    warning = None
    if not archive_saved:
        archive_path, warning = _save_archive(client, preferences, info_hash, torrent_bytes)
        if archive_path:
            torrent.torrent_file = archive_path
            torrent.last_error = ''
            archive_saved = True
        elif warning:
            torrent.last_error = warning
            _log_event(
                'torrent_archive_failed',
                warning,
                level=TorrentEvent.Level.WARNING,
                torrent=torrent,
                movie=movie,
                payload=_add_event_payload(
                    movie=movie,
                    kinozal_torrent_id=kinozal_torrent_id,
                    extra={'info_hash': info_hash},
                ),
            )
        torrent.save(update_fields=['torrent_file', 'last_error', 'updated_at'])

    _log_event(
        'torrent_uploaded' if source == 'manual' else 'torrent_added',
        f'Раздача добавлена в qBittorrent: {name}',
        torrent=torrent,
        movie=movie,
        payload=_add_event_payload(
            movie=movie,
            kinozal_torrent_id=kinozal_torrent_id,
            extra={
                'info_hash': info_hash,
                'archive_saved': archive_saved,
                'warning': warning,
                'source': source,
            },
        ),
    )

    return TorrentAddResult(
        torrent=torrent,
        created=created,
        archive_saved=archive_saved,
        warning=warning,
    )


def add_torrent_from_kinozal(
    *,
    torrent_bytes: bytes,
    torrent_id: int,
    source_url: str | None = None,
    tag: str | None = None,
) -> TorrentAddResult:
    """Раздача скачана с Kinozal: привязка к Vault выполняется отдельным импортом."""
    return _add_torrent(
        torrent_bytes=torrent_bytes,
        source_url=source_url,
        tag=tag,
        kinozal_torrent_id=torrent_id,
        source='kinozal',
    )


def add_torrent_from_file(
    *,
    torrent_bytes: bytes,
    movie: Movie,
    tag: str | None = None,
) -> TorrentAddResult:
    """Вручную загруженный .torrent сразу привязывается к фильму Vault."""
    return _add_torrent(
        torrent_bytes=torrent_bytes,
        movie=movie,
        tag=tag,
        source='manual',
    )


def link_torrent_to_movie(torrent_id: int, movie: Movie) -> bool:
    torrent = Torrent.objects.filter(pk=torrent_id).first()
    if torrent is None:
        return False

    if torrent.movie_id == movie.id:
        return True

    if torrent.movie_id is not None:
        _log_event(
            'torrent_link_conflict',
            'Раздача уже привязана к другому фильму Vault.',
            level=TorrentEvent.Level.WARNING,
            torrent=torrent,
            movie=movie,
            payload={'existing_movie_id': torrent.movie_id, 'new_movie_id': movie.id},
        )
        return False

    torrent.movie = movie
    torrent.save(update_fields=['movie', 'updated_at'])
    _log_event(
        'torrent_linked',
        f'Раздача привязана к фильму «{movie.title}».',
        torrent=torrent,
        movie=movie,
        payload={'info_hash': torrent.info_hash},
    )
    return True


def list_torrents(*, limit: int = 500, offset: int = 0) -> tuple[list[QbtTorrentRow], int]:
    preferences = _preferences()
    if not _configured_url(preferences):
        raise QbtError(
            'qbt_not_configured',
            'qBittorrent не настроен.',
            hint='Заполни URL, логин и пароль в Preferences → qBittorrent.',
            status_code=400,
        )

    client = build_client(preferences=preferences)
    try:
        total = client.torrents_count()
        items = client.torrents_info(
            sort='added_on',
            reverse=True,
            limit=limit,
            offset=offset,
        )
    except Exception as exc:  # noqa: BLE001
        raise qbt_error_from_exception(exc, action='получение списка раздач') from exc

    hashes = [_safe_str(getattr(item, 'hash', '')).lower() for item in items]
    hashes = [item for item in hashes if item]
    local_map = {
        torrent.info_hash: torrent
        for torrent in Torrent.objects.filter(info_hash__in=hashes).select_related('movie')
    }

    rows: list[QbtTorrentRow] = []
    for item in items:
        info_hash = _safe_str(getattr(item, 'hash', '')).lower()
        name = _safe_str(getattr(item, 'name', '')) or info_hash
        save_path = _safe_str(getattr(item, 'save_path', ''))
        content_path = _safe_str(getattr(item, 'content_path', ''))
        local_torrent = local_map.get(info_hash)

        if local_torrent is not None:
            update_fields: list[str] = []
            if name and local_torrent.name != name:
                local_torrent.name = name
                update_fields.append('name')
            if save_path and local_torrent.save_path != save_path:
                local_torrent.save_path = save_path
                update_fields.append('save_path')
            if content_path and local_torrent.content_path != content_path:
                local_torrent.content_path = content_path
                update_fields.append('content_path')
            if update_fields:
                local_torrent.save(update_fields=[*update_fields, 'updated_at'])

        rows.append(
            QbtTorrentRow(
                info_hash=info_hash,
                name=name,
                state=_safe_str(getattr(item, 'state', '')),
                progress=_safe_float(getattr(item, 'progress', 0.0)),
                size=_safe_int(getattr(item, 'size', 0)),
                total_size=_safe_int(getattr(item, 'total_size', 0)),
                dlspeed=_safe_int(getattr(item, 'dlspeed', 0)),
                upspeed=_safe_int(getattr(item, 'upspeed', 0)),
                eta=_safe_int(getattr(item, 'eta', 0)),
                category=_safe_str(getattr(item, 'category', '')),
                tags=_tags_list(getattr(item, 'tags', '')),
                save_path=save_path,
                content_path=content_path,
                added_on=_safe_optional_int(getattr(item, 'added_on', None)),
                completion_on=_safe_optional_int(getattr(item, 'completion_on', None)),
                torrent=local_torrent,
                linked_movie=local_torrent.movie if local_torrent else None,
            )
        )

    return rows, total


def get_progress(hashes: list[str]) -> tuple[bool, list[QbtProgressRow]]:
    """Best-effort прогресс для карточек Vault. Ошибки qbt не должны ломать Vault."""
    normalized = list(dict.fromkeys((value or '').strip().lower() for value in hashes if (value or '').strip()))
    if not normalized:
        return True, []

    preferences = _preferences()
    if not _configured_url(preferences):
        return False, []

    try:
        client = build_client(preferences=preferences)
        items = client.torrents_info(torrent_hashes=normalized[:200])
    except Exception as exc:  # noqa: BLE001
        logger.debug('Не удалось получить прогресс qBittorrent: %s', exc, exc_info=True)
        return False, []

    wanted = set(normalized)
    rows: list[QbtProgressRow] = []
    for item in items:
        info_hash = _safe_str(getattr(item, 'hash', '')).lower()
        if info_hash not in wanted:
            continue
        rows.append(
            QbtProgressRow(
                info_hash=info_hash,
                state=_safe_str(getattr(item, 'state', '')),
                progress=_safe_float(getattr(item, 'progress', 0.0)),
                dlspeed=_safe_int(getattr(item, 'dlspeed', 0)),
                upspeed=_safe_int(getattr(item, 'upspeed', 0)),
                eta=_safe_int(getattr(item, 'eta', 0)),
                size=_safe_int(getattr(item, 'size', 0)),
            )
        )

    return True, rows


def attach_torrent_to_movie(info_hash: str, movie: Movie) -> tuple[Torrent, str | None]:
    """Привязывает уже существующую в qBittorrent раздачу к фильму Vault."""
    normalized = (info_hash or '').strip().lower()
    if not normalized:
        raise QbtError('qbt_torrent_not_found', 'Не указан infohash раздачи.', status_code=400)

    preferences = _preferences()
    if not _configured_url(preferences):
        raise QbtError(
            'qbt_not_configured',
            'qBittorrent не настроен.',
            hint='Заполни URL, логин и пароль в Preferences → qBittorrent.',
            status_code=400,
        )

    client = build_client(preferences=preferences)
    try:
        items = client.torrents_info(torrent_hashes=normalized)
    except Exception as exc:  # noqa: BLE001
        raise qbt_error_from_exception(exc, action='поиск раздачи') from exc

    if not items:
        raise QbtError(
            'qbt_torrent_not_found',
            'Раздача не найдена в qBittorrent.',
            status_code=404,
        )

    info = items[0]
    qbt_hash = _safe_str(getattr(info, 'hash', '')).lower() or normalized
    existing = Torrent.objects.filter(info_hash=qbt_hash).first()

    if existing is not None and existing.movie_id is not None and existing.movie_id != movie.id:
        raise QbtError(
            'qbt_torrent_already_linked',
            'Раздача уже привязана к другому фильму Vault.',
            status_code=409,
        )

    source_url = ''
    try:
        properties = client.torrents_properties(torrent_hash=qbt_hash)
        comment = _safe_str(getattr(properties, 'comment', ''))
        # Любая http(s)-ссылка из comment — страница раздачи на трекере.
        if comment.startswith(('http://', 'https://')):
            source_url = comment
    except Exception:  # noqa: BLE001 - comment не обязателен
        logger.debug('Не удалось получить comment раздачи %s', qbt_hash, exc_info=True)

    name = _safe_str(getattr(info, 'name', '')) or qbt_hash
    save_path = _safe_str(getattr(info, 'save_path', ''))
    content_path = _safe_str(getattr(info, 'content_path', ''))

    configured_folder = (preferences.torrents_backup_folder or '').strip()
    archive_relative = existing.torrent_file if existing is not None else ''
    archive_saved = False
    warning: str | None = None

    if configured_folder and archive_relative:
        try:
            archive_saved = archive_exists(
                resolve_backup_folder(configured_folder),
                archive_relative,
            )
        except (ValueError, OSError):
            archive_saved = False

    if not archive_saved:
        if not configured_folder:
            warning = 'Папка backup для .torrent не настроена в Preferences → qBittorrent.'
        else:
            try:
                exported = client.torrents_export(torrent_hash=qbt_hash)
                archive_relative = write_torrent_archive(
                    resolve_backup_folder(configured_folder),
                    qbt_hash,
                    exported,
                )
                archive_saved = True
            except Exception as exc:  # noqa: BLE001
                warning = f'Не удалось сохранить .torrent: {exc}'
                logger.warning('Не удалось экспортировать .torrent для %s: %s', qbt_hash, exc, exc_info=True)

    defaults = {
        'name': name,
        'save_path': save_path,
        'content_path': content_path,
        'last_error': warning or '',
    }
    if source_url:
        defaults['source_url'] = source_url
    if archive_relative:
        defaults['torrent_file'] = archive_relative

    torrent, _created = Torrent.objects.update_or_create(
        info_hash=qbt_hash,
        defaults=defaults,
    )

    if torrent.movie_id is not None and torrent.movie_id != movie.id:
        raise QbtError(
            'qbt_torrent_already_linked',
            'Раздача уже привязана к другому фильму Vault.',
            status_code=409,
        )

    torrent.movie = movie
    torrent.save(update_fields=['movie', 'updated_at'])

    _log_event(
        'torrent_manual_linked',
        f'Раздача привязана к фильму «{movie.title}» вручную.',
        torrent=torrent,
        movie=movie,
        payload={'info_hash': torrent.info_hash, 'archive_saved': archive_saved},
    )

    return torrent, warning


def delete_torrent(
    torrent: Torrent,
    *,
    delete_files: bool = True,
    reason: str = 'manual',
) -> TorrentDeleteResult:
    """Удаляет раздачу из qBittorrent (вместе с файлами), архив .torrent и локальную запись.

    Если qBittorrent недоступен, локальная запись и архив сохраняются, чтобы удаление
    можно было повторить. Медиафайлы удаляет сам qBittorrent через delete_files=True.
    """
    info_hash = torrent.info_hash
    name = torrent.name
    movie = torrent.movie

    preferences = _preferences()
    qbt_deleted = False
    error: str | None = None

    if not _configured_url(preferences):
        error = 'qBittorrent не настроен: раздача и локальная запись не удалены.'
    else:
        try:
            client = build_client(preferences=preferences)
            client.torrents_delete(
                delete_files=delete_files,
                torrent_hashes=info_hash,
            )
            qbt_deleted = True
        except Exception as exc:  # noqa: BLE001
            mapped = qbt_error_from_exception(exc, action='удаление раздачи')
            error = mapped.message
            logger.warning(
                'Не удалось удалить раздачу %s из qBittorrent: %s',
                info_hash,
                exc,
                exc_info=True,
            )

    archive_deleted = False
    if qbt_deleted:
        configured_folder = (preferences.torrents_backup_folder or '').strip()
        if configured_folder and torrent.torrent_file:
            try:
                folder = resolve_backup_folder(configured_folder)
                if archive_exists(folder, torrent.torrent_file):
                    archive_deleted = delete_torrent_archive(folder, torrent.torrent_file)
                    if not archive_deleted:
                        error = (
                            'Раздача удалена, но архив .torrent удалить не удалось. '
                            'Проверь права на папку backup.'
                        )
            except (ValueError, OSError) as exc:
                error = f'Раздача удалена, но архив .torrent удалить не удалось: {exc}'
                logger.warning(
                    'Не удалось удалить архив .torrent для %s: %s',
                    info_hash,
                    exc,
                    exc_info=True,
                )

    record_deleted = False
    if qbt_deleted:
        torrent.delete()
        record_deleted = True
    elif error:
        torrent.last_error = error
        torrent.save(update_fields=['last_error', 'updated_at'])

    event_type = 'torrent_deleted' if record_deleted else 'torrent_delete_failed'
    level = TorrentEvent.Level.INFO if record_deleted else TorrentEvent.Level.ERROR
    if record_deleted and error:
        level = TorrentEvent.Level.WARNING

    _log_event(
        event_type,
        (
            f'Раздача удалена: {name}'
            if record_deleted
            else f'Не удалось удалить раздачу: {name}'
        ),
        level=level,
        torrent=None if record_deleted else torrent,
        movie=movie,
        payload={
            'info_hash': info_hash,
            'name': name,
            'delete_files': delete_files,
            'qbt_deleted': qbt_deleted,
            'archive_deleted': archive_deleted,
            'record_deleted': record_deleted,
            'reason': reason,
            'error': error,
        },
    )

    return TorrentDeleteResult(
        info_hash=info_hash,
        name=name,
        qbt_deleted=qbt_deleted,
        archive_deleted=archive_deleted,
        record_deleted=record_deleted,
        error=error,
    )


def delete_movie_torrents(
    movie: Movie,
    *,
    delete_files: bool = True,
    reason: str = 'watched',
) -> MovieTorrentsDeleteResult:
    """Удаляет все раздачи, привязанные к фильму Vault."""
    torrents = list(
        Torrent.objects.filter(movie=movie)
        .select_related('movie')
        .order_by('id')
    )
    results = [
        delete_torrent(torrent, delete_files=delete_files, reason=reason)
        for torrent in torrents
    ]
    errors = [
        f'{item.name}: {item.error}'
        for item in results
        if item.error
    ]
    return MovieTorrentsDeleteResult(results=results, errors=errors)
