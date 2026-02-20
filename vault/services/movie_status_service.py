from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
from ..models import Movie, UserList, UserMovie


class MovieStatusService:
    """Сервис для управления статусом просмотра, избранным и оценкой фильма."""

    LIST_TYPE_TO_WATCH_STATUS = {
        'watched': UserMovie.WatchStatus.WATCHED,
        'will_watch': UserMovie.WatchStatus.PLAN,
        'wont_watch': UserMovie.WatchStatus.SKIP,
    }
    WATCH_STATUS_TO_LIST_TYPE = {value: key for key, value in LIST_TYPE_TO_WATCH_STATUS.items()}

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
    def add_to_list(cls, user, movie, list_type):
        """Добавить фильм в системный список-статус (теперь через флаги UserMovie)."""
        user_movie = cls._get_or_create_user_movie(user, movie)

        if list_type in cls.LIST_TYPE_TO_WATCH_STATUS:
            user_movie.watch_status = cls.LIST_TYPE_TO_WATCH_STATUS[list_type]
            user_movie.save(update_fields=['watch_status', 'updated_at'])
            return user_movie

        if list_type == 'favorites':
            user_movie.is_favorite = True
            user_movie.save(update_fields=['is_favorite', 'updated_at'])
            return user_movie

        raise ValidationError(f"Неизвестный тип списка: {list_type}")

    @classmethod
    @transaction.atomic
    def remove_from_list(cls, user, movie, list_type):
        """Удалить фильм из системного списка-статуса (через флаги UserMovie)."""
        user_movie = UserMovie.objects.filter(user=user, movie=movie).first()
        if not user_movie:
            return False

        changed = False
        if list_type in cls.LIST_TYPE_TO_WATCH_STATUS:
            if user_movie.watch_status == cls.LIST_TYPE_TO_WATCH_STATUS[list_type]:
                user_movie.watch_status = None
                changed = True
        elif list_type == 'favorites':
            if user_movie.is_favorite:
                user_movie.is_favorite = False
                changed = True
        else:
            raise ValidationError(f"Неизвестный тип списка: {list_type}")

        if changed:
            user_movie.save(update_fields=['watch_status', 'is_favorite', 'updated_at'])
            cls._cleanup_user_movie(user_movie)

        return changed

    @classmethod
    @transaction.atomic
    def toggle_list(cls, user, movie, list_type):
        """
        Переключить статус фильма в списке (добавить/удалить)
        Возвращает: True если добавлен, False если удален
        """
        user_movie = UserMovie.objects.filter(user=user, movie=movie).first()

        if list_type in cls.LIST_TYPE_TO_WATCH_STATUS:
            target = cls.LIST_TYPE_TO_WATCH_STATUS[list_type]
            if user_movie and user_movie.watch_status == target:
                cls.remove_from_list(user, movie, list_type)
                return False
            cls.add_to_list(user, movie, list_type)
            return True

        if list_type == 'favorites':
            if user_movie and user_movie.is_favorite:
                cls.remove_from_list(user, movie, list_type)
                return False
            cls.add_to_list(user, movie, list_type)
            return True

        raise ValidationError(f"Неизвестный тип списка: {list_type}")

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
        user_movie.rated_at = timezone.localdate()
        user_movie.watch_status = UserMovie.WatchStatus.WATCHED
        user_movie.save(update_fields=['rating', 'rated_at', 'watch_status', 'updated_at'])
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
        user_movie.rated_at = None
        user_movie.save(update_fields=['rating', 'rated_at', 'updated_at'])
        cls._cleanup_user_movie(user_movie)
        return True

    @classmethod
    @transaction.atomic
    def toggle_favorites(cls, user, movie):
        """Добавить/удалить из избранного (независимый статус)"""
        return cls.toggle_list(user, movie, 'favorites')

    @classmethod
    def get_list_movies(cls, user, list_type, order_by='-added_at'):
        """Получить фильмы из системного списка-статуса по list_type."""
        if order_by == '-added_at':
            order_by = '-user_movies__created_at'

        if list_type in cls.LIST_TYPE_TO_WATCH_STATUS:
            return Movie.objects.filter(
                user_movies__user=user,
                user_movies__watch_status=cls.LIST_TYPE_TO_WATCH_STATUS[list_type],
            ).order_by(order_by)

        if list_type == 'favorites':
            return Movie.objects.filter(
                user_movies__user=user,
                user_movies__is_favorite=True,
            ).order_by(order_by)

        return Movie.objects.none()

    @classmethod
    def get_system_lists_counts(cls, user):
        user_movies = UserMovie.objects.filter(user=user)
        return {
            'watched': user_movies.filter(watch_status=UserMovie.WatchStatus.WATCHED).count(),
            'will_watch': user_movies.filter(watch_status=UserMovie.WatchStatus.PLAN).count(),
            'wont_watch': user_movies.filter(watch_status=UserMovie.WatchStatus.SKIP).count(),
            'favorites': user_movies.filter(is_favorite=True).count(),
        }
