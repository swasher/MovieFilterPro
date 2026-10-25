from __future__ import annotations

import os
import re
from pathlib import Path
from uuid import uuid4

INFO_HASH_RE = re.compile(r'^[a-f0-9]{40,64}$')


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


def archive_relpath(info_hash: str) -> str:
    normalized = (info_hash or '').strip().lower()
    if not INFO_HASH_RE.fullmatch(normalized):
        raise ValueError('Некорректный infohash для имени torrent-файла.')
    return f'{normalized}.torrent'


def write_torrent_archive(folder: Path, info_hash: str, data: bytes) -> str:
    ensure_backup_folder(folder)
    relative_path = archive_relpath(info_hash)
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
