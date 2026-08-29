from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Optional

from django.db import transaction
from django.utils import timezone

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

    SKIP_LIST_NAME = "Не буду смотреть"

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

    @classmethod
    def _schedule_retry(cls, user_movie_id: int, delay: int = 600):
        """Legacy HUEY retry (теперь persistent queue, delay 10m)."""
        try:
            from vault.tasks import tmdb_writeback_user_movie

            tmdb_writeback_user_movie.schedule(args=(user_movie_id,), delay=delay)
            logger.warning("writeback scheduled retry user_movie=%s delay=%ss", user_movie_id, delay)
            return True
        except Exception as exc:
            logger.warning("writeback schedule retry failed user_movie=%s: %s", user_movie_id, exc)
            return False

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
            # increment attempts
            TMDBWritebackQueueItem.objects.filter(pk=obj.pk).update(attempts=obj.attempts + 1)
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

        # --- persistent queue handling (forever, 10m) ---
        failed = [r for r in results if not r.success and r.action != "skipped"]
        if failed:
            # берём первую ошибку для очереди
            err_msg = failed[0].error or "unknown"
            is_auth = any("401" in (r.error or "") or "Authentication" in (r.error or "") or "Unauthorized" in (r.error or "") for r in failed) or any(cls._is_auth_error(Exception(r.error)) for r in failed if r.error)
            # точнее: проверяем failed error strings
            if any("401" in (r.error or "") or "Invalid API key" in (r.error or "") for r in failed):
                is_auth = True
            cls._upsert_queue_item(movie, err_msg, is_auth=is_auth)
            # также HUEY retry для 429/сети (10m)
            if not is_auth:
                # schedule HUEY as secondary trigger (periodic task и так подхватит)
                try:
                    from vault.tasks import tmdb_writeback_user_movie

                    tmdb_writeback_user_movie.schedule(args=(user_movie.pk,), delay=600)
                except Exception:
                    pass
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
            # skip list cleanup (§20.7): удалить из зеркального списка если был
            try:
                from vault.models import UserList, UserListMovie

                skip_lists = UserList.objects.filter(name=cls.SKIP_LIST_NAME)
                del_cnt, _ = UserListMovie.objects.filter(user_list__in=skip_lists, movie=movie).delete()
                if del_cnt:
                    logger.info("writeback skip_list cleanup delete movie=%s deleted=%s", movie.id, del_cnt)
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
                cls._schedule_retry(getattr(user_movie, "pk", None) or getattr(user_movie, "id", 0), delay=5)
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
                cls._schedule_retry(getattr(user_movie, "pk", None) or getattr(user_movie, "id", 0), delay=5)
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
                cls._schedule_retry(getattr(user_movie, "pk", None) or getattr(user_movie, "id", 0), delay=5)
            else:
                logger.warning("writeback rating failed tmdb_id=%s rating=%s: %s", movie.tmdb_id, rating, exc)
            return WritebackResult(success=False, action="rate" if rating is not None else "unrate", tmdb_id=movie.tmdb_id, media_type=movie.tmdb_media_type, error=msg, retry_after=5 if cls._is_rate_limited(exc) else None)

    @classmethod
    def sync_skip_list(cls, user_movie) -> Optional[WritebackResult]:
        """SKIP (Не буду смотреть) ↔ TMDB List 'Не буду смотреть' (UserList). §20.7"""
        from vault.models import UserMovie as UM, UserList, UserListMovie

        user = getattr(user_movie, "user", None)
        movie = getattr(user_movie, "movie", None)
        if not user or not movie:
            return None
        # guard: нужен tmdb_id чтобы синк имел смысл, иначе только локально
        has_tmdb = bool(getattr(movie, "tmdb_id", None))
        watch_status = getattr(user_movie, "watch_status", None)
        # найти/создать системный зеркальный список (локально)
        skip_list, _ = UserList.objects.get_or_create(
            user=user, name=cls.SKIP_LIST_NAME, defaults={"description": "Авто: зеркало статуса 'Не буду смотреть' → TMDB"}
        )
        try:
            if watch_status == UM.WatchStatus.SKIP:
                # добавить в зеркальный список (локально) → сигнал UserListMovie займётся TMDB (auto-create)
                obj, created = UserListMovie.objects.get_or_create(user_list=skip_list, movie=movie)
                if created:
                    logger.info("writeback skip_list add movie=%s list=%s", movie.id, skip_list.id)
                # если уже есть — ничего, TMDB синк уже был при создании
                return WritebackResult(success=True, action="skip_list_add", tmdb_id=getattr(movie, "tmdb_id", None), media_type=getattr(movie, "tmdb_media_type", None))
            else:
                # убрать из зеркального списка если был
                deleted, _ = UserListMovie.objects.filter(user_list=skip_list, movie=movie).delete()
                if deleted:
                    logger.info("writeback skip_list remove movie=%s list=%s", movie.id, skip_list.id)
                    return WritebackResult(success=True, action="skip_list_remove", tmdb_id=getattr(movie, "tmdb_id", None), media_type=getattr(movie, "tmdb_media_type", None))
                return None
        except Exception as exc:
            logger.warning("writeback skip_list failed movie=%s: %s", getattr(movie, "id", "?"), exc)
            return WritebackResult(success=False, action="skip_list_add" if watch_status == UM.WatchStatus.SKIP else "skip_list_remove", tmdb_id=getattr(movie, "tmdb_id", None), error=str(exc))

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
            logger.debug("list_add skipped: UserList %s has no tmdb_list_id (need init)", user_list.id)
            return WritebackResult(success=False, action="list_add_skipped", error="no tmdb_list_id — need lists init")
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
    def create_tmdb_list(cls, user_list) -> WritebackResult:
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
                result = tmdb.create_list(name=locked.name, iso_639_1="ru", description=locked.description or "", public=bool(locked.is_public))
                new_id = getattr(result, "id", None)
                if new_id is None and isinstance(result, int):
                    new_id = result
                if not new_id:
                    return WritebackResult(success=False, action="list_create", error=f"unexpected result {result}")
                UL.objects.filter(pk=locked.pk).update(tmdb_list_id=int(new_id))
                user_list.tmdb_list_id = int(new_id)
                locked.tmdb_list_id = int(new_id)
                logger.info("writeback list_create id=%s tmdb_list=%s", locked.id, new_id)
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
        """Одноразовая инициализация: создать все локальные UserList на TMDB где tmdb_list_id is None. Ставит флаг."""
        from moviefilter.models import UserPreferences
        from vault.models import UserList

        prefs = UserPreferences.get()
        if prefs.tmdb_lists_initialized:
            return {"created": 0, "skipped": UserList.objects.filter(tmdb_list_id__isnull=False).count(), "reason": "already initialized"}

        should, reason = cls._should_writeback_lists()
        if not should:
            return {"created": 0, "error": reason}

        qs = UserList.objects.filter(tmdb_list_id__isnull=True)
        created = 0
        errors = []
        for ul in qs:
            res = cls.create_tmdb_list(ul)
            if res.success:
                created += 1
            else:
                errors.append(f"{ul.id}:{res.error}")

        # ставим флаг даже при частичном успехе — spam-листы не должны блокировать новые списки
        # (ошибки типа 18 spam — не ретраятся, нужно переименовать)
        prefs.tmdb_lists_initialized = True
        prefs.save(update_fields=["tmdb_lists_initialized"])
        if errors:
            logger.warning("writeback lists init partial created=%s errors=%s", created, errors)
        else:
            logger.info("writeback lists init done created=%s", created)

        return {"created": created, "errors": errors, "total": qs.count()}
