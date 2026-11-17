from django.contrib.auth.models import User
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.utils import timezone


class Country(models.Model):
    """Модель стран производства"""
    name = models.CharField('Название', max_length=100, unique=True)
    code = models.CharField('Код', max_length=2, unique=True, blank=True)

    class Meta:
        verbose_name = 'Страна'
        verbose_name_plural = 'Страны'
        ordering = ['name']
        app_label = 'core'

    def __str__(self):
        return self.name


class AiEndpoint(models.Model):
    """
    Шаблон подключения к AI: OpenAI-совместимый `/chat/completions`.

    Здесь нет провайдерной логики: локальный сервер (Ollama / LM Studio /
    Lemonade / Unsloth) и облачный API (Groq и т.п.) — просто разные шаблоны.
    Один из шаблонов выбирается как основной в `UserPreferences.ai_endpoint`.
    """

    name = models.CharField("Название", max_length=100, unique=True)
    base_url = models.CharField("Base URL", max_length=300)
    model = models.CharField("Модель", max_length=200)
    api_key = models.CharField("API-ключ", max_length=300, blank=True)
    created_at = models.DateTimeField("Создан", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлён", auto_now=True)

    class Meta:
        verbose_name = "AI endpoint"
        verbose_name_plural = "AI endpoints"
        ordering = ["name"]
        app_label = "core"

    def __str__(self) -> str:
        return f"{self.name} ({self.model})"


class UserPreferences(models.Model):
    """
    Global Settings.
    Внимание! Я выпилил мультипользовательскую функциональность.
    Теперь настройки как бы едины для всех пользователей.
    Такой подход упрощает доступ к настройкам в разных частях приложения - им не требуется аутентифицированный юзер.
    Если понадобиться вернуться к поддерже мультипользователей - нужно передавать user по всей цепочке, особенно в parsing логику,
    и там брать настройки per user.

    Добавил удобный метод get(): теперь пользоваться настройками можно так:

        from core.models import UserPreferences

        preferences = UserPreferences.get()
        cookie_pass = preferences.cookie_pass
    """
    # Legacy-поле: настройки глобальные (singleton pk=1), а не per-user.
    # nullable, чтобы приложение могло стартовать на пустой базе до создания
    # первого пользователя (см. UserPreferences.get()).
    user = models.OneToOneField(
        User,
        unique=True,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='preferences',
    )
    last_scan = models.DateField(blank=True, null=True, default=timezone.now)
    last_scan_kinozal_id = models.PositiveIntegerField(blank=True, null=True)
    scan_from_page = models.PositiveSmallIntegerField(blank=True, null=True, default=0, help_text='Если длительный скан оборвался, можно его продолжить с этой страницы до последней.')

    scan_interval_minutes = models.PositiveIntegerField(
        blank=True,
        null=True,
        default=None,
        help_text='Интервал автоматического сканирования Kinozal в минутах. NULL — автозапуск выключен.',
    )
    scan_in_progress = models.BooleanField(
        default=False,
        help_text='Сейчас идёт сканирование (ручное или по расписанию). Взаимное исключение.',
    )
    scan_cancel_requested = models.BooleanField(
        default=False,
        help_text='Запрос отмены текущего сканирования. Используется для сканов по расписанию в HUEY-воркере.',
    )
    last_scheduled_run_at = models.DateTimeField(
        blank=True,
        null=True,
        help_text='Время завершения последнего сканирования по расписанию.',
    )
    last_scheduled_status = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        help_text='Результат последнего сканирования по расписанию: success/error/cancelled.',
    )

    countries = models.CharField(max_length=300, default='СССР, Россия, Индия')
    genres = models.CharField(max_length=300, default='Мюзикл')
    max_year = models.PositiveSmallIntegerField(default=1990)
    min_rating = models.FloatField(default=3.0)

    low_countries = models.CharField(max_length=300, default='Таиланд, Япония, Южная Корея, Китай')
    low_genres = models.CharField(max_length=300, default='Ужасы')
    low_max_year = models.PositiveSmallIntegerField(default=2000)
    low_min_rating = models.FloatField(default=5.0)

    plex_address = models.CharField(max_length=100, blank=True, null=True)
    plex_token = models.CharField(max_length=25, blank=True, null=True)

    cookie_pass = models.CharField(max_length=25, blank=True, null=True)
    cookie_uid = models.CharField(max_length=25, blank=True, null=True)
    kinozal_domain = models.CharField(max_length=50, blank=True, null=True)
    kinozal_mirrors = ArrayField(
        models.CharField(max_length=50),
        default=list,
        verbose_name="Зеркала kinozal",
        help_text="Список известных зеркал Kinozal (домены без https://).",
    )
    # DEPRECATED: старый hotfolder больше не используется. Оставлен в схеме,
    # чтобы не делать разрушительную миграцию; download flow работает через qBittorrent API.
    torrents_hotfolder = models.CharField(max_length=70, blank=True, null=True)

    qbt_url = models.CharField(
        'qBittorrent URL',
        max_length=300,
        blank=True,
        null=True,
        help_text='URL Web API qBittorrent, доступный с backend (в Docker — имя сервиса, не localhost).',
    )
    qbt_username = models.CharField('qBittorrent логин', max_length=200, blank=True, null=True)
    qbt_password = models.CharField('qBittorrent пароль', max_length=200, blank=True, null=True)
    # DEPRECATED: логин/пароль больше не используются (убраны из Preferences).
    # Оставлены в схеме, чтобы не делать разрушительную миграцию на production db.
    qbt_api_key = models.CharField(
        'qBittorrent API key',
        max_length=300,
        blank=True,
        null=True,
        help_text='API-ключ Web API qBittorrent 5.2+ (передаётся в заголовке Authorization: Bearer).',
    )
    qbt_skip_cert_verify = models.BooleanField(
        'Не проверять TLS-сертификат',
        default=False,
        help_text='Отключить проверку сертификата, если WebUI работает по HTTPS с самоподписанным сертификатом.',
    )
    torrents_backup_folder = models.CharField(
        'Папка backup .torrent',
        max_length=500,
        blank=True,
        null=True,
        help_text='Папка для хранения .torrent-файлов. В Docker обычно /app/backup_torrents.',
    )

    ignore_title = models.CharField(max_length=500, default='')

    tmdb_api_key = models.CharField(max_length=50, blank=True, null=True)
    omdb_api_key = models.CharField(max_length=50, blank=True, null=True)
    tavily_api_key = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        help_text='API-ключ Tavily для веб-поиска в умном поиске TMDB (не обязателен, если задан SearXNG URL)',
    )
    searxng_url = models.CharField(
        max_length=300,
        blank=True,
        null=True,
        help_text='URL локального SearXNG (/search). Если задан — веб-поиск идёт через него, Tavily-ключ не обязателен',
    )
    tmdb_v4_read_access_token = models.CharField(max_length=400, blank=True, null=True)
    tmdb_v4_authenticated_access_token = models.CharField(max_length=400, blank=True, null=True)

    tmdb_sync_enabled = models.BooleanField('Обработка очереди TMDB включена', default=False)
    tmdb_sync_stop_reason = models.CharField(
        max_length=500,
        blank=True,
        null=True,
        help_text='Причина автоматической остановки очереди TMDB sync (показывается красным тостом)',
    )

    tmdb_writeback_enabled = models.BooleanField(
        'Обратная синхронизация в TMDB',
        default=True,
        help_text='Автоматически записывать изменения статуса/оценки/избранного в TMDB',
    )
    tmdb_writeback_lists_enabled = models.BooleanField(
        'Синхронизация списков с TMDB',
        default=True,
        help_text='Синхронизировать пользовательские списки с TMDB Lists',
    )
    tmdb_lists_initialized = models.BooleanField(
        'TMDB списки инициализированы',
        default=False,
        help_text='Созданы ли все локальные UserList на TMDB (одноразово)',
    )
    tmdb_skip_list_id = models.PositiveIntegerField(
        'TMDB Skip List ID',
        null=True,
        blank=True,
        help_text='ID TMDB-листа "Не интересует" (зеркало системного статуса SKIP)',
    )
    tmdb_watched_list_id = models.PositiveIntegerField(
        'TMDB Watched List ID',
        null=True,
        blank=True,
        help_text='ID TMDB-листа "Просмотрено" (зеркало системного статуса WATCHED)',
    )

    ai_enabled = models.BooleanField(
        'AI включен',
        default=False,
        help_text='Использовать AI (выбранный AI endpoint) в фичах скана и Vault',
    )
    ai_endpoint = models.ForeignKey(
        'core.AiEndpoint',
        verbose_name='Выбранный AI endpoint',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='+',
        help_text='Основной шаблон подключения для AI-фич',
    )

    vault_image_cache_enabled = models.BooleanField(
        'Дисковый кеш изображений Vault',
        default=True,
        help_text=(
            'Вкл — постеры и фото Vault отдаются через /api/vault/images/... '
            'с дисковым кешем. Выкл — картинки грузятся напрямую с CDN TMDB '
            'и кешируются браузером.'
        ),
    )

    def save(self, *args, **kwargs):
        self.pk = 1  # всегда используем один и тот же primary key, потому что это БД-синглтон с одной записью
        super().save(*args, **kwargs)

    @classmethod
    def get(cls):
        obj, created = cls.objects.get_or_create(pk=1)
        return obj

    def get_normal_preferences(self) -> tuple[list[str], list[str], int, float]:
        countries = self.countries.split(', ') if self.countries else []
        genres = self.genres.split(', ') if self.genres else []
        return countries, genres, self.max_year, self.min_rating

    def get_low_priority_preferences(self) -> tuple[list[str], list[str], int, float]:
        countries = self.low_countries.split(', ') if self.low_countries else []
        genres = self.low_genres.split(', ') if self.low_genres else []
        return countries, genres, self.low_max_year, self.low_min_rating

    class Meta:
        verbose_name = "User Preferences"
        verbose_name_plural = "User Preferences"
