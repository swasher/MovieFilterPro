from django.utils import timezone
from django.db import models
from django.contrib.auth.models import User

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
