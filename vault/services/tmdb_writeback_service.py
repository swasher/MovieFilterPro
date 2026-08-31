from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import timedelta
from typing import Optional

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from vault.constants import SKIP_LIST_NAME as _SKIP_LIST_NAME

logger = logging.getLogger("vault.tmdb_writeback")

# ------------------------------------ #
#          APPLICATION LAYER           #
# ------------------------------------ #


@dataclass
class WritebackResult:
    success: bool
    action: str  # watchlist_add, watchlist_remove, favorite_add, favorite_remove, rate, unrate, list_add, ...
    tmdb_id: Optional[int] = None
    media_type: Optional[str] = None
    error: Optional[str] = None
    retry_after: Optional[int] = None


class TmdbWritebackService:
    """Сервис обратной записи данных Vault в TMDB. Инфраструктура — через tmdb_adapter."""

    # Локальный системный зеркальный список "Не интересует" зеркально
    # синхронизируется в TMDB-лист с таким же именем.
    SKIP_LIST_NAME = _SKIP_LIST_NAME

    # Процесс-лок для сериализации _ensure_skip_list_tmdb_id.
    # На sqlite select_for_update — no-op, поэтому дополнительно используем
    # threading.Lock (по образцу tmdb_adapter/client_singleton.py).
    _skip_list_lock = threading.Lock()

    # --- error classification ---

    @staticmethod
    def _is_rate_limited(exc: Exception) -> bool:
        msg = str(exc)
        name = type(exc).__name__
        # tmdbapis raises TMDbException with "(429 ...)" for rate limit
        return "429" in msg or "429" in name or "Rate limit" in msg

    @staticmethod
    def _is_auth_error(exc: Exception) -> bool:
        msg = str(exc)
        name = type(exc).__name__
        return (
            "401" in msg
            or name in ("Authentication", "Unauthorized", "WritePermission")
            or "Invalid API key" in msg
            or "Authentication" in msg
        )

    # --- persistent queue (forever) ---

    @classmethod
    def _upsert_queue_item(cls, movie, error: str, *, is_auth: bool = False):
        """Создать/обновить запись forever-очереди. Auth → next_retry=None."""
        try:
            from vault.models import TMDBWritebackQueueItem

            now = timezone.now()
            next_retry = None if is_auth else now + timedelta(minutes=10)
            state = TMDBWritebackQueueItem.State.ERROR if is_auth else TMDBWritebackQueueItem.State.PENDING
            # need movie_id for snap support
            movie_id = getattr(movie, "id", None) or getattr(movie, "pk", None)
            if not movie_id:
                return None
            obj, created = TMDBWritebackQueueItem.objects.update_or_create(
                movie_id=movie_id,
                defaults={
                    "state": state,
                    "last_error": (error or "")[:2000],
                    "next_retry_at": next_retry,
                },
            )
            # Атомарный инкремент через F() — не теряем попытки при конкурентных
            # вызовах (два periodic tick'а, rapid-fire сигналы и т.п.).
            TMDBWritebackQueueItem.objects.filter(pk=obj.pk).update(attempts=F("attempts") + 1)
            logger.warning("writeback queue upsert movie=%s state=%s next_retry=%s err=%s", movie_id, state, next_retry, error[:200])
            return obj
        except Exception as exc:
            logger.exception("writeback queue upsert failed movie=%s: %s", getattr(movie, "id", "?"), exc)
            return None

    @classmethod
    def _clear_queue_item(cls, movie):
        try:
            from vault.models import TMDBWritebackQueueItem

            movie_id = getattr(movie, "id", None) or getattr(movie, "pk", None)
            if not movie_id:
                return
            deleted, _ = TMDBWritebackQueueItem.objects.filter(movie_id=movie_id).delete()
            if deleted:
                logger.info("writeback queue cleared movie=%s", movie_id)
        except Exception as exc:
            logger.warning("writeback queue clear failed: %s", exc)

    @classmethod
    def get_writeback_status(cls, movie) -> dict:
        """Для индикатора: pending/error/synced/disabled/no_tmdb_id."""
        from vault.models import TMDBWritebackQueueItem

        # queue check first
        try:
            qi = TMDBWritebackQueueItem.objects.filter(movie=movie).first()
            if qi:
                return {"status": qi.state, "last_error": qi.last_error, "next_retry_at": qi.next_retry_at.isoformat() if qi.next_retry_at else None}
        except Exception:
            pass
        should, reason = cls._should_writeback(movie)
        if not should:
            if "no tmdb_id" in reason:
                return {"status": "no_tmdb_id", "reason": reason}
            return {"status": "disabled", "reason": reason}
        return {"status": "synced"}

    # --- guards ---

    @classmethod
    def _should_writeback(cls, movie) -> tuple[bool, str]:
        """Общий guard: токен, настройки, tmdb_id."""
        from moviefilter.models import UserPreferences

        prefs = UserPreferences.get()
        if not prefs.tmdb_writeback_enabled:
            return False, "writeback disabled in preferences"
        if not prefs.tmdb_v4_authenticated_access_token:
            return False, "no TMDB write token"
        if movie is None:
            return False, "no movie"
        if not getattr(movie, "tmdb_id", None):
            return False, "movie has no tmdb_id"
        media_type = getattr(movie, "tmdb_media_type", None)
        if media_type not in ("movie", "tv"):
            return False, f"invalid media_type={media_type}"
        return True, ""

    @classmethod
    def _get_tmdb_obj(cls, movie):
        """Вернуть tmdb Movie / TVShow объект по vault Movie."""
        from tmdb_adapter.client_singleton import get_tmdb_client

        tmdb = get_tmdb_client()
        tmdb_id = int(movie.tmdb_id)
        if movie.tmdb_media_type == "movie":
            return tmdb.movie(tmdb_id)
        return tmdb.tv_show(tmdb_id)

    # --- public: single UserMovie sync ---

    @classmethod
    def sync_user_movie_to_tmdb(cls, user_movie) -> list[WritebackResult]:
        """
        Синхронизировать ОДИН UserMovie с TMDB (watchlist + favorite + rating).
        Вызывается из signals post_save. Идемпотентно — выставляет конечное состояние.
        """
        movie = getattr(user_movie, "movie", None)
        # если movie не загружен — подгружаем
        if movie is None:
            try:
                from vault.models import UserMovie as UM

                user_movie = UM.objects.select_related("movie").get(pk=user_movie.pk)
                movie = user_movie.movie
            except Exception as exc:
                logger.warning("writeback: cannot load movie for user_movie %s: %s", getattr(user_movie, "pk", "?"), exc)
                return [WritebackResult(success=False, action="load", error=str(exc))]

        should, reason = cls._should_writeback(movie)
        if not should:
            logger.debug("writeback skipped movie=%s tmdb_id=%s reason=%s", getattr(movie, "id", "?"), getattr(movie, "tmdb_id", None), reason)
            return [WritebackResult(success=False, action="skipped", tmdb_id=getattr(movie, "tmdb_id", None), media_type=getattr(movie, "tmdb_media_type", None), error=reason)]

        results: list[WritebackResult] = []
        # watch_status -> watchlist
        try:
            r = cls.sync_watch_status(user_movie)
            if r:
                results.append(r)
        except Exception as exc:
            logger.exception("writeback watch_status failed: %s", exc)
            results.append(WritebackResult(success=False, action="watchlist", tmdb_id=movie.tmdb_id, media_type=movie.tmdb_media_type, error=str(exc)))

        # favorite
        try:
            r = cls.sync_favorite(user_movie)
            if r:
                results.append(r)
        except Exception as exc:
            logger.exception("writeback favorite failed: %s", exc)
            results.append(WritebackResult(success=False, action="favorite", tmdb_id=movie.tmdb_id, media_type=movie.tmdb_media_type, error=str(exc)))

        # rating
        try:
            r = cls.sync_rating(user_movie)
            if r:
                results.append(r)
        except Exception as exc:
            logger.exception("writeback rating failed: %s", exc)
            results.append(WritebackResult(success=False, action="rate", tmdb_id=movie.tmdb_id, media_type=movie.tmdb_media_type, error=str(exc)))

        # skip mirror list (§20.7)
        try:
            r = cls.sync_skip_list(user_movie)
            if r:
                results.append(r)
        except Exception as exc:
            logger.exception("writeback skip_list failed: %s", exc)
            results.append(WritebackResult(success=False, action="skip_list", tmdb_id=movie.tmdb_id, media_type=movie.tmdb_media_type, error=str(exc)))

        # user custom lists
        should_lists, lists_reason = cls._should_writeback_lists()
        if should_lists:
            try:
                from vault.models import UserListMovie

                for lm in UserListMovie.objects.filter(movie=movie).select_related("user_list"):
                    r = cls.sync_list_item_added(lm)
                    if r:
                        results.append(r)
            except Exception as exc:
                logger.exception("writeback user_lists failed: %s", exc)
                results.append(WritebackResult(success=False, action="user_lists", tmdb_id=movie.tmdb_id, media_type=movie.tmdb_media_type, error=str(exc)))
        else:
            logger.debug("writeback user_lists skipped: %s", lists_reason)

        # --- persistent queue handling (forever, 10m) ---
        # Ретрай обеспечивается periodic task `tmdb_writeback_retry_tick`
        # (vault/tasks.py), который раз в 10 минут подбирает записи из
        # TMDBWritebackQueueItem и вызывает sync_user_movie_to_tmdb.
        # Дополнительный HUEY-schedule здесь не нужен — иначе на один failed
        # write-back приходят два независимых триггера и дублируют запросы.
        failed = [r for r in results if not r.success and r.action != "skipped"]
        if failed:
            err_msg = failed[0].error or "unknown"
            is_auth = any(cls._is_auth_error(Exception(r.error)) for r in failed if r.error)
            cls._upsert_queue_item(movie, err_msg, is_auth=is_auth)
        else:
            cls._clear_queue_item(movie)

        return results

    @classmethod
    def sync_user_movie_to_tmdb_by_id(cls, user_movie_id: int) -> list[WritebackResult]:
        """Helper для HUEY / on_commit — загрузка по id."""
        from vault.models import UserMovie

        try:
            um = UserMovie.objects.select_related("movie").get(pk=user_movie_id)
        except UserMovie.DoesNotExist:
            logger.warning("writeback: UserMovie %s not found", user_movie_id)
            return [WritebackResult(success=False, action="not_found", error=f"UserMovie {user_movie_id} not found")]
        return cls.sync_user_movie_to_tmdb(um)

    @classmethod
    def sync_user_movie_deleted(cls, user_movie) -> list[WritebackResult]:
        """
        Cleanup при удалении UserMovie — убрать из watchlist/favorite и удалить рейтинг.
        user_movie — инстанс до удаления (post_delete всё ещё содержит поля в памяти).
        """
        movie = getattr(user_movie, "movie", None)
        if movie is None:
            # попытка достать из снапшота полей — без movie ничего не сделать
            logger.debug("writeback delete: no movie for user_movie %s", getattr(user_movie, "pk", "?"))
            return []
        should, reason = cls._should_writeback(movie)
        if not should:
            return [WritebackResult(success=False, action="skipped", tmdb_id=getattr(movie, "tmdb_id", None), media_type=getattr(movie, "tmdb_media_type", None), error=reason)]

        results: list[WritebackResult] = []
        try:
            tmdb_obj = cls._get_tmdb_obj(movie)
            # watchlist remove
            try:
                tmdb_obj.remove_from_watchlist()
                logger.info("writeback delete: watchlist_remove tmdb_id=%s", movie.tmdb_id)
                results.append(WritebackResult(success=True, action="watchlist_remove", tmdb_id=movie.tmdb_id, media_type=movie.tmdb_media_type))
            except Exception as exc:
                msg = str(exc)
                # 404/не в watchlist — считаем успехом идемпотентно
                if "404" in msg or "not found" in msg.lower():
                    results.append(WritebackResult(success=True, action="watchlist_remove", tmdb_id=movie.tmdb_id, media_type=movie.tmdb_media_type))
                else:
                    logger.warning("writeback delete watchlist_remove failed tmdb_id=%s: %s", movie.tmdb_id, exc)
                    results.append(WritebackResult(success=False, action="watchlist_remove", tmdb_id=movie.tmdb_id, media_type=movie.tmdb_media_type, error=msg))
            # favorite remove
            try:
                tmdb_obj.remove_as_favorite()
                logger.info("writeback delete: favorite_remove tmdb_id=%s", movie.tmdb_id)
                results.append(WritebackResult(success=True, action="favorite_remove", tmdb_id=movie.tmdb_id, media_type=movie.tmdb_media_type))
            except Exception as exc:
                msg = str(exc)
                if "404" in msg or "not found" in msg.lower():
                    results.append(WritebackResult(success=True, action="favorite_remove", tmdb_id=movie.tmdb_id, media_type=movie.tmdb_media_type))
                else:
                    logger.warning("writeback delete favorite_remove failed tmdb_id=%s: %s", movie.tmdb_id, exc)
                    results.append(WritebackResult(success=False, action="favorite_remove", tmdb_id=movie.tmdb_id, media_type=movie.tmdb_media_type, error=msg))
            # rating delete
            try:
                tmdb_obj.delete_rating()
                logger.info("writeback delete: delete_rating tmdb_id=%s", movie.tmdb_id)
                results.append(WritebackResult(success=True, action="unrate", tmdb_id=movie.tmdb_id, media_type=movie.tmdb_media_type))
            except Exception as exc:
                msg = str(exc)
                # если рейтинга нет — ok
                if "404" in msg or "not found" in msg.lower():
                    results.append(WritebackResult(success=True, action="unrate", tmdb_id=movie.tmdb_id, media_type=movie.tmdb_media_type))
                else:
                    logger.warning("writeback delete delete_rating failed tmdb_id=%s: %s", movie.tmdb_id, exc)
                    results.append(WritebackResult(success=False, action="unrate", tmdb_id=movie.tmdb_id, media_type=movie.tmdb_media_type, error=msg))
            # skip list cleanup: удалить из TMDB skip list если был
            try:
                from moviefilter.models import UserPreferences

                prefs = UserPreferences.get()
                if prefs.tmdb_skip_list_id:
                    media_type = getattr(movie, "tmdb_media_type", None) or "movie"
                    movie_tmdb_id = getattr(movie, "tmdb_id", None)
                    if movie_tmdb_id:
                        from tmdb_adapter.client_singleton import get_tmdb_client
                        tmdb = get_tmdb_client()
                        api4 = tmdb._api4
                        if api4:
                            api4.list_remove_items(
                                list_id=int(prefs.tmdb_skip_list_id),
                                items=[{"media_type": media_type, "media_id": int(movie_tmdb_id)}],
                            )
                            logger.info("writeback skip_list cleanup movie=%s tmdb_id=%s", movie.id, movie_tmdb_id)
            except Exception as exc:
                logger.warning("writeback skip_list cleanup failed: %s", exc)
        except Exception as exc:
            logger.exception("writeback delete failed tmdb_id=%s: %s", getattr(movie, "tmdb_id", "?"), exc)
            results.append(WritebackResult(success=False, action="delete", tmdb_id=getattr(movie, "tmdb_id", None), media_type=getattr(movie, "tmdb_media_type", None), error=str(exc)))
        # после удаления UserMovie — чистим forever-очередь
        try:
            cls._clear_queue_item(movie)
        except Exception:
            pass
        return results

    # ------------------------------------ #
    #            DOMAIN LAYER              #
    # ------------------------------------ #

    @classmethod
    def sync_watch_status(cls, user_movie) -> Optional[WritebackResult]:
        """Синхронизировать watch_status -> TMDB watchlist."""
        from vault.models import UserMovie as UM

        movie = user_movie.movie
        tmdb_obj = cls._get_tmdb_obj(movie)
        status = user_movie.watch_status

        # PLAN (2) -> add, else remove
        watch_status = status
        try:
            if watch_status == UM.WatchStatus.PLAN:
                tmdb_obj.add_to_watchlist()
                logger.info("writeback watchlist_add movie=%s tmdb_id=%s", movie.id, movie.tmdb_id)
                return WritebackResult(success=True, action="watchlist_add", tmdb_id=movie.tmdb_id, media_type=movie.tmdb_media_type)
            else:
                # WATCHED, SKIP, None -> remove
                tmdb_obj.remove_from_watchlist()
                logger.info("writeback watchlist_remove movie=%s tmdb_id=%s status=%s", movie.id, movie.tmdb_id, watch_status)
                return WritebackResult(success=True, action="watchlist_remove", tmdb_id=movie.tmdb_id, media_type=movie.tmdb_media_type)
        except Exception as exc:
            msg = str(exc)
            if cls._is_auth_error(exc):
                logger.error("writeback 401 token expired watchlist tmdb_id=%s: %s", movie.tmdb_id, exc)
            elif cls._is_rate_limited(exc):
                logger.warning("writeback 429 rate-limited watchlist tmdb_id=%s: %s", movie.tmdb_id, exc)
                # Ретрай 429 обеспечивает persistent queue (sync_user_movie_to_tmdb -> TMDBWritebackQueueItem)
            else:
                logger.warning("writeback watchlist failed tmdb_id=%s: %s", movie.tmdb_id, exc)
            return WritebackResult(success=False, action="watchlist_add" if watch_status == UM.WatchStatus.PLAN else "watchlist_remove", tmdb_id=movie.tmdb_id, media_type=movie.tmdb_media_type, error=msg, retry_after=5 if cls._is_rate_limited(exc) else None)

    @classmethod
    def sync_favorite(cls, user_movie) -> Optional[WritebackResult]:
        movie = user_movie.movie
        tmdb_obj = cls._get_tmdb_obj(movie)
        is_fav = bool(user_movie.is_favorite)
        try:
            if is_fav:
                tmdb_obj.mark_as_favorite()
                logger.info("writeback favorite_add movie=%s tmdb_id=%s", movie.id, movie.tmdb_id)
                return WritebackResult(success=True, action="favorite_add", tmdb_id=movie.tmdb_id, media_type=movie.tmdb_media_type)
            else:
                tmdb_obj.remove_as_favorite()
                logger.info("writeback favorite_remove movie=%s tmdb_id=%s", movie.id, movie.tmdb_id)
                return WritebackResult(success=True, action="favorite_remove", tmdb_id=movie.tmdb_id, media_type=movie.tmdb_media_type)
        except Exception as exc:
            msg = str(exc)
            if cls._is_auth_error(exc):
                logger.error("writeback 401 token expired favorite tmdb_id=%s: %s", movie.tmdb_id, exc)
            elif cls._is_rate_limited(exc):
                logger.warning("writeback 429 rate-limited favorite tmdb_id=%s: %s", movie.tmdb_id, exc)
                # Ретрай 429 обеспечивает persistent queue
            else:
                logger.warning("writeback favorite failed tmdb_id=%s is_fav=%s: %s", movie.tmdb_id, is_fav, exc)
            return WritebackResult(success=False, action="favorite_add" if is_fav else "favorite_remove", tmdb_id=movie.tmdb_id, media_type=movie.tmdb_media_type, error=msg, retry_after=5 if cls._is_rate_limited(exc) else None)

    @classmethod
    def sync_rating(cls, user_movie) -> Optional[WritebackResult]:
        movie = user_movie.movie
        tmdb_obj = cls._get_tmdb_obj(movie)
        rating = user_movie.rating
        try:
            if rating is not None:
                # TMDB принимает float 0.5-10.0, Vault int 1-10 — передаём как есть (целые валидны)
                tmdb_obj.rate(float(rating))
                logger.info("writeback rate movie=%s tmdb_id=%s rating=%s", movie.id, movie.tmdb_id, rating)
                return WritebackResult(success=True, action="rate", tmdb_id=movie.tmdb_id, media_type=movie.tmdb_media_type)
            else:
                tmdb_obj.delete_rating()
                logger.info("writeback unrate movie=%s tmdb_id=%s", movie.id, movie.tmdb_id)
                return WritebackResult(success=True, action="unrate", tmdb_id=movie.tmdb_id, media_type=movie.tmdb_media_type)
        except Exception as exc:
            msg = str(exc)
            # Если рейтинга не было — delete_rating может 404 — считаем ок для unrate
            if rating is None and ("404" in msg or "not found" in msg.lower()):
                return WritebackResult(success=True, action="unrate", tmdb_id=movie.tmdb_id, media_type=movie.tmdb_media_type)
            if cls._is_auth_error(exc):
                logger.error("writeback 401 token expired rating tmdb_id=%s: %s", movie.tmdb_id, exc)
            elif cls._is_rate_limited(exc):
                logger.warning("writeback 429 rate-limited rating tmdb_id=%s: %s", movie.tmdb_id, exc)
                # Ретрай 429 обеспечивает persistent queue
            else:
                logger.warning("writeback rating failed tmdb_id=%s rating=%s: %s", movie.tmdb_id, rating, exc)
            return WritebackResult(success=False, action="rate" if rating is not None else "unrate", tmdb_id=movie.tmdb_id, media_type=movie.tmdb_media_type, error=msg, retry_after=5 if cls._is_rate_limited(exc) else None)

    # --- skip list (TMDB mirror, без локального UserList) ---

    @classmethod
    def _ensure_skip_list_tmdb_id(cls) -> int:
        """Вернуть TMDB list ID для 'Не интересует'.
        1. Кэш в preferences → проверяем что список жив на TMDB.
        2. Если нет — ищем по имени среди account lists.
        3. Если нет — создаём.
        Бросает исключение если TMDB API недоступен."""
        from moviefilter.models import UserPreferences
        from tmdb_adapter.client_singleton import get_tmdb_client

        tmdb = get_tmdb_client()
        api4 = tmdb._api4
        if api4 is None:
            raise RuntimeError("TMDB v4 client not available")

        def _list_exists(list_id: int) -> bool:
            try:
                api4.list_get_list(list_id=list_id)
                return True
            except Exception:
                return False

        # Сериализуем параллельные вызовы: одновременный вход двух сигналов
        # без блокировки создаст два одинаковых TMDB-листа «Не интересует».
        # threading.Lock покрывает single-process + multi-thread (dev runserver),
        # select_for_update — multi-process (postgres).
        with cls._skip_list_lock:
            with transaction.atomic():
                prefs = UserPreferences.objects.select_for_update().get(pk=1)

                # 1. Кэш — проверяем что жив
                if prefs.tmdb_skip_list_id:
                    if _list_exists(int(prefs.tmdb_skip_list_id)):
                        return int(prefs.tmdb_skip_list_id)
                    # удалён на TMDB — сбрасываем
                    prefs.tmdb_skip_list_id = None
                    prefs.save(update_fields=["tmdb_skip_list_id"])

                # 2. Ищем по имени (api4 возвращает dict)
                target_name = cls.SKIP_LIST_NAME
                page = 1
                while True:
                    try:
                        result = api4.account_get_lists(page=page)
                    except Exception:
                        break
                    if not isinstance(result, dict):
                        break
                    for item in result.get("results", []):
                        if item.get("name") == target_name:
                            list_id = int(item["id"])
                            prefs.tmdb_skip_list_id = list_id
                            prefs.save(update_fields=["tmdb_skip_list_id"])
                            return list_id
                    if page >= result.get("total_pages", 1):
                        break
                    page += 1

                # 3. Создаём (api4.list_create_list возвращает dict)
                result = api4.list_create_list(
                    name=target_name,
                    iso_639_1="ru",
                    description="Зеркало системного статуса 'Не интересует'",
                    public=False,
                )
                new_id = result.get("id") if isinstance(result, dict) else None
                if not new_id:
                    raise RuntimeError(f"TMDB list_create_list returned unexpected: {result}")
                new_id = int(new_id)
                prefs.tmdb_skip_list_id = new_id
                prefs.save(update_fields=["tmdb_skip_list_id"])
                return new_id

    @classmethod
    def sync_skip_list(cls, user_movie) -> Optional[WritebackResult]:
        """SKIP (Не интересует) ↔ TMDB List 'Не интересует'.

        Архитектура:
        - Локально: системный список = UserMovie.watch_status=SKIP. Никакого UserList.
        - На TMDB: отдельный список, ID хранится в UserPreferences.tmdb_skip_list_id.
        - Метод идемпотентен: добавляет/убирает фильм из TMDB-листа."""
        from vault.models import UserMovie as UM

        movie = getattr(user_movie, "movie", None)
        if not movie:
            return None
        watch_status = getattr(user_movie, "watch_status", None)
        movie_tmdb_id = getattr(movie, "tmdb_id", None)
        if not movie_tmdb_id:
            return None

        try:
            list_tmdb_id = cls._ensure_skip_list_tmdb_id()
        except Exception as exc:
            logger.warning("writeback skip_list: cannot get/create TMDB list: %s", exc)
            return WritebackResult(success=False, action="skip_list", tmdb_id=movie_tmdb_id, error=str(exc))

        media_type = getattr(movie, "tmdb_media_type", None) or "movie"

        try:
            from tmdb_adapter.client_singleton import get_tmdb_client

            tmdb = get_tmdb_client()
            api4 = tmdb._api4
            if api4 is None:
                return WritebackResult(success=False, action="skip_list", tmdb_id=movie_tmdb_id, error="no v4 client")

            if watch_status == UM.WatchStatus.SKIP:
                api4.list_add_items(
                    list_id=list_tmdb_id,
                    items=[{"media_type": media_type, "media_id": int(movie_tmdb_id)}],
                )
                logger.info("writeback skip_list add movie=%s tmdb_id=%s list=%s", movie.id, movie_tmdb_id, list_tmdb_id)
                return WritebackResult(success=True, action="skip_list_add", tmdb_id=movie_tmdb_id, media_type=media_type)
            else:
                api4.list_remove_items(
                    list_id=list_tmdb_id,
                    items=[{"media_type": media_type, "media_id": int(movie_tmdb_id)}],
                )
                logger.info("writeback skip_list remove movie=%s tmdb_id=%s list=%s", movie.id, movie_tmdb_id, list_tmdb_id)
                return WritebackResult(success=True, action="skip_list_remove", tmdb_id=movie_tmdb_id, media_type=media_type)
        except Exception as exc:
            # Если список был удалён на TMDB — сбросить кэш и пробрасывать ошибку
            msg = str(exc)
            if "404" in msg or "not found" in msg.lower():
                from moviefilter.models import UserPreferences
                UserPreferences.objects.filter(pk=1).update(tmdb_skip_list_id=None)
            logger.warning("writeback skip_list failed movie=%s: %s", getattr(movie, "id", "?"), exc)
            return WritebackResult(
                success=False,
                action="skip_list_add" if watch_status == UM.WatchStatus.SKIP else "skip_list_remove",
                tmdb_id=movie_tmdb_id,
                error=msg,
            )

    # --- lists ---

    @classmethod
    def _should_writeback_lists(cls) -> tuple[bool, str]:
        from moviefilter.models import UserPreferences

        prefs = UserPreferences.get()
        # Single toggle: lists follow main writeback (tmdb_writeback_lists_enabled kept for compat but ignored)
        if not prefs.tmdb_writeback_enabled:
            return False, "writeback disabled"
        if not prefs.tmdb_v4_authenticated_access_token:
            return False, "no token"
        return True, ""

    @classmethod
    def sync_list_item_added(cls, list_movie) -> Optional[WritebackResult]:
        """Добавить фильм в TMDB list (UserListMovie post_save)."""
        should, reason = cls._should_writeback_lists()
        if not should:
            logger.debug("lists writeback skipped: %s", reason)
            return WritebackResult(success=False, action="list_add_skipped", error=reason)
        user_list = getattr(list_movie, "user_list", None)
        movie = getattr(list_movie, "movie", None)
        if user_list is None or movie is None:
            try:
                from vault.models import UserListMovie

                list_movie = UserListMovie.objects.select_related("user_list", "movie").get(pk=list_movie.pk)
                user_list = list_movie.user_list
                movie = list_movie.movie
            except Exception as exc:
                return WritebackResult(success=False, action="list_add", error=str(exc))
        if not getattr(movie, "tmdb_id", None):
            return WritebackResult(success=False, action="list_add", error="movie has no tmdb_id")
        if not getattr(user_list, "tmdb_list_id", None):
            # §20.6: создаём TMDB-лист на лету, если ещё нет.
            # Это снимает race между list_sync и list_item_added при async-HUEY:
            # если добавление фильма обработалось раньше, чем список был создан,
            # здесь он создаётся сам (защита от дублей — select_for_update в create_tmdb_list).
            create_result = cls.create_tmdb_list(user_list)
            if not create_result.success:
                return WritebackResult(success=False, action="list_add_skipped", error=f"auto-create failed: {create_result.error}")
            user_list.refresh_from_db(fields=["tmdb_list_id"])
        try:
            from tmdb_adapter.client_singleton import get_tmdb_client

            tmdb = get_tmdb_client()
            api4 = tmdb._api4
            if api4 is None:
                return WritebackResult(success=False, action="list_add", error="no v4 client")
            media_type = movie.tmdb_media_type or "movie"
            api4.list_add_items(list_id=int(user_list.tmdb_list_id), items=[{"media_type": media_type, "media_id": int(movie.tmdb_id)}])
            logger.info("writeback list_add list=%s tmdb_list=%s movie tmdb_id=%s", user_list.id, user_list.tmdb_list_id, movie.tmdb_id)
            return WritebackResult(success=True, action="list_add", tmdb_id=movie.tmdb_id, media_type=media_type)
        except Exception as exc:
            logger.warning("writeback list_add failed: %s", exc)
            return WritebackResult(success=False, action="list_add", tmdb_id=getattr(movie, "tmdb_id", None), error=str(exc))

    @classmethod
    def sync_list_item_removed(cls, list_movie) -> Optional[WritebackResult]:
        """Удалить фильм из TMDB list (UserListMovie post_delete)."""
        should, reason = cls._should_writeback_lists()
        if not should:
            return WritebackResult(success=False, action="list_remove_skipped", error=reason)
        # В post_delete related объекты ещё доступны в памяти, но на всякий — снапшот
        user_list = getattr(list_movie, "user_list", None)
        movie = getattr(list_movie, "movie", None)
        # если удалён каскадом — пробуем из snapshot атрибутов (если вызываем pre_delete — будет доступно)
        if user_list is None or movie is None:
            logger.debug("list_remove: missing relation for list_movie %s", getattr(list_movie, "pk", "?"))
            return WritebackResult(success=False, action="list_remove", error="missing relation")
        if not getattr(user_list, "tmdb_list_id", None):
            return WritebackResult(success=False, action="list_remove_skipped", error="no tmdb_list_id")
        if not getattr(movie, "tmdb_id", None):
            return WritebackResult(success=False, action="list_remove", error="no tmdb_id")
        try:
            from tmdb_adapter.client_singleton import get_tmdb_client

            tmdb = get_tmdb_client()
            api4 = tmdb._api4
            if api4 is None:
                return WritebackResult(success=False, action="list_remove", error="no v4 client")
            media_type = movie.tmdb_media_type or "movie"
            api4.list_remove_items(list_id=int(user_list.tmdb_list_id), items=[{"media_type": media_type, "media_id": int(movie.tmdb_id)}])
            logger.info("writeback list_remove list=%s tmdb_list=%s tmdb_id=%s", user_list.id, user_list.tmdb_list_id, movie.tmdb_id)
            return WritebackResult(success=True, action="list_remove", tmdb_id=movie.tmdb_id, media_type=media_type)
        except Exception as exc:
            logger.warning("writeback list_remove failed: %s", exc)
            return WritebackResult(success=False, action="list_remove", tmdb_id=getattr(movie, "tmdb_id", None), error=str(exc))

    @classmethod
    def create_tmdb_list(cls, user_list, tmdb_name: str | None = None) -> WritebackResult:
        """Создать TMDB List для UserList.
        tmdb_name — имя для TMDB-листа (по умолчанию берётся локальное name).
        """
        should, reason = cls._should_writeback_lists()
        if not should:
            return WritebackResult(success=False, action="list_create_skipped", error=reason)
        try:
            from tmdb_adapter.client_singleton import get_tmdb_client
            from vault.models import UserList as UL

            # §1.2 race: лочим строку перед внешним API, чтобы не создать дубликаты
            with transaction.atomic():
                locked = UL.objects.select_for_update().get(pk=user_list.pk)
                if locked.tmdb_list_id:
                    # уже создал параллельный поток
                    user_list.tmdb_list_id = locked.tmdb_list_id
                    return WritebackResult(success=True, action="list_create", tmdb_id=int(locked.tmdb_list_id), media_type="list")
                tmdb = get_tmdb_client()
                list_name = tmdb_name or locked.name
                result = tmdb.create_list(name=list_name, iso_639_1="ru", description=locked.description or "", public=bool(locked.is_public))
                new_id = getattr(result, "id", None)
                if new_id is None and isinstance(result, int):
                    new_id = result
                if not new_id:
                    return WritebackResult(success=False, action="list_create", error=f"unexpected result {result}")
                UL.objects.filter(pk=locked.pk).update(tmdb_list_id=int(new_id))
                user_list.tmdb_list_id = int(new_id)
                locked.tmdb_list_id = int(new_id)
                logger.info("writeback list_create id=%s tmdb_list=%s tmdb_name=%s", locked.id, new_id, list_name)
                return WritebackResult(success=True, action="list_create", tmdb_id=int(new_id), media_type="list")
        except UL.DoesNotExist:
            return WritebackResult(success=False, action="list_create", error="UserList not found")
        except Exception as exc:
            logger.warning("writeback list_create failed: %s", exc)
            return WritebackResult(success=False, action="list_create", error=str(exc))

    @classmethod
    def delete_tmdb_list(cls, user_list) -> WritebackResult:
        should, reason = cls._should_writeback_lists()
        if not should:
            return WritebackResult(success=False, action="list_delete_skipped", error=reason)
        tmdb_list_id = getattr(user_list, "tmdb_list_id", None)
        if not tmdb_list_id:
            return WritebackResult(success=False, action="list_delete_skipped", error="no tmdb_list_id")
        try:
            from tmdb_adapter.client_singleton import get_tmdb_client

            tmdb = get_tmdb_client()
            api4 = tmdb._api4
            if api4 is None:
                return WritebackResult(success=False, action="list_delete", error="no v4 client")
            api4.list_delete_list(list_id=int(tmdb_list_id))
            logger.info("writeback list_delete id=%s tmdb_list=%s", user_list.id, tmdb_list_id)
            return WritebackResult(success=True, action="list_delete", tmdb_id=int(tmdb_list_id))
        except Exception as exc:
            logger.warning("writeback list_delete failed: %s", exc)
            return WritebackResult(success=False, action="list_delete", error=str(exc))

    @classmethod
    def update_tmdb_list(cls, user_list, old_name: str | None = None) -> WritebackResult:
        """Обновить имя/описание TMDB List при rename."""
        should, reason = cls._should_writeback_lists()
        if not should:
            return WritebackResult(success=False, action="list_update_skipped", error=reason)
        tmdb_list_id = getattr(user_list, "tmdb_list_id", None)
        if not tmdb_list_id:
            return WritebackResult(success=False, action="list_update_skipped", error="no tmdb_list_id")
        try:
            from tmdb_adapter.client_singleton import get_tmdb_client

            tmdb = get_tmdb_client()
            api4 = tmdb._api4
            if api4 is None:
                return WritebackResult(success=False, action="list_update", error="no v4 client")
            # TMDB V4: list_update_list
            api4.list_update_list(list_id=int(tmdb_list_id), name=user_list.name, description=user_list.description or "", public=bool(user_list.is_public))
            logger.info("writeback list_update id=%s tmdb_list=%s name=%s", user_list.id, tmdb_list_id, user_list.name)
            return WritebackResult(success=True, action="list_update", tmdb_id=int(tmdb_list_id))
        except Exception as exc:
            logger.warning("writeback list_update failed id=%s: %s", user_list.id, exc)
            return WritebackResult(success=False, action="list_update", error=str(exc))

    @classmethod
    def init_all_user_lists(cls) -> dict:
        """Одноразовая инициализация + восстановление удалённых на TMDB списков. Ставит флаг."""
        from moviefilter.models import UserPreferences
        from vault.models import UserList

        prefs = UserPreferences.get()
        should, reason = cls._should_writeback_lists()
        if not should:
            return {"created": 0, "error": reason}

        # инициализируем TMDB skip list ID (если ещё нет)
        try:
            cls._ensure_skip_list_tmdb_id()
        except Exception as exc:
            logger.warning("writeback lists init: skip list init failed: %s", exc)

        # берём все локальные списки, проверяем каждый
        all_lists = list(UserList.objects.all())
        to_create = []
        for ul in all_lists:
            if not ul.tmdb_list_id:
                to_create.append(ul)
                continue
            # есть tmdb_id — проверяем жив ли он на TMDB (пользователь мог удалить вручную)
            try:
                from tmdb_adapter.client_singleton import get_tmdb_client

                tmdb = get_tmdb_client()
                api4 = tmdb._api4
                if api4 is None:
                    continue
                api4.list_get_list(list_id=int(ul.tmdb_list_id))
            except Exception as exc:
                msg = str(exc)
                # 404 / NotFound → список удалён на TMDB, надо пересоздать
                if "404" in msg or "NotFound" in type(exc).__name__ or "not found" in msg.lower():
                    logger.warning("writeback lists init: TMDB list %s missing for UserList %s (%s), will recreate", ul.tmdb_list_id, ul.id, ul.name)
                    # сбросим локально и добавим в создание
                    UserList.objects.filter(pk=ul.pk).update(tmdb_list_id=None)
                    ul.tmdb_list_id = None
                    to_create.append(ul)
                else:
                    logger.warning("writeback lists init check failed for %s: %s", ul.id, exc)

        created = 0
        errors = []
        for ul in to_create:
            # перечитать свежий объект (tmdb_list_id мог уже быть сброшен)
            try:
                fresh = UserList.objects.get(pk=ul.pk)
            except Exception:
                fresh = ul
            res = cls.create_tmdb_list(fresh)
            if res.success:
                created += 1
            else:
                errors.append(f"{fresh.id}:{fresh.name}:{res.error}")
            # пауза чтобы не триггерить spam-фильтр TMDB при массовой создании
            import time

            time.sleep(1.5)

        prefs.tmdb_lists_initialized = True
        prefs.save(update_fields=["tmdb_lists_initialized"])
        if errors:
            logger.warning("writeback lists init done created=%s errors=%s", created, errors)
        else:
            logger.info("writeback lists init done created=%s total_checked=%s", created, len(all_lists))

        return {"created": created, "errors": errors, "total": len(all_lists), "to_create": len(to_create)}
