from django.db import models


class BestfilmsEntry(models.Model):
    """Одна строка рейтинга bestfilmsof для пары (год, жанр).

    `genre=""` означает «весь год без жанра» (конвенция `_norm_genre()`:
    снаружи `None`, в БД `""`, чтобы unique-констрейнт работал).
    """

    year = models.IntegerField(db_index=True)
    genre = models.CharField(max_length=32, db_index=True)
    imdb_id = models.CharField(max_length=16)
    tmdb_id = models.IntegerField()
    position = models.IntegerField()
    score = models.FloatField(null=True, blank=True)
    title = models.CharField(max_length=255)
    # Рейтинги / голоса — всё приходит внутри ответа bestfilmsof.
    imdb_rating = models.FloatField(null=True, blank=True)
    imdb_votes = models.IntegerField(null=True, blank=True)
    tomato_meter = models.IntegerField(null=True, blank=True)
    metascore = models.IntegerField(null=True, blank=True)
    # Касса (в API есть только gross, бюджета нет).
    gross = models.BigIntegerField(null=True, blank=True)
    gross_scope = models.CharField(max_length=16, null=True, blank=True)
    # Награды.
    oscar_wins = models.IntegerField(default=0)
    oscar_nominations = models.IntegerField(default=0)
    best_picture = models.BooleanField(default=False)
    award_points = models.IntegerField(default=0)
    awards_wins = models.IntegerField(null=True, blank=True)
    awards_nominations = models.IntegerField(null=True, blank=True)
    other_awards = models.JSONField(default=list, blank=True)
    # Компоненты скора для локального пересчёта («weigh the score your way»):
    # score = 100 * sum(w_i * c_i) / sum(w_i), c_i = компонент или *_fallback.
    comp_imdb = models.FloatField(null=True, blank=True)
    comp_critics = models.FloatField(null=True, blank=True)
    comp_awards = models.FloatField(null=True, blank=True)
    comp_boxoffice = models.FloatField(null=True, blank=True)
    fb_critics = models.FloatField(null=True, blank=True)
    fb_boxoffice = models.FloatField(null=True, blank=True)

    class Meta:
        verbose_name = "Строка рейтинга bestfilmsof"
        verbose_name_plural = "Строки рейтинга bestfilmsof"
        constraints = [
            models.UniqueConstraint(
                fields=["year", "genre", "imdb_id"],
                name="uniq_bestfilms_entry",
            ),
        ]
        indexes = [
            models.Index(fields=["year", "genre"]),
        ]
        ordering = ["position"]

    def __str__(self):
        return f"{self.year}/{self.genre} #{self.position} {self.title}"


class BestfilmsCache(models.Model):
    """Кеш метаданных TMDB, общий для всех списков (год, жанр).

    Базовые поля — английские (приходят бесплатно внутри ответа bestfilmsof).
    Русские (`title_ru`/`overview_ru`) добираются из коллекции Vault или TMDB.
    При чтении приоритет: коллекция Vault -> этот кеш -> значения entry.
    """

    tmdb_id = models.IntegerField(primary_key=True)
    title = models.CharField(max_length=255)
    overview = models.TextField(null=True, blank=True)
    title_ru = models.CharField(max_length=255, null=True, blank=True)
    overview_ru = models.TextField(null=True, blank=True)
    poster_path = models.CharField(max_length=255, null=True, blank=True)
    release_date = models.DateField(null=True, blank=True)
    fetched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Кеш метаданных bestfilmsof"
        verbose_name_plural = "Кеш метаданных bestfilmsof"

    def __str__(self):
        return f"{self.tmdb_id} {self.title}"


class BestfilmsSync(models.Model):
    """Состояние синхронизации набора данных.

    `key` — стабильный уникальный ключ без NULL-ловушек Postgres:
    "list:{year}:{genre}" для списков, "summary:{genre}" для жанровых сводок.
    Строка создаётся при первом обращении; параллельные синки защищены
    `run_token` (claim -> задача -> сверка токена).
    """

    class Status(models.TextChoices):
        IDLE = "idle", "Готово"
        RUNNING = "running", "Выполняется"
        ERROR = "error", "Ошибка"

    key = models.CharField(max_length=64, unique=True)
    year = models.IntegerField(null=True, blank=True, db_index=True)
    genre = models.CharField(max_length=32, db_index=True)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.IDLE
    )
    run_token = models.CharField(max_length=32, blank=True, default="")
    synced_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    worker_started_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Когда воркер фактически начал выполнять задачу (None — ещё в очереди).",
    )
    finished_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True, default="")
    last_stats = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = "Состояние синхронизации bestfilmsof"
        verbose_name_plural = "Состояния синхронизации bestfilmsof"

    def __str__(self):
        return f"{self.key}: {self.status} ({self.synced_at})"


class BestfilmsGenreYear(models.Model):
    """Сводка по жанру: количество фильмов и топ-фильм для каждого года.

    Источник: GET /api/movies/genre/{genre} (один запрос, 100+ строк по годам).
    `genre=""` здесь не встречается: сводка всегда по конкретному жанру.
    """

    year = models.IntegerField(db_index=True)
    genre = models.CharField(max_length=32, db_index=True)
    count = models.IntegerField(default=0)
    top_imdb_id = models.CharField(max_length=16)
    top_tmdb_id = models.IntegerField()
    top_title = models.CharField(max_length=255)
    top_score = models.FloatField(null=True, blank=True)

    class Meta:
        verbose_name = "Год жанровой сводки bestfilmsof"
        verbose_name_plural = "Годы жанровых сводок bestfilmsof"
        constraints = [
            models.UniqueConstraint(
                fields=["year", "genre"],
                name="uniq_bestfilms_genreyear",
            ),
        ]
        ordering = ["-year"]

    def __str__(self):
        return f"{self.genre} {self.year}: {self.count} films, top {self.top_title}"
