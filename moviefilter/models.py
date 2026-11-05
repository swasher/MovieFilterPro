from django.utils import timezone
from django.db import models
from django.contrib.auth.models import User
from django.contrib.postgres.fields import ArrayField

from movie_filter_pro.settings import HIGH, LOW, DEFER, SKIP, WAIT_TRANS, TRANS_FOUND

"""
Логика такая:
- парсер парсит moviefilter, находит фильм
- проверяет, есть ли фильм в базе
- добавляет этот фильм в базу при необходимости со статусом "НОВЫЙ"
- смотрит в эксель (или куда-то) от kinorium, и если там есть такой фильм, то соотв. меняет его статус.
"""


class Genre(models.Model):
    name = models.CharField(max_length=30)


class MovieRSS(models.Model):
    """
    Это фильмы с кинозала, которые ждут реакции юзера.
    Если пользователь нажал Ignore на фильме, он остается в базе с меткой Ignore. В дальнейшем, при сканированнии,
    сканер знает, что такие фильмы показывать пользователю не нужно.
    """

    PRIORITY = (
        (LOW, 'Низкий'),
        (HIGH, 'Обычный'),
        (DEFER, 'Отложено'),
        (SKIP, 'Отказ'),
        (WAIT_TRANS, 'Жду дубляж'),
        (TRANS_FOUND, 'Найден дубляж или ПМ'),
    )

    class Meta:
        ordering = ['scanned_at', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['title', 'original_title', 'year'],
                name='unique_movierss_movie_identity',
            ),
        ]

    # Похоже, что этот флаг не используется нигде
    # POSSIBLE DEPRECATED
    ignored_deprecated = models.BooleanField(default=False, help_text='Пользователь не хочет, чтобы этот фильм снова появился в ленте')

    low_priority_deprecated = models.BooleanField(default=False)
    priority = models.PositiveSmallIntegerField(choices=PRIORITY, verbose_name='Priority')
    kinozal_id = models.PositiveIntegerField()
    title = models.CharField(max_length=200)
    original_title = models.CharField(max_length=200)
    year = models.CharField(max_length=9, help_text='Год может быть представлен как диапазон: 1982-1994')
    tracker_date = models.DateField(help_text='Дата создания раздачи на трекере Kinozal')
    scanned_at = models.DateTimeField(default=timezone.now, db_index=True, help_text='Дата и время попадания записи в базу при сканировании')
    dubbed = models.BooleanField(blank=True, null=True, help_text='Раздача имеет дубляж или ПМ. Нужно для передачи этой информации из сканера в чекер.')

    imdb_id = models.CharField(max_length=15, blank=True, null=True)
    imdb_rating = models.FloatField(blank=True, null=True)

    kinopoisk_id = models.PositiveIntegerField(blank=True, null=True)
    kinopoisk_rating = models.FloatField(blank=True, null=True)

    genres = models.TextField(blank=True, null=True)
    countries = models.TextField(blank=True, null=True)

    director = models.TextField(blank=True, null=True)
    actors = models.TextField(blank=True, null=True)
    plot = models.TextField(blank=True, null=True)
    translate = models.CharField(max_length=300, blank=True, null=True)
    poster = models.CharField(max_length=500)

    kinorium_id = models.PositiveIntegerField(blank=True, null=True, help_text='На данный момент не используется, потому что мы не можем получить ID из Кинориума')
    kinorium_partial_match = models.BooleanField(default=False, blank=True, null=True)

    @property
    def genres_as_list(self):
        return self.genres.split(', ')

    @property
    def countries_as_list(self):
        return self.countries.split(', ')

    @property
    def actors_as_list(self):
        return self.actors.split(', ')

    @property
    def director_as_list(self):
        return self.director.split(', ')

    def __str__(self):
        name = self.original_title if self.original_title else self.title
        return f"{name} - {self.year}"


class Kinorium(models.Model):
    """
    Эта таблица не имеет внешнего ключа к Moveies. Это просто копия CSV из Кинориума для более быстрого поиска(можно
    было бы просто по CSV искать)

    Поля kinozal_title и kinozal_original_title и kinozal_year нужны для того, чтобы в случае, если данные Кинозала
    не совпадают с данными Кинориума, пользователь мог нажать 'Fix it', и в базе будет записаны актуальные данные
    Кинозала. По ним в след раз и будет происходить поиск.

    Каждый раз, когда пользователь обновляет базу, она не перезаписывается, а только обновляются статусы.

    Если в таблице отсутствует original_title, то оригинальное название было на русском (возможно есть и другие причины)

    Чтобы проанализировать данные kinorium'а, нам нужно два списка - "Списки фильмов" и "Оценки и просмотры".
    В первом будут фильмы, которые "Буду смотреть" и "Не буду смотреть". У просмотренных фильмов нет назначенного
    списка, поэтому они вообще отсутствуют в этой таблице. Их мы извлекаем из "Оценки и просмотры".

    Если фильм присутствует в списке "Оценки и просмотры", значит он просмотрен. Он может как иметь мой рейтинг,
    так и быть без рейтинга.
    """

    UNKNOWN = 0
    WATCHED = 1
    WILL_WATCH = 2
    DECLINED = 3

    STATUS = (
        (UNKNOWN, 'Новый'),
        (WATCHED, 'Просмотрен'),
        (WILL_WATCH, 'Буду смотреть'),  # значит, уже скачан
        (DECLINED, 'Не буду смотреть'),
    )

    title = models.CharField(max_length=200)
    original_title = models.CharField(max_length=200, blank=True)
    year = models.PositiveSmallIntegerField()

    status = models.PositiveSmallIntegerField(choices=STATUS, verbose_name='Статус', default=UNKNOWN)

    def __str__(self):
        return f'{self.title} - {self.year}'


class UserPreferences(models.Model):
    """
    Global Settings.
    Внимание! Я выпилил мультипользовательскую функциональность.
    Теперь настройки как бы едины для всех пользователей.
    Такой подход упрощает доступ к настройкам в разных частях приложения - им не требуется аутентифицированный юзер.
    Если понадобиться вернуться к поддерже мультипользователей - нужно передавать user по всей цепочке, особенно в parsing логику,
    и там брать настройки per user.

    Добавил удобный метод get(): теперь пользоваться настройками можно так:

        from moviefilter.models import UserPreferences

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
        'Локальный AI включен',
        default=False,
        help_text='Использовать локальный AI для будущих фич',
    )
    ai_base_url = models.CharField(
        max_length=300,
        blank=True,
        null=True,
        help_text='Base URL OpenAI-совместимого сервера, например http://localhost:11434/v1',
    )
    ai_api_key = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        help_text='API-ключ, если сервер его требует (для локальных обычно не нужен)',
    )
    ai_model = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text='Имя модели, например qwen2.5:7b',
    )
    groq_api_key = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        help_text='API-ключ Groq для облачных LLM',
    )
    groq_model = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text='Имя Groq-модели, например llama-3.3-70b-versatile',
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


class Country(models.Model):
    """
    Нужно потому, что в Kinozale в одном поле и страны и студии. С помощью списка известных стран будем отделять
     одни от других.
    """
    name = models.CharField(max_length=60, unique=True)

    def __str__(self):
        return self.name


# Сколько последних запусков сканирования хранить в ScanRun/ScanLogEntry.
# Более старые запуски (и их лог-строки) удаляются после завершения нового запуска.
SCAN_HISTORY_MAX_RUNS = 200


class ScanRun(models.Model):
    """Сводка одного запуска сканирования Kinozal (ручного или по расписанию)."""

    class Trigger(models.TextChoices):
        MANUAL = "manual", "Manual"
        SCHEDULED = "scheduled", "Scheduled"

    class Status(models.TextChoices):
        RUNNING = "running", "Running"
        SUCCESS = "success", "Success"
        ERROR = "error", "Error"
        CANCELLED = "cancelled", "Cancelled"
        RATE_LIMITED = "rate_limited", "Rate limited"
        CLOUDFLARE_BLOCKED = "cloudflare_blocked", "Cloudflare blocked"

    trigger = models.CharField('Триггер', max_length=20, choices=Trigger, db_index=True)
    status = models.CharField('Статус', max_length=30, choices=Status, default=Status.RUNNING, db_index=True)
    started_at = models.DateTimeField('Начало', auto_now_add=True, db_index=True)
    finished_at = models.DateTimeField('Завершение', null=True, blank=True)
    scan_to_date = models.DateField('Сканировать до даты', null=True, blank=True)
    new_movies_count = models.PositiveIntegerField('Новых фильмов', default=0)
    error_type = models.CharField('Тип ошибки', max_length=50, null=True, blank=True)
    error_message = models.TextField('Сообщение об ошибке', blank=True)
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name='scan_runs',
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = 'Запуск сканирования'
        verbose_name_plural = 'Запуски сканирования'
        ordering = ['-started_at', '-id']

    def __str__(self):
        return f'{self.get_trigger_display()} {self.started_at:%d.%m.%y %H:%M}'

    @classmethod
    def prune_history(cls, max_runs: int = SCAN_HISTORY_MAX_RUNS) -> None:
        """Удаляет запуски сверх лимита (каскадно их лог-строки)."""
        ids_to_keep = list(
            cls.objects.order_by("-started_at", "-id")
            .values_list("id", flat=True)[:max_runs]
        )
        cls.objects.exclude(id__in=ids_to_keep).delete()


class ScanLogEntry(models.Model):
    """Построчная запись лога сканирования, привязанная к запуску."""

    class Level(models.TextChoices):
        INFO = "info", "Info"
        ERROR = "error", "Error"

    run = models.ForeignKey(ScanRun, on_delete=models.CASCADE, related_name='entries', db_index=True)
    level = models.CharField('Уровень', max_length=10, choices=Level, default=Level.INFO, db_index=True)
    message = models.TextField('Сообщение')
    created_at = models.DateTimeField('Создано', auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = 'Запись лога сканирования'
        verbose_name_plural = 'Записи лога сканирования'
        ordering = ['created_at', 'id']
        indexes = [
            models.Index(fields=['run', 'created_at'], name='mf_scanlog_run_created_idx'),
        ]

    def __str__(self):
        return f'[{self.run_id}] {self.message[:80]}'
