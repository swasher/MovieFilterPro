from __future__ import annotations

from dataclasses import dataclass

from requests import RequestException

from moviefilter.hotfolder import resolve_torrents_hotfolder_path
from moviefilter.kinozal import KinozalClient
from moviefilter.models import UserPreferences


@dataclass(slots=True, frozen=True)
class TorrentDownloadResult:
    torrent_id: int
    filename: str
    saved_to: str
    message: str


class TorrentDownloadError(Exception):
    def __init__(self, code: str, message: str, *, hint: str | None = None, status_code: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint
        self.status_code = status_code


def validate_download_preferences() -> UserPreferences:
    preferences = UserPreferences.get()

    if not (preferences.kinozal_domain or "").strip():
        raise TorrentDownloadError(
            "settings_missing_domain",
            "Не указан домен Kinozal.",
            hint="Открой Preferences и заполни `kinozal_domain`.",
        )

    if not (preferences.cookie_uid or "").strip() or not (preferences.cookie_pass or "").strip():
        raise TorrentDownloadError(
            "settings_missing_auth",
            "Не настроены cookies для авторизации на Kinozal.",
            hint="Открой Preferences и заполни `cookie_uid` и `cookie_pass`.",
        )

    if not (preferences.torrents_hotfolder or "").strip():
        raise TorrentDownloadError(
            "settings_missing_hotfolder",
            "Не настроен hotfolder для torrent-файлов.",
            hint="Укажи рабочий путь в `torrents_hotfolder`.",
        )

    return preferences


def download_torrent_file(torrent_id: int, *, preferences: UserPreferences | None = None) -> TorrentDownloadResult:
    preferences = preferences or validate_download_preferences()
    client = KinozalClient()
    configured_destination = preferences.torrents_hotfolder or ""
    resolved_destination = resolve_torrents_hotfolder_path(configured_destination)

    try:
        response = client.download_torrent(torrent_id)
    except RequestException as exc:
        raise TorrentDownloadError(
            "kinozal_unreachable",
            "Не удалось связаться с Kinozal при скачивании torrent-файла.",
            hint=str(exc),
            status_code=502,
        ) from exc

    out_of_torrent_number_message = "Вам недоступен торрент-файл для скачивания"

    if response.headers.get("Content-Type") != "application/x-bittorrent":
        body = response.content.decode("windows-1251", errors="ignore")
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

    if response.status_code != 200:
        raise TorrentDownloadError(
            "bad_kinozal_response",
            f"Kinozal вернул неожиданный статус: {response.status_code}.",
            status_code=502,
        )

    try:
        filename = response.headers["content-disposition"].split("=")[1].strip('"')
    except (KeyError, IndexError) as exc:
        raise TorrentDownloadError(
            "missing_torrent_filename",
            "Не удалось определить имя torrent-файла из ответа Kinozal.",
            status_code=502,
        ) from exc

    try:
        resolved_destination.mkdir(parents=True, exist_ok=True)
        full_path = resolved_destination / filename
        with open(full_path, "wb") as file:
            file.write(response.content)
    except (FileNotFoundError, OSError) as exc:
        raise TorrentDownloadError(
            "hotfolder_write_failed",
            "Не удалось записать torrent-файл в hotfolder.",
            hint=f"Настройка: {configured_destination}. Реальный путь: {resolved_destination}. {exc}",
            status_code=400,
        ) from exc

    return TorrentDownloadResult(
        torrent_id=torrent_id,
        filename=filename,
        saved_to=str(full_path),
        message=f"Torrent сохранен: {full_path}",
    )
