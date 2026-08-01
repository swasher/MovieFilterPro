from decimal import InvalidOperation

from django.core.management.base import BaseCommand
from django.db import transaction

from vault import models as v


class Command(BaseCommand):
    help = 'Удаляет ВСЕ данные только из моделей приложения vault (без затрагивания других приложений).'
    chunk_size = 1000

    def _delete_in_chunks(self, model):
        total_deleted = 0
        db_alias = model.objects.db
        pk_qs = model.objects.order_by('pk').values_list('pk', flat=True)

        while True:
            batch = list(pk_qs[:self.chunk_size])
            if not batch:
                break
            qs = model.objects.filter(pk__in=batch)
            try:
                deleted, _ = qs.delete()
                total_deleted += deleted
            except InvalidOperation:
                # В SQLite могут встречаться битые decimal-значения.
                # _raw_delete удаляет строки без чтения и конвертации полей.
                if model.__name__ == 'Movie':
                    for m2m in model._meta.local_many_to_many:
                        through = m2m.remote_field.through
                        source_fk_name = m2m.m2m_field_name()
                        through.objects.filter(**{f'{source_fk_name}__in': batch})._raw_delete(db_alias)
                total_deleted += qs._raw_delete(db_alias)

        return total_deleted

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING('ВНИМАНИЕ: полная очистка данных приложения vault!'))

        # Порядок важен для соблюдения ограничений внешних ключей.
        # Сначала удаляем модели, которые ссылаются на другие (многие-ко-многим, пользовательский контент),
        # затем уже основные сущности.
        to_purge = [
            # Пользовательский контент и связи
            v.UserMovie,
            v.FavoritePerson,
            v.UserListMovie,
            v.MoviePerson,

            # События связи приложений
            v.VaultConnectionEvent,

            # Иерархия сериалов
            v.Episode,
            v.Season,

            # Основные модели (после удаления зависимостей)
            v.UserList,
            v.Movie,
            v.Person,
            v.Genre,
        ]

        with transaction.atomic():
            for model in to_purge:
                deleted = self._delete_in_chunks(model)
                self.stdout.write(f'  ✓ {model.__name__}: удалено {deleted}')

        self.stdout.write(self.style.SUCCESS('\n✅ Данные vault очищены. Таблицы других приложений не тронуты.'))
