from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
from ..models import UserList, UserMovie


class MovieStatusService:
    """Сервис для управления статусом просмотра, избранным и оценкой фильма."""

    STATUS_KEY_TO_WATCH_STATUS = {
        'watched': UserMovie.WatchStatus.WATCHED,
        'will_watch': UserMovie.WatchStatus.PLAN,
        'wont_watch': UserMovie.WatchStatus.SKIP,
    }
    WATCH_STATUS_TO_STATUS_KEY = {value: key for key, value in STATUS_KEY_TO_WATCH_STATUS.items()}

    @classmethod
    def _get_or_create_user_movie(cls, user, movie):
        user_movie, _ = UserMovie.objects.get_or_create(user=user, movie=movie)
        return user_movie

    @classmethod
    def _cleanup_user_movie(cls, user_movie: UserMovie):
        if user_movie.watch_status is None and not user_movie.is_favorite and user_movie.rating is None:
            user_movie.delete()

    @staticmethod
    def get_movie_status(user, movie):
        """
        Получить текущий статус фильма у пользователя
        Возвращает: dict с информацией о статусах
        """
        user_movie = UserMovie.objects.filter(user=user, movie=movie).first()
        watch_status = user_movie.watch_status if user_movie else None

        return {
            'in_watched': watch_status == UserMovie.WatchStatus.WATCHED,
            'in_will_watch': watch_status == UserMovie.WatchStatus.PLAN,
            'in_wont_watch': watch_status == UserMovie.WatchStatus.SKIP,
            'in_favorites': bool(user_movie and user_movie.is_favorite),
            'rating': user_movie.rating if user_movie else None,
            'note': user_movie.note if user_movie else '',
            'custom_lists': list(UserList.objects.filter(
                user=user,
                list_movies__movie=movie
            ).values('id', 'name'))
        }

    @classmethod
    @transaction.atomic
    def set_status(cls, user, movie, status_key):
        """Включить системный статус (watch_status или favorites)."""
        user_movie = cls._get_or_create_user_movie(user, movie)

        if status_key in cls.STATUS_KEY_TO_WATCH_STATUS:
            user_movie.watch_status = cls.STATUS_KEY_TO_WATCH_STATUS[status_key]
            if status_key in ('will_watch', 'wont_watch'):
                user_movie.rating = None
                user_movie.watched_at = None
            user_movie.save(update_fields=['watch_status', 'rating', 'watched_at', 'updated_at'])
            return user_movie

        if status_key == 'favorites':
            user_movie.is_favorite = True
            user_movie.save(update_fields=['is_favorite', 'updated_at'])
            return user_movie

        raise ValidationError(f"Неизвестный статус: {status_key}")

    @classmethod
    @transaction.atomic
    def unset_status(cls, user, movie, status_key):
        """Выключить системный статус (watch_status или favorites)."""
        user_movie = UserMovie.objects.filter(user=user, movie=movie).first()
        if not user_movie:
            return False

        changed = False
        if status_key in cls.STATUS_KEY_TO_WATCH_STATUS:
            if user_movie.watch_status == cls.STATUS_KEY_TO_WATCH_STATUS[status_key]:
                user_movie.watch_status = None
                changed = True
        elif status_key == 'favorites':
            if user_movie.is_favorite:
                user_movie.is_favorite = False
                changed = True
        else:
            raise ValidationError(f"Неизвестный статус: {status_key}")

        if changed:
            user_movie.save(update_fields=['watch_status', 'is_favorite', 'updated_at'])
            cls._cleanup_user_movie(user_movie)

        return changed

    @classmethod
    @transaction.atomic
    def toggle_status(cls, user, movie, status_key):
        """
        Переключить системный статус фильма (добавить/удалить)
        Возвращает: True если добавлен, False если удален
        """
        user_movie = UserMovie.objects.filter(user=user, movie=movie).first()

        if status_key in cls.STATUS_KEY_TO_WATCH_STATUS:
            target = cls.STATUS_KEY_TO_WATCH_STATUS[status_key]
            if user_movie and user_movie.watch_status == target:
                cls.unset_status(user, movie, status_key)
                return False
            cls.set_status(user, movie, status_key)
            return True

        if status_key == 'favorites':
            if user_movie and user_movie.is_favorite:
                cls.unset_status(user, movie, status_key)
                return False
            cls.set_status(user, movie, status_key)
            return True

        raise ValidationError(f"Неизвестный статус: {status_key}")

    @classmethod
    @transaction.atomic
    def rate_movie(cls, user, movie, rating_value):
        """
        Поставить оценку фильму
        Автоматически перемещает фильм из "Буду смотреть" в "Просмотрено"
        """
        if not (1 <= rating_value <= 10):
            raise ValidationError("Оценка должна быть от 1 до 10")

        user_movie = cls._get_or_create_user_movie(user, movie)
        user_movie.rating = rating_value
        user_movie.watched_at = timezone.localdate()
        user_movie.watch_status = UserMovie.WatchStatus.WATCHED
        user_movie.save(update_fields=['rating', 'watched_at', 'watch_status', 'updated_at'])
        return user_movie

    @classmethod
    @transaction.atomic
    def remove_rating(cls, user, movie):
        """
        Удалить оценку фильма
        НЕ удаляет фильм из "Просмотрено" автоматически
        """
        user_movie = UserMovie.objects.filter(user=user, movie=movie).first()
        if not user_movie or user_movie.rating is None:
            return False

        user_movie.rating = None
        user_movie.watched_at = None
        user_movie.save(update_fields=['rating', 'watched_at', 'updated_at'])
        cls._cleanup_user_movie(user_movie)
        return True

    @classmethod
    @transaction.atomic
    def set_note(cls, user, movie, text):
        """Сохранить заметку/комментарий пользователя к фильму."""
        user_movie = cls._get_or_create_user_movie(user, movie)
        user_movie.note = (text or "").strip()
        user_movie.save(update_fields=['note', 'updated_at'])
        if not user_movie.note:
            cls._cleanup_user_movie(user_movie)
        return user_movie

    @classmethod
    @transaction.atomic
    def clear_note(cls, user, movie):
        """Удалить заметку/комментарий пользователя к фильму."""
        user_movie = UserMovie.objects.filter(user=user, movie=movie).first()
        if not user_movie or not user_movie.note:
            return user_movie
        user_movie.note = ""
        user_movie.save(update_fields=['note', 'updated_at'])
        cls._cleanup_user_movie(user_movie)
        return user_movie

    @classmethod
    def get_system_lists_counts(cls, user):
        user_movies = UserMovie.objects.filter(user=user)
        return {
            'watched': user_movies.filter(watch_status=UserMovie.WatchStatus.WATCHED).count(),
            'will_watch': user_movies.filter(watch_status=UserMovie.WatchStatus.PLAN).count(),
            'wont_watch': user_movies.filter(watch_status=UserMovie.WatchStatus.SKIP).count(),
            'favorites': user_movies.filter(is_favorite=True).count(),
        }
