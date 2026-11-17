from django.db import models


class PlexLibraryItem(models.Model):
    """Снимок элемента библиотеки Plex (фильм или сериал).

    Мягкая связность: строка не является «умной» связкой, а зеркалом того,
    что реально лежит на Plex-сервере. `vault_movie` заполняется при
    синхронизации простым сравнением GUID-идентификаторов (tmdb/imdb/tvdb).
    Строки, исчезнувшие из Plex, удаляются при следующей синхронизации —
    отдельной операции «удалить связь» не существует.
    """

    class MediaType(models.TextChoices):
        MOVIE = 'movie', 'Фильм'
        SHOW = 'show', 'Сериал'

    rating_key = models.CharField('Plex ratingKey', max_length=32, unique=True)
    media_type = models.CharField('Тип', max_length=10, choices=MediaType, db_index=True)
    section = models.CharField('Секция Plex', max_length=200, blank=True, default='', db_index=True)

    title = models.CharField('Название', max_length=500)
    original_title = models.CharField('Оригинальное название', max_length=500, blank=True, default='')
    year = models.PositiveIntegerField('Год', null=True, blank=True)

    file_path = models.CharField('Путь к файлу', max_length=1000, blank=True, default='')
    file_name = models.CharField('Имя файла', max_length=255, blank=True, default='')

    # Сырые GUID-ы Plex (imdb://tt..., tmdb://..., tvdb://...) — для отладки и
    # повторного матчинга без обращения к серверу.
    guids = models.JSONField('Сырые GUID', default=list, blank=True)
    guid_tmdb = models.CharField('TMDB ID', max_length=16, blank=True, default='', db_index=True)
    guid_imdb = models.CharField('IMDb ID', max_length=16, blank=True, default='', db_index=True)
    guid_tvdb = models.CharField('TVDB ID', max_length=16, blank=True, default='', db_index=True)

    vault_movie = models.ForeignKey(
        'vault.Movie',
        verbose_name='Фильм Vault',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='plex_items',
    )
    match_method = models.CharField('Метод матчинга', max_length=10, blank=True, default='')

    last_seen_at = models.DateTimeField('Последний раз в Plex')
    created_at = models.DateTimeField('Создано', auto_now_add=True)
    updated_at = models.DateTimeField('Обновлено', auto_now=True)

    class Meta:
        verbose_name = 'Элемент библиотеки Plex'
        verbose_name_plural = 'Элементы библиотеки Plex'
        ordering = ['title', 'id']
        indexes = [
            models.Index(fields=['vault_movie', 'media_type'], name='plexitem_movie_type_idx'),
        ]

    def __str__(self):
        return f"{self.title} ({self.year}) [{self.section}]"


class PlexLinkState(models.Model):
    """Состояние синхронизации связи Vault <-> Plex (синглтон, pk=1)."""

    is_syncing = models.BooleanField('Идёт синхронизация', default=False)
    last_synced_at = models.DateTimeField('Последняя успешная синхронизация', null=True, blank=True)
    last_attempt_at = models.DateTimeField('Последняя попытка синхронизации', null=True, blank=True)
    items_total = models.PositiveIntegerField('Элементов в Plex', default=0)
    matched_total = models.PositiveIntegerField('Связано с Vault', default=0)
    unmatched_total = models.PositiveIntegerField('Не связано с Vault', default=0)
    last_error = models.TextField('Последняя ошибка', blank=True, default='')
    updated_at = models.DateTimeField('Обновлено', auto_now=True)

    class Meta:
        verbose_name = 'Состояние связи Plex'
        verbose_name_plural = 'Состояние связи Plex'

    def __str__(self):
        return f"PlexLinkState (last_synced={self.last_synced_at})"

    @classmethod
    def get(cls) -> 'PlexLinkState':
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
