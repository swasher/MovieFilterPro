"""Сервис мягкой связности Vault <-> Plex.

Связь не хранится как самостоятельная сущность: она вычисляется сравнением
GUID-идентификаторов Plex (tmdb/imdb/tvdb) с полями ``vault.Movie``. Таблица
``PlexLibraryItem`` — только кэш-зеркало библиотеки Plex для быстрого чтения
и для обратного направления (страница Plex -> Vault).

Создание связи происходит исключительно при синхронизации кэша. Отдельной
операции удаления нет: строки, исчезнувшие из Plex, вычищаются реконсиляцией,
а удаление фильма из Vault обнуляет FK через ``SET_NULL``.
"""

from __future__ import annotations

import logging
from pathlib import PurePath

from django.utils import timezone
from plexapi.server import PlexServer

from core.models import UserPreferences
from vault.models import Movie

from plex.models import PlexLinkState, PlexLibraryItem

logger = logging.getLogger(__name__)

# Кэш считается устаревшим через час, повторная попытка после ошибки — не раньше 5 минут.
PLEX_LINK_STALE_SECONDS = 3600
PLEX_LINK_RETRY_SECONDS = 300

SUPPORTED_SECTION_TYPES = {
    PlexLibraryItem.MediaType.MOVIE,
    PlexLibraryItem.MediaType.SHOW,
}

# Новые агенты отдают guid-ы как imdb://tt..., старые — как
# com.plexapp.agents.imdb://tt...?lang=en.
PROVIDER_ALIASES = {
    'imdb': 'imdb',
    'tmdb': 'tmdb',
    'themoviedb': 'tmdb',
    'tvdb': 'tvdb',
    'thetvdb': 'tvdb',
}
LEGACY_AGENT_PREFIX = 'com.plexapp.agents.'

# Поля, которые перезаписываются при повторной синхронизации существующей строки.
UPSERT_UPDATE_FIELDS = [
    'media_type',
    'section',
    'title',
    'original_title',
    'year',
    'file_path',
    'file_name',
    'guids',
    'guid_tmdb',
    'guid_imdb',
    'guid_tvdb',
    'vault_movie',
    'match_method',
    'last_seen_at',
    'updated_at',
]


# ------------------------------------ #
#           DOMAIN LAYER               #
# ------------------------------------ #

def _guid_text(value) -> str | None:
    """Достать строку GUID из plexapi-объекта или сырой строки.

    Важно брать ``.id`` у Guid-объекта: ``str()``/``repr()`` plexapi обрезает
    длинные legacy-идентификаторы до 20 символов.
    """
    if value is None:
        return None
    identifier = getattr(value, 'id', None)
    text = identifier if identifier is not None else str(value)
    text = (text or '').strip()
    if text.startswith('<Guid:') and text.endswith('>'):
        text = text[6:-1]
    return text or None


def _normalize_provider(provider: str) -> str:
    provider = (provider or '').strip().lower()
    if provider.startswith(LEGACY_AGENT_PREFIX):
        provider = provider[len(LEGACY_AGENT_PREFIX):]
    return PROVIDER_ALIASES.get(provider, provider)


def parse_guids(raw_guids) -> dict[str, str]:
    """Разобрать список GUID-ов Plex в словарь ``{provider: id}``.

    Берутся только imdb/tmdb/tvdb; внутренние ``plex://`` и прочие
    провайдеры игнорируются.
    """
    parsed: dict[str, str] = {}
    for raw in raw_guids or []:
        text = _guid_text(raw)
        if not text or '://' not in text:
            continue
        provider, _, identifier = text.partition('://')
        identifier = identifier.split('?', 1)[0].strip()
        provider = _normalize_provider(provider)
        if not identifier or provider not in {'imdb', 'tmdb', 'tvdb'}:
            continue
        if provider == 'imdb':
            identifier = identifier.lower()
        elif not identifier.isdigit():
            continue
        parsed.setdefault(provider, identifier)
    return parsed


def movie_is_series(movie: Movie) -> bool:
    """Серия ли фильм Vault. Первые три сигнала те же, что в vault.api._is_series_movie."""
    return movie.tmdb_media_type == Movie.TMDBMediaType.TV or movie.movie_type in (
        Movie.MovieType.SERIES,
        Movie.MovieType.MINISERIES,
    )


def _pick_single(candidates: list[Movie] | None) -> Movie | None:
    """Единственный кандидат или None (конфликт ID -> не линкуем автоматически)."""
    if not candidates:
        return None
    unique = {movie.id: movie for movie in candidates}
    if len(unique) != 1:
        return None
    return next(iter(unique.values()))


def build_match_indexes(movies):
    tmdb_index: dict[tuple[int, bool], list[Movie]] = {}
    imdb_index: dict[tuple[str, bool], list[Movie]] = {}
    tvdb_index: dict[int, list[Movie]] = {}

    for movie in movies:
        is_series = movie_is_series(movie)
        if movie.tmdb_id:
            tmdb_index.setdefault((int(movie.tmdb_id), is_series), []).append(movie)
        imdb_id = (movie.imdb_id or '').strip().lower()
        if imdb_id:
            imdb_index.setdefault((imdb_id, is_series), []).append(movie)
        if movie.tvdb_id and is_series:
            tvdb_index.setdefault(int(movie.tvdb_id), []).append(movie)

    return tmdb_index, imdb_index, tvdb_index


def match_item(item: dict, indexes) -> tuple[int | None, str]:
    """Найти vault-фильм для элемента Plex: (movie_id, match_method)."""
    tmdb_index, imdb_index, tvdb_index = indexes
    is_show = item['media_type'] == PlexLibraryItem.MediaType.SHOW
    guid_tmdb = item.get('guid_tmdb') or ''
    guid_imdb = (item.get('guid_imdb') or '').lower()
    guid_tvdb = item.get('guid_tvdb') or ''

    if is_show:
        # Для сериалов TVDB — самый устойчивый ключ, затем TMDB, затем IMDb.
        if guid_tvdb.isdigit():
            movie = _pick_single(tvdb_index.get(int(guid_tvdb)))
            if movie:
                return movie.id, 'tvdb'
        if guid_tmdb.isdigit():
            movie = _pick_single(tmdb_index.get((int(guid_tmdb), True)))
            if movie:
                return movie.id, 'tmdb'
        if guid_imdb:
            movie = _pick_single(imdb_index.get((guid_imdb, True)))
            if movie:
                return movie.id, 'imdb'
        return None, ''

    if guid_tmdb.isdigit():
        movie = _pick_single(tmdb_index.get((int(guid_tmdb), False)))
        if movie:
            return movie.id, 'tmdb'
    if guid_imdb:
        movie = _pick_single(imdb_index.get((guid_imdb, False)))
        if movie:
            return movie.id, 'imdb'
    return None, ''


def _extract_file_info(item) -> tuple[str, str]:
    media_list = getattr(item, 'media', None) or []
    for media in media_list:
        for part in getattr(media, 'parts', None) or []:
            file_path = getattr(part, 'file', None)
            if file_path:
                return file_path, PurePath(file_path).name
    return '', ''


def extract_item_snapshot(item, media_type: str, section_title: str) -> dict:
    """Привести элемент plexapi к плоскому словарю для кэша."""
    guids = [text for text in (_guid_text(raw) for raw in getattr(item, 'guids', None) or []) if text]
    parsed = parse_guids(guids)
    file_path, file_name = _extract_file_info(item) if media_type == PlexLibraryItem.MediaType.MOVIE else ('', '')

    return {
        'rating_key': str(getattr(item, 'ratingKey', '') or ''),
        'media_type': media_type,
        'section': section_title or '',
        'title': getattr(item, 'title', '') or '',
        'original_title': getattr(item, 'originalTitle', '') or '',
        'year': getattr(item, 'year', None),
        'file_path': file_path,
        'file_name': file_name,
        'guids': guids,
        'guid_tmdb': parsed.get('tmdb', ''),
        'guid_imdb': parsed.get('imdb', ''),
        'guid_tvdb': parsed.get('tvdb', ''),
    }


def fetch_library_snapshot(server: PlexServer) -> list[dict]:
    """Снять снапшот movie/show-секций Plex (music/photo пропускаются)."""
    snapshot: list[dict] = []
    for section in server.library.sections():
        section_type = (getattr(section, 'type', '') or '').lower()
        if section_type not in SUPPORTED_SECTION_TYPES:
            continue
        section_title = getattr(section, 'title', '') or ''
        for item in section.all():
            entry = extract_item_snapshot(item, section_type, section_title)
            if not entry['rating_key']:
                continue
            snapshot.append(entry)
    return snapshot


# ------------------------------------ #
#          APPLICATION LAYER           #
# ------------------------------------ #

class PlexLinkSyncService:
    """Синхронизация кэша Plex и проверка его свежести."""

    @classmethod
    def is_configured(cls) -> bool:
        prefs = UserPreferences.get()
        return bool(prefs.plex_address and prefs.plex_token)

    @classmethod
    def is_stale(cls) -> bool:
        state = PlexLinkState.get()
        if state.last_synced_at is None:
            return True
        return (timezone.now() - state.last_synced_at).total_seconds() >= PLEX_LINK_STALE_SECONDS

    @classmethod
    def ensure_fresh_async(cls) -> bool:
        """Поставить фоновую синхронизацию, если кэш протух.

        Возвращает True, если задача была поставлена. Повторная постановка
        ограничена PLEX_LINK_RETRY_SECONDS, чтобы недоступный Plex не
        спамил очередь задач на каждый запрос.
        """
        if not cls.is_configured():
            return False

        state = PlexLinkState.get()
        now = timezone.now()
        if state.is_syncing:
            return False
        if (
            state.last_synced_at is not None
            and (now - state.last_synced_at).total_seconds() < PLEX_LINK_STALE_SECONDS
        ):
            return False
        if (
            state.last_attempt_at is not None
            and (now - state.last_attempt_at).total_seconds() < PLEX_LINK_RETRY_SECONDS
        ):
            return False

        # Отмечаем попытку заранее: если HUEY-воркер лежит, очередь не растёт.
        PlexLinkState.objects.filter(pk=state.pk).update(last_attempt_at=now)

        from plex.tasks import sync_plex_link

        sync_plex_link()
        return True

    @classmethod
    def sync(cls) -> PlexLinkState:
        """Пересобрать кэш Plex. Ошибка соединения не трогает старый кэш."""
        state = PlexLinkState.get()
        if state.is_syncing:
            return state

        now = timezone.now()
        state.is_syncing = True
        state.last_attempt_at = now
        state.save(update_fields=['is_syncing', 'last_attempt_at', 'updated_at'])

        try:
            if not cls.is_configured():
                return cls._reset_not_configured(state)

            server = cls._connect()
            snapshot = fetch_library_snapshot(server)
            cls._persist_snapshot(snapshot, synced_at=now)

            matched_total = sum(1 for row in snapshot if row.get('vault_movie_id'))
            state.items_total = len(snapshot)
            state.matched_total = matched_total
            state.unmatched_total = len(snapshot) - matched_total
            state.last_synced_at = now
            state.last_error = ''
            state.is_syncing = False
            state.save(update_fields=[
                'items_total', 'matched_total', 'unmatched_total',
                'last_synced_at', 'last_error', 'is_syncing', 'updated_at',
            ])
            return state
        except Exception as exc:  # noqa: BLE001 — статус важнее типа исключения
            logger.exception('Plex link sync failed')
            state.is_syncing = False
            state.last_error = f'{type(exc).__name__}: {exc}'[:2000]
            state.save(update_fields=['is_syncing', 'last_error', 'updated_at'])
            return state

    # ------------------------------------------------------------------ #

    @classmethod
    def _connect(cls) -> PlexServer:
        prefs = UserPreferences.get()
        return PlexServer(prefs.plex_address, prefs.plex_token)

    @classmethod
    def _reset_not_configured(cls, state: PlexLinkState) -> PlexLinkState:
        PlexLibraryItem.objects.all().delete()
        state.items_total = 0
        state.matched_total = 0
        state.unmatched_total = 0
        state.last_synced_at = None
        state.last_error = ''
        state.is_syncing = False
        state.save(update_fields=[
            'items_total', 'matched_total', 'unmatched_total',
            'last_synced_at', 'last_error', 'is_syncing', 'updated_at',
        ])
        return state

    @classmethod
    def _persist_snapshot(cls, snapshot: list[dict], *, synced_at) -> None:
        movies = list(Movie.objects.only(
            'id', 'tmdb_id', 'tmdb_media_type', 'imdb_id', 'tvdb_id', 'movie_type',
        ))
        indexes = build_match_indexes(movies)

        rows: list[PlexLibraryItem] = []
        for item in snapshot:
            movie_id, method = match_item(item, indexes)
            item['vault_movie_id'] = movie_id
            rows.append(PlexLibraryItem(
                rating_key=item['rating_key'],
                media_type=item['media_type'],
                section=item['section'],
                title=item['title'],
                original_title=item['original_title'],
                year=item['year'],
                file_path=item['file_path'],
                file_name=item['file_name'],
                guids=item['guids'],
                guid_tmdb=item['guid_tmdb'],
                guid_imdb=item['guid_imdb'],
                guid_tvdb=item['guid_tvdb'],
                vault_movie_id=movie_id,
                match_method=method,
                last_seen_at=synced_at,
            ))

        PlexLibraryItem.objects.bulk_create(
            rows,
            update_conflicts=True,
            update_fields=UPSERT_UPDATE_FIELDS,
            unique_fields=['rating_key'],
            batch_size=500,
        )
        # Реконсиляция: всё, что не встретилось в этом снапшоте, из Plex исчезло.
        PlexLibraryItem.objects.filter(last_seen_at__lt=synced_at).delete()
