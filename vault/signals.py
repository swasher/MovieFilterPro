import logging
from django.db import transaction
from django.db.models.signals import post_save, post_delete, pre_delete
from django.dispatch import receiver

from vault.models import UserList, UserListMovie, UserMovie
from vault.services.tmdb_writeback_dispatch import TmdbWritebackDispatch

logger = logging.getLogger("vault.tmdb_writeback")


# --- UserMovie ---


@receiver(post_save, sender=UserMovie)
def on_user_movie_saved(sender, instance, created, **kwargs):
    pk = instance.pk  # захват по значению для on_commit (R1)
    transaction.on_commit(lambda pk=pk: TmdbWritebackDispatch.schedule_user_movie_writeback(pk))


# Снапшот для pre_delete -> post_delete (tmdb_id/media_type исчезают после каскада movie delete)
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

    def _do(mid=movie_id, tid=tmdb_id, mt=media_type):
        TmdbWritebackDispatch.schedule_user_movie_delete(mid, tid, mt)

    transaction.on_commit(_do)


# --- UserListMovie ---


@receiver(post_save, sender=UserListMovie)
def on_user_list_movie_saved(sender, instance, created, **kwargs):
    if not created:
        return
    pk = instance.pk
    transaction.on_commit(lambda pk=pk: TmdbWritebackDispatch.schedule_list_item_added(pk))


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
    ul = getattr(cached, "user_list", None)
    mv = getattr(cached, "movie", None)
    if ul is None or mv is None:
        logger.debug("writeback list_remove skipped: missing snapshot for list_movie %s", getattr(cached, "pk", "?"))
        return
    tmdb_list_id = getattr(ul, "tmdb_list_id", None)
    tmdb_id = getattr(mv, "tmdb_id", None)
    media_type = getattr(mv, "tmdb_media_type", None) or "movie"

    def _do(tl=tmdb_list_id, tid=tmdb_id, mt=media_type):
        if tl and tid:
            TmdbWritebackDispatch.schedule_list_item_removed(tl, tid, mt)

    transaction.on_commit(_do)


# --- UserList CRUD → TMDB Lists (automatik, без кнопки) ---


@receiver(post_save, sender=UserList)
def on_userlist_saved(sender, instance, created, **kwargs):
    # skip-лист («Не интересует») создаётся на TMDB с тем же именем,
    # это делает sync_skip_list, здесь не дублируем
    if instance.name == TmdbWritebackDispatch.SKIP_LIST_NAME:
        return
    ul_id = instance.pk
    transaction.on_commit(lambda ul_id=ul_id: TmdbWritebackDispatch.schedule_list_sync(ul_id))


@receiver(post_delete, sender=UserList)
def on_userlist_deleted(sender, instance, **kwargs):
    # если списка нет на TMDB — нечего удалять
    if not getattr(instance, "tmdb_list_id", None):
        return
    tmdb_id = instance.tmdb_list_id

    def _do(tmdb_id=tmdb_id):
        TmdbWritebackDispatch.schedule_list_delete(tmdb_id)

    transaction.on_commit(_do)