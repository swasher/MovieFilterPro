from django.db import models


class Torrent(models.Model):
    """Раздача qBittorrent, связанная с фильмом Vault."""

    movie = models.ForeignKey(
        'vault.Movie',
        verbose_name='Фильм Vault',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='torrents',
    )
    info_hash = models.CharField('Info hash', max_length=64, unique=True)
    name = models.CharField('Название раздачи', max_length=500)
    source_url = models.URLField('Страница раздачи', max_length=1000, blank=True)
    torrent_file = models.CharField(
        'Файл .torrent',
        max_length=500,
        blank=True,
        help_text='Относительный путь внутри папки backup из Preferences.',
    )
    save_path = models.CharField('Save path qBittorrent', max_length=1000, blank=True)
    content_path = models.CharField('Путь к содержимому', max_length=1000, blank=True)
    last_error = models.TextField('Последняя ошибка', blank=True)
    created_at = models.DateTimeField('Создано', auto_now_add=True)
    updated_at = models.DateTimeField('Обновлено', auto_now=True)

    class Meta:
        verbose_name = 'Раздача qBittorrent'
        verbose_name_plural = 'Раздачи qBittorrent'
        ordering = ['-created_at', '-id']
        indexes = [
            models.Index(fields=['movie', '-created_at']),
        ]

    def __str__(self):
        return f'{self.name} ({self.info_hash[:8]})'


class TorrentEvent(models.Model):
    """Персистентный журнал действий qBittorrent-интеграции."""

    class Level(models.TextChoices):
        INFO = 'info', 'Info'
        WARNING = 'warning', 'Warning'
        ERROR = 'error', 'Error'

    torrent = models.ForeignKey(
        Torrent,
        verbose_name='Раздача',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='events',
    )
    movie = models.ForeignKey(
        'vault.Movie',
        verbose_name='Фильм Vault',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='torrent_events',
    )
    level = models.CharField('Уровень', max_length=20, choices=Level, default=Level.INFO, db_index=True)
    event_type = models.CharField('Тип события', max_length=100, db_index=True)
    message = models.TextField('Сообщение')
    payload = models.JSONField('Payload', null=True, blank=True)
    created_at = models.DateTimeField('Создано', auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = 'Событие qBittorrent'
        verbose_name_plural = 'События qBittorrent'
        ordering = ['-created_at', '-id']
        indexes = [
            models.Index(fields=['event_type', '-created_at']),
        ]

    def __str__(self):
        return f'{self.event_type}: {self.message[:80]}'
