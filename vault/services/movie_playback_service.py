"""Запуск фильма во внешнем плеере (VLC) через кастомный протокол ``mfp://``.

Схема целиком:

    браузер  →  mfp://<slug>?t=<token>
             →  mfp-play.ps1 (Windows, обработчик протокола mfp)
             →  GET /api/vault/playback-target/<slug>?t=<token>
             →  {"unc_path": "\\\\qnap\\Movies\\...mkv"}
             →  vlc.exe "\\\\qnap\\Movies\\...mkv"

Сервер не отдаёт байты фильма: VLC читает файл с сетевой шары сам, поэтому
кодеки и перемотка ограничены только возможностями VLC, а backend не тратит
CPU на стриминг. Сервер лишь переводит путь «как его видит Plex» во UNC-путь
«как его видит Windows-клиент» и выдаёт короткоживущий подписанный токен.

Обработчик протокола и установочный .reg лежат в каталоге ``player/``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import PureWindowsPath
from urllib.parse import quote

from django.core import signing

from core.models import UserPreferences
from plex.models import PlexLibraryItem

logger = logging.getLogger("vault.playback")

# Схема запуска. Должна совпадать с ключом в HKCU\Software\Classes (player/play.reg).
LAUNCH_SCHEME = "mfp"

# Подпись токена запуска. Токен живёт ограниченно: страница фильма может быть
# открыта долго, но вечная ссылка на файл не нужна.
TOKEN_SALT = "vault.playback.launch"
TOKEN_MAX_AGE_SECONDS = 12 * 60 * 60

# Причины, по которым запуск невозможен. Тексты идут прямо в UI.
REASON_DISABLED = "Кнопка «Смотреть» выключена в Preferences → Плеер."
REASON_NOT_IN_PLEX = "Фильма нет в Plex: неизвестен путь к файлу."
REASON_NO_PATH_RULES = "Не настроен маппинг путей Plex → UNC (Preferences → Плеер)."


# ------------------------------------ #
#            DOMAIN LAYER              #
# ------------------------------------ #


@dataclass(frozen=True)
class PathRule:
    """Правило перевода префикса пути Plex в префикс UNC-пути."""

    source: str  # '/share/Movies'
    target: str  # '\\\\qnap\\Movies'


@dataclass(frozen=True)
class PlaybackTarget:
    """Файл, который можно отдать внешнему плееру."""

    source_path: str  # путь как его видит Plex
    unc_path: str  # путь как его видит Windows-клиент
    file_name: str


@dataclass(frozen=True)
class PlaybackResolution:
    target: PlaybackTarget | None
    reason: str | None = None

    @property
    def available(self) -> bool:
        return self.target is not None


def _normalize_prefix(value: str) -> str:
    return value.strip().replace("\\", "/").rstrip("/")


def parse_path_rules(raw: str) -> list[PathRule]:
    """Разбирает многострочный список правил ``<plex_prefix> => <unc_prefix>``.

    Пустые строки и строки с ``#`` игнорируются. Правила сортируются по убыванию
    длины префикса, чтобы самое конкретное совпадение выигрывало независимо от
    порядка строк в настройках.
    """

    rules: list[PathRule] = []
    for line in (raw or "").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        source, separator, target = stripped.partition("=>")
        if not separator:
            continue
        normalized_source = _normalize_prefix(source)
        normalized_target = target.strip().rstrip("\\/")
        if not normalized_source or not normalized_target:
            continue
        rules.append(PathRule(source=normalized_source, target=normalized_target))

    rules.sort(key=lambda rule: len(rule.source), reverse=True)
    return rules


def map_path(path: str, rules: list[PathRule]) -> str | None:
    """Переводит путь Plex в UNC-путь по самому длинному совпавшему префиксу.

    Возвращает ``None``, если правило не найдено или путь указывает на каталог
    (например, папка сезона), а не на файл.
    """

    normalized = (path or "").strip().replace("\\", "/")
    if not normalized:
        return None

    for rule in rules:
        if normalized == rule.source:
            continue
        if not normalized.startswith(rule.source + "/"):
            continue
        tail = normalized[len(rule.source):].lstrip("/")
        if not tail:
            continue
        return "\\".join([rule.target, *tail.split("/")])

    return None


def sign_launch_token(slug: str) -> str:
    return signing.TimestampSigner(salt=TOKEN_SALT).sign(slug)


def read_launch_token(token: str, *, max_age: int = TOKEN_MAX_AGE_SECONDS) -> str | None:
    """Возвращает slug из токена или ``None``, если токен битый/просрочен."""

    if not token:
        return None
    try:
        return signing.TimestampSigner(salt=TOKEN_SALT).unsign(token, max_age=max_age)
    except (signing.BadSignature, signing.SignatureExpired):
        return None


# ------------------------------------ #
#          APPLICATION LAYER           #
# ------------------------------------ #


class MoviePlaybackService:
    """Определяет, что и как запустить во внешнем плеере для фильма Vault."""

    @classmethod
    def resolve(cls, movie, preferences: UserPreferences | None = None) -> PlaybackResolution:
        preferences = preferences or UserPreferences.get()

        if not preferences.player_enabled:
            return PlaybackResolution(None, REASON_DISABLED)

        rules = parse_path_rules(preferences.player_path_map)
        if not rules:
            return PlaybackResolution(None, REASON_NO_PATH_RULES)

        links = list(
            PlexLibraryItem.objects.filter(vault_movie=movie)
            .exclude(file_path="")
            .exclude(media_type=PlexLibraryItem.MediaType.SHOW)
            .order_by("section", "rating_key")
        )
        if not links:
            return PlaybackResolution(None, REASON_NOT_IN_PLEX)

        for link in links:
            unc_path = map_path(link.file_path, rules)
            if not unc_path:
                continue
            file_name = link.file_name or PureWindowsPath(unc_path).name
            return PlaybackResolution(
                PlaybackTarget(
                    source_path=link.file_path,
                    unc_path=unc_path,
                    file_name=file_name,
                )
            )

        return PlaybackResolution(
            None,
            f"Нет правила маппинга для пути {links[0].file_path}.",
        )

    @classmethod
    def build_launch_url(cls, slug: str) -> str:
        """Ссылка для браузера: её открытие передаёт управление обработчику протокола."""

        return f"{LAUNCH_SCHEME}://{slug}?t={quote(sign_launch_token(slug), safe='')}"

    @classmethod
    def resolve_launch(cls, slug: str, token: str):
        """Проверяет токен запуска (вызывается из обработчика протокола, без сессии).

        Возвращает пару ``(movie, resolution)``. Бросает ``PermissionError`` при
        битом/просроченном токене и ``LookupError``, если фильма нет.
        """

        token_slug = read_launch_token(token)
        if token_slug is None or token_slug != slug:
            raise PermissionError("invalid_launch_token")

        from vault.models import Movie

        movie = Movie.objects.filter(slug=slug).first()
        if movie is None:
            raise LookupError("movie_not_found")

        resolution = cls.resolve(movie)
        if resolution.target is None:
            logger.info("Playback unavailable for %s: %s", slug, resolution.reason)
        return movie, resolution
