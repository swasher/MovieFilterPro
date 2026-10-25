from __future__ import annotations

import re
from dataclasses import dataclass

from requests import RequestException

from moviefilter.kinozal import KinozalClient
from moviefilter.models import UserPreferences


@dataclass(slots=True, frozen=True)
class TorrentFile:
    torrent_id: int
    filename: str
    content: bytes


class TorrentDownloadError(Exception):
    def __init__(self, code: str, message: str, *, hint: str | None = None, status_code: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint
        self.status_code = status_code


def validate_kinozal_preferences() -> UserPreferences:
    preferences = UserPreferences.get()

    if not (preferences.kinozal_domain or "").strip():
        raise TorrentDownloadError(
            "settings_missing_domain",
            "Не указан домен Kinozal.",
            hint="Открой Preferences и добавь зеркало в «Зеркала kinozal».",
        )

    if not (preferences.cookie_uid or "").strip() or not (preferences.cookie_pass or "").strip():
        raise TorrentDownloadError(
            "settings_missing_auth",
            "Не настроены cookies для авторизации на Kinozal.",
            hint="Открой Preferences и заполни `cookie_uid` и `cookie_pass`.",
        )

    return preferences


def _extract_filename(header_value: str, torrent_id: int) -> str:
    match = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)"?', header_value or "", re.IGNORECASE)
    raw_name = match.group(1).strip() if match else ""
    # Имя используется только для отображения; путь в архив строится по infohash.
    raw_name = raw_name.replace("\\", "/").split("/")[-1].strip()
    return raw_name or f"id{torrent_id}.torrent"


def fetch_torrent_file(torrent_id: int, *, preferences: UserPreferences | None = None) -> TorrentFile:
    preferences = preferences or validate_kinozal_preferences()
    client = KinozalClient()

    try:
        response = client.download_torrent(torrent_id)
    except RequestException as exc:
        raise TorrentDownloadError(
            "kinozal_unreachable",
            "Не удалось связаться с Kinozal при скачивании torrent-файла.",
            hint=str(exc),
            status_code=502,
        ) from exc

    if response.status_code != 200:
        raise TorrentDownloadError(
            "bad_kinozal_response",
            f"Kinozal вернул неожиданный статус: {response.status_code}.",
            status_code=502,
        )

    content = response.content or b""
    if not content.lstrip().startswith(b"d"):
        body = content.decode("windows-1251", errors="ignore")
        out_of_torrent_number_message = "Вам недоступен торрент-файл для скачивания"
        if out_of_torrent_number_message in body:
            raise TorrentDownloadError(
                "download_limit_reached",
                "Kinozal сообщил, что дневной лимит скачиваний исчерпан.",
                status_code=409,
            )
        raise TorrentDownloadError(
            "invalid_torrent_response",
            "Kinozal вернул HTML вместо torrent-файла.",
            status_code=502,
        )

    filename = _extract_filename(response.headers.get("content-disposition", ""), torrent_id)
    return TorrentFile(
        torrent_id=torrent_id,
        filename=filename,
        content=content,
    )
