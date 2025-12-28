# services/movie_status_service.py

from django.db import transaction
from django.core.exceptions import ValidationError
from typing import Optional
from ..models import Movie, UserList, UserListMovie, Rating


class MovieStatusService:
    """Сервис для управления статусами фильмов и пользовательскими списками"""

    # Взаимоисключающие статусы
    MUTUALLY_EXCLUSIVE_STATUSES = ['watched', 'will_watch', 'wont_watch']

    @staticmethod
    def get_user_system_lists(user):
        """Получить все системные списки пользователя"""
        return {
            list_obj.list_type: list_obj
            for list_obj in UserList.objects.filter(
                user=user,
                is_system=True
            )
        }

    @staticmethod
    def get_movie_status(user, movie):
        """
        Получить текущий статус фильма у пользователя
        Возвращает: dict с информацией о статусах
        """
        user_lists = UserList.objects.filter(
            user=user,
            list_movies__movie=movie
        ).values_list('list_type', flat=True)

        try:
            rating = Rating.objects.get(user=user, movie=movie)
        except Rating.DoesNotExist:
            rating = None

        return {
            'in_watched': 'watched' in user_lists,
            'in_will_watch': 'will_watch' in user_lists,
            'in_wont_watch': 'wont_watch' in user_lists,
            'in_favorites': 'favorites' in user_lists,
            'rating': rating.rating if rating else None,
            'custom_lists': list(UserList.objects.filter(
                user=user,
                list_type='custom',
                list_movies__movie=movie
            ).values('id', 'name'))
        }

    @classmethod
    @transaction.atomic
    def add_to_list(cls, user, movie, list_type, note=''):
        """
        Добавить фильм в список с учетом взаимоисключающей логики
        """
        # Получаем нужный список
        try:
            user_list = UserList.objects.get(user=user, list_type=list_type)
        except UserList.DoesNotExist:
            raise ValidationError(f"Список типа {list_type} не найден")

        # Если это взаимоисключающий статус, удаляем из других таких статусов
        if list_type in cls.MUTUALLY_EXCLUSIVE_STATUSES:
            other_statuses = [s for s in cls.MUTUALLY_EXCLUSIVE_STATUSES if s != list_type]
            other_lists = UserList.objects.filter(
                user=user,
                list_type__in=other_statuses
            )
            UserListMovie.objects.filter(
                user_list__in=other_lists,
                movie=movie
            ).delete()

        # Добавляем в список (или обновляем, если уже есть)
        list_movie, created = UserListMovie.objects.get_or_create(
            user_list=user_list,
            movie=movie,
            defaults={'note': note}
        )

        if not created and note:
            list_movie.note = note
            list_movie.save()

        return list_movie

    @classmethod
    @transaction.atomic
    def remove_from_list(cls, user, movie, list_type):
        """Удалить фильм из списка"""
        try:
            user_list = UserList.objects.get(user=user, list_type=list_type)
            UserListMovie.objects.filter(
                user_list=user_list,
                movie=movie
            ).delete()
            return True
        except UserList.DoesNotExist:
            return False

    @classmethod
    @transaction.atomic
    def toggle_list(cls, user, movie, list_type):
        """
        Переключить статус фильма в списке (добавить/удалить)
        Возвращает: True если добавлен, False если удален
        """
        try:
            user_list = UserList.objects.get(user=user, list_type=list_type)
            exists = UserListMovie.objects.filter(
                user_list=user_list,
                movie=movie
            ).exists()

            if exists:
                cls.remove_from_list(user, movie, list_type)
                return False
            else:
                cls.add_to_list(user, movie, list_type)
                return True
        except UserList.DoesNotExist:
            raise ValidationError(f"Список типа {list_type} не найден")

    @classmethod
    @transaction.atomic
    def rate_movie(cls, user, movie, rating_value):
        """
        Поставить оценку фильму
        Автоматически перемещает фильм из "Буду смотреть" в "Просмотрено"
        """
        if not (1 <= rating_value <= 10):
            raise ValidationError("Оценка должна быть от 1 до 10")

        # Создаем или обновляем оценку
        rating, created = Rating.objects.update_or_create(
            user=user,
            movie=movie,
            defaults={'rating': rating_value}
        )

        # Автоматически перемещаем в "Просмотрено"
        cls.add_to_list(user, movie, 'watched')

        return rating

    @classmethod
    @transaction.atomic
    def remove_rating(cls, user, movie):
        """
        Удалить оценку фильма
        НЕ удаляет фильм из "Просмотрено" автоматически
        """
        try:
            rating = Rating.objects.get(user=user, movie=movie)
            rating.delete()
            return True
        except Rating.DoesNotExist:
            return False

    @classmethod
    @transaction.atomic
    def toggle_favorites(cls, user, movie):
        """Добавить/удалить из избранного (независимый статус)"""
        return cls.toggle_list(user, movie, 'favorites')

    @classmethod
    def get_list_movies(cls, user, list_type, order_by='-added_at'):
        """Получить все фильмы из списка определенного типа"""
        try:
            user_list = UserList.objects.get(user=user, list_type=list_type)
            return Movie.objects.filter(
                in_lists__user_list=user_list
            ).order_by(order_by)
        except UserList.DoesNotExist:
            return Movie.objects.none()