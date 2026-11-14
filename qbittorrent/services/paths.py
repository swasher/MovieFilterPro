from __future__ import annotations

import os
import re
from pathlib import Path
from uuid import uuid4

INFO_HASH_RE = re.compile(r'^[a-f0-9]{40,64}$')

_INVALID_FILENAME_CHARS_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def resolve_configured_path(configured: str) -> Path:
    raw_path = (configured or '').strip()
    if not raw_path:
        raise ValueError('Путь не задан.')

    expanded_path = os.path.expandvars(os.path.expanduser(raw_path))

    if os.name == 'nt' and expanded_path.startswith('/') and not expanded_path.startswith('//'):
        current_dir = Path.cwd()
        drive_root = Path(current_dir.anchor or f'{current_dir.drive}\\')
        windows_relative_path = expanded_path.lstrip('/').replace('/', os.sep)
        return drive_root / windows_relative_path

    return Path(expanded_path)


def resolve_backup_folder(configured: str) -> Path:
    return resolve_configured_path(configured)


def ensure_backup_folder(folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    if not folder.is_dir():
        raise ValueError(f'Путь не является папкой: {folder}')
    if not os.access(folder, os.W_OK):
        raise ValueError(f'Нет прав на запись в папку: {folder}')
    return folder


def _sanitize_archive_base(name: str | None, info_hash: str) -> str:
    """Приводит произвольное имя к безопасному базовому имени файла .torrent."""
    raw = (name or '').strip()
    if raw.lower().endswith('.torrent'):
        raw = raw[:-len('.torrent')].rstrip()

    if not raw:
        raw = info_hash

    cleaned = _INVALID_FILENAME_CHARS_RE.sub('_', raw)
    cleaned = cleaned.strip(' .')
    if not cleaned:
        cleaned = info_hash

    # Ограничиваем длину, чтобы не упереться в лимиты файловой системы.
    if len(cleaned) > 180:
        cleaned = cleaned[:180].rstrip(' .')
        if not cleaned:
            cleaned = info_hash

    return cleaned


def _movie_archive_name(movie: object | None) -> str | None:
    if movie is None:
        return None
    title = getattr(movie, 'title', None)
    if not title:
        return None
    year = getattr(movie, 'year', None)
    if year:
        return f'{title} ({year})'
    return str(title)


def archive_name_for(
    info_hash: str,
    *,
    archive_name: str | None = None,
    name: str | None = None,
    filename: str | None = None,
    original_name: str | None = None,
    original_filename: str | None = None,
    movie: object | None = None,
) -> str:
    """Вычисляет итоговое базовое имя (без расширения) для архива .torrent.

    Приоритет: явно переданное имя → фильм → оригинальное имя файла → infohash.
    """
    resolved_movie_name = _movie_archive_name(movie)
    base = (
        archive_name
        or name
        or filename
        or original_name
        or original_filename
        or resolved_movie_name
    )
    return _sanitize_archive_base(base, info_hash)


def archive_relpath(
    info_hash: str,
    archive_name: str | None = None,
    *,
    name: str | None = None,
    filename: str | None = None,
    original_name: str | None = None,
    original_filename: str | None = None,
    movie: object | None = None,
) -> str:
    normalized = (info_hash or '').strip().lower()
    if not INFO_HASH_RE.fullmatch(normalized):
        # Если infohash некорректен, используем его как есть только для fallback-имени.
        normalized = (info_hash or '').strip() or 'torrent'

    base = archive_name_for(
        normalized,
        archive_name=archive_name,
        name=name,
        filename=filename,
        original_name=original_name,
        original_filename=original_filename,
        movie=movie,
    )
    # Если явное имя не передано и нет фильма/оригинального имени — сохраняем
    # историческое поведение: файл называется по infohash.
    if (
        archive_name is None
        and name is None
        and filename is None
        and original_name is None
        and original_filename is None
        and movie is None
    ):
        base = normalized

    return f'{base}.torrent'


def write_torrent_archive(
    folder: Path,
    info_hash: str,
    data: bytes,
    archive_name: str | None = None,
    *,
    name: str | None = None,
    filename: str | None = None,
    original_name: str | None = None,
    original_filename: str | None = None,
    movie: object | None = None,
) -> str:
    ensure_backup_folder(folder)
    relative_path = archive_relpath(
        info_hash,
        archive_name=archive_name,
        name=name,
        filename=filename,
        original_name=original_name,
        original_filename=original_filename,
        movie=movie,
    )

    target = folder / relative_path
    # Избегаем перезаписи чужого архива при совпадении имён: добавляем короткий hash.
    if target.exists() and relative_path.lower() != f'{info_hash.lower()}.torrent':
        stem = Path(relative_path).stem
        suffix = Path(relative_path).suffix or '.torrent'
        candidate = f'{stem} ({str(info_hash)[:8]}){suffix}'
        if not (folder / candidate).exists():
            relative_path = candidate
            target = folder / relative_path
        else:
            relative_path = f'{str(info_hash).lower()}.torrent'
            target = folder / relative_path

    temp_path = folder / f'.{uuid4().hex}.tmp'

    try:
        temp_path.write_bytes(data)
        os.replace(temp_path, target)
    finally:
        temp_path.unlink(missing_ok=True)

    try:
        os.chmod(target, 0o600)
    except OSError:
        pass

    return relative_path


def resolve_archive_file(folder: Path, relative_path: str) -> Path:
    if not relative_path:
        raise ValueError('Путь к torrent-файлу не задан.')
    folder_resolved = folder.resolve()
    target = (folder / relative_path).resolve()
    if not target.is_relative_to(folder_resolved):
        raise ValueError('Путь к torrent-файлу выходит за пределы папки backup.')
    return target


def archive_exists(folder: Path, relative_path: str) -> bool:
    if not relative_path:
        return False
    try:
        return resolve_archive_file(folder, relative_path).is_file()
    except ValueError:
        return False


def delete_torrent_archive(folder: Path, relative_path: str) -> bool:
    if not relative_path:
        return False
    try:
        target = resolve_archive_file(folder, relative_path)
    except ValueError:
        return False
    if not target.is_file():
        return False
    target.unlink()
    return True
