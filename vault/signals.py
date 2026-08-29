import logging
from django.db import transaction
from django.db.models.signals import post_save, post_delete, pre_delete
from django.dispatch import receiver

from vault.models import UserList, UserListMovie, UserMovie

logger = logging.getLogger("vault.tmdb_writeback")


def _schedule_writeback_user_movie(user_movie_id: int):
    """Запускает writeback вне транзакции (точечно, без bulk)."""
    from vault.services.tmdb_writeback_service import TmdbWritebackService

    try:
        TmdbWritebackService.sync_user_movie_to_tmdb_by_id(user_movie_id)
    except Exception as exc:
        logger.exception("writeback schedule failed for UserMovie %s: %s", user_movie_id, exc)


def _schedule_writeback_delete(snapshot_movie_id: int, snapshot_tmdb_id, snapshot_media_type, snapshot_user_movie_pk):
    """Для удалённых UserMovie — snapshot уже есть, вызываем sync_user_movie_deleted напрямую."""
    # Формируем лёгкий снапшот-объект чтобы не тянуть БД
    class _MovieSnap:
        def __init__(self, id_, tmdb_id, media_type):
            self.id = id_
            self.tmdb_id = tmdb_id
            self.tmdb_media_type = media_type

    class _UMSnap:
        def __init__(self, pk_, movie):
            self.pk = pk_
            self.movie = movie

    from vault.services.tmdb_writeback_service import TmdbWritebackService

    try:
        snap = _UMSnap(snapshot_user_movie_pk, _MovieSnap(snapshot_movie_id, snapshot_tmdb_id, snapshot_media_type))
        TmdbWritebackService.sync_user_movie_deleted(snap)
    except Exception as exc:
        logger.exception("writeback delete schedule failed for UserMovie %s: %s", snapshot_user_movie_pk, exc)


# Кэш для pre_delete -> post_delete (tmdb_id/media_type исчезают после каскада movie delete)
_pending_delete_cache: dict[int, tuple[int | None, int | None, str | None]] = {}


@receiver(pre_delete, sender=UserMovie)
def _cache_user_movie_for_delete(sender, instance, **kwargs):
    try:
        movie = getattr(instance, "movie", None)
        # если movie не загружен — пробуем загрузить снапшот
        tmdb_id = getattr(movie, "tmdb_id", None) if movie else None
        media_type = getattr(movie, "tmdb_media_type", None) if movie else None
        movie_id = getattr(movie, "id", None) if movie else getattr(instance, "movie_id", None)
        # фолбэк: подгрузить movie по fk если нужно
        if (tmdb_id is None or media_type is None) and movie_id:
            from vault.models import Movie

            m = Movie.objects.filter(pk=movie_id).values("id", "tmdb_id", "tmdb_media_type").first()
            if m:
                tmdb_id = m["tmdb_id"]
                media_type = m["tmdb_media_type"]
                movie_id = m["id"]
        _pending_delete_cache[instance.pk] = (movie_id, tmdb_id, media_type)
    except Exception:
        pass


@receiver(post_save, sender=UserMovie)
def on_user_movie_saved(sender, instance, created, **kwargs):
    pk = instance.pk  # захват по значению для on_commit (R1)
    transaction.on_commit(lambda pk=pk: _schedule_writeback_user_movie(pk))


@receiver(post_delete, sender=UserMovie)
def on_user_movie_deleted(sender, instance, **kwargs):
    cached = _pending_delete_cache.pop(instance.pk, None)
    if cached is None:
        # фолбэк — пробуем из instance (если movie ещё в памяти)
        movie = getattr(instance, "movie", None)
        cached = (
            getattr(movie, "id", None) if movie else getattr(instance, "movie_id", None),
            getattr(movie, "tmdb_id", None) if movie else None,
            getattr(movie, "tmdb_media_type", None) if movie else None,
        )
    movie_id, tmdb_id, media_type = cached
    if not tmdb_id or media_type not in ("movie", "tv"):
        logger.debug("writeback delete skipped UserMovie %s tmdb_id=%s media=%s", instance.pk, tmdb_id, media_type)
        return
    pk = instance.pk
    transaction.on_commit(lambda pk=pk, mid=movie_id, tid=tmdb_id, mt=media_type: _schedule_writeback_delete(mid, tid, mt, pk))


# --- UserListMovie ---

@receiver(post_save, sender=UserListMovie)
def on_user_list_movie_saved(sender, instance, created, **kwargs):
    if not created:
        return
    pk = instance.pk

    def _do(pk=pk):
        from vault.models import UserListMovie as ULM

        try:
            obj = ULM.objects.select_related("user_list", "movie").get(pk=pk)
        except ULM.DoesNotExist:
            return
        from vault.services.tmdb_writeback_service import TmdbWritebackService as S

        S.sync_list_item_added(obj)

    transaction.on_commit(_do)


# Для list_remove нужен pre_delete чтобы сохранить связи (post_delete теряет FK объекты)
_pending_list_delete: dict[int, object] = {}


@receiver(pre_delete, sender=UserListMovie)
def _cache_list_movie_for_delete(sender, instance, **kwargs):
    # сохраняем снапшот с подгруженными relation если возможно
    try:
        # force load if not cached
        ul = getattr(instance, "user_list", None)
        mv = getattr(instance, "movie", None)
        if ul is None or mv is None:
            from vault.models import UserListMovie as ULM

            try:
                fresh = ULM.objects.select_related("user_list", "movie").get(pk=instance.pk)
                instance.user_list = fresh.user_list
                instance.movie = fresh.movie
            except Exception:
                pass
        _pending_list_delete[instance.pk] = instance
    except Exception:
        pass


@receiver(post_delete, sender=UserListMovie)
def on_user_list_movie_deleted(sender, instance, **kwargs):
    cached = _pending_list_delete.pop(instance.pk, instance)
    # instance в post_delete уже без pk? но мы сохранили
    pk = getattr(cached, "pk", None)
    # используем cached с relation
    def _do(cached=cached):
        from vault.services.tmdb_writeback_service import TmdbWritebackService as S

        S.sync_list_item_removed(cached)

    transaction.on_commit(_do)


# --- UserList CRUD → TMDB Lists (automatik, без кнопки) ---

@receiver(post_save, sender=UserList)
def on_userlist_saved(sender, instance, created, **kwargs):
    from vault.services.tmdb_writeback_service import TmdbWritebackService

    should, _ = TmdbWritebackService._should_writeback_lists()
    if not should:
        return
    ul_id = instance.pk

    def _do(ul_id=ul_id):
        from vault.models import UserList as UL
        from vault.services.tmdb_writeback_service import TmdbWritebackService as S

        try:
            ul = UL.objects.get(pk=ul_id)
        except UL.DoesNotExist:
            return
        if not ul.tmdb_list_id:
            # ещё не на TMDB — создаём (покрывает и rename pending-списка)
            S.create_tmdb_list(ul)
        else:
            # уже на TMDB — обновляем имя/описание
            S.update_tmdb_list(ul)

    transaction.on_commit(_do)


@receiver(post_delete, sender=UserList)
def on_userlist_deleted(sender, instance, **kwargs):
    from vault.services.tmdb_writeback_service import TmdbWritebackService

    # если списка нет на TMDB — нечего удалять
    if not getattr(instance, "tmdb_list_id", None):
        return
    should, _ = TmdbWritebackService._should_writeback_lists()
    if not should:
        return
    tmdb_id = instance.tmdb_list_id
    # instance уже удалён, используем снапшот

    def _do(tmdb_id=tmdb_id):
        from vault.services.tmdb_writeback_service import TmdbWritebackService as S

        # создаём лёгкий снапшот для delete
        class _Snap:
            tmdb_list_id = tmdb_id
            id = 0

        S.delete_tmdb_list(_Snap())

    transaction.on_commit(_do)
