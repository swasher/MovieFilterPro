from __future__ import annotations

import hashlib
from dataclasses import dataclass

import bencodepy


class TorrentMetadataError(Exception):
    """Не удалось разобрать .torrent-файл."""


@dataclass(slots=True, frozen=True)
class TorrentMetadata:
    info_hash: str
    name: str
    comment: str


def _decode_text(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode('utf-8', errors='replace').strip()
    if isinstance(value, str):
        return value.strip()
    return ''


def parse_torrent_metadata(data: bytes) -> TorrentMetadata:
    """Извлекает v1 infohash, имя и comment из .torrent-файла."""
    if not data:
        raise TorrentMetadataError('Пустой torrent-файл.')

    try:
        meta = bencodepy.decode(data)
    except Exception as exc:  # noqa: BLE001 - bencodepy имеет разные типы ошибок
        raise TorrentMetadataError('Не удалось разобрать torrent-файл.') from exc

    if not isinstance(meta, dict):
        raise TorrentMetadataError('Torrent-файл имеет неверную структуру.')

    info = meta.get(b'info')
    if not isinstance(info, dict):
        raise TorrentMetadataError('В torrent-файле отсутствует info-секция.')

    try:
        info_hash = hashlib.sha1(bencodepy.encode(info)).hexdigest()
    except Exception as exc:  # noqa: BLE001
        raise TorrentMetadataError('Не удалось вычислить infohash torrent-файла.') from exc

    name = _decode_text(info.get(b'name') or info.get(b'name.utf-8'))
    comment = _decode_text(meta.get(b'comment'))

    return TorrentMetadata(
        info_hash=info_hash,
        name=name,
        comment=comment,
    )
