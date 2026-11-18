from django.db import models


class TasteProfile(models.Model):
    """
    Профиль вкусов человека — текст вида rita_profile.md:
    жанры, что нравится/не нравится, ограничения.

    Профилей может быть несколько (по одному на человека).
    """

    name = models.CharField("Название", max_length=100, unique=True)
    content = models.TextField("Профиль вкусов", blank=True)
    created_at = models.DateTimeField("Создан", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлён", auto_now=True)

    class Meta:
        verbose_name = "Профиль вкусов"
        verbose_name_plural = "Профили вкусов"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class PromptTemplate(models.Model):
    """
    Системный промпт (singleton, pk=1).

    Пустой `content` означает «использовать встроенный текст по умолчанию».
    """

    content = models.TextField("Текст промпта", blank=True)
    updated_at = models.DateTimeField("Обновлён", auto_now=True)

    class Meta:
        verbose_name = "Системный промпт"
        verbose_name_plural = "Системный промпт"

    def save(self, *args, **kwargs):
        self.pk = 1  # singleton, как UserPreferences
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return "Системный промпт"


class MoviePrediction(models.Model):
    """
    Один прогон AI-предсказания для пары (фильм, профиль вкусов).

    Храним и вход (снапшот карточки), и результат, чтобы модалка могла показать
    последний прогон без повторного обращения к LLM.
    """

    class Status(models.TextChoices):
        RUNNING = "running", "Выполняется"
        DONE = "done", "Готово"
        ERROR = "error", "Ошибка"

    class Verdict(models.TextChoices):
        WATCH = "watch", "Брать"
        MAYBE = "maybe", "Может быть"
        SKIP = "skip", "Не брать"

    movie = models.ForeignKey(
        "vault.Movie",
        verbose_name="Фильм",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="ai_predictions",
    )
    rss_movie = models.ForeignKey(
        "moviefilter.MovieRSS",
        verbose_name="Раздача Kinozal",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="ai_predictions",
    )
    taste_profile = models.ForeignKey(
        TasteProfile,
        verbose_name="Профиль вкусов",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="predictions",
    )
    status = models.CharField(
        "Статус",
        max_length=10,
        choices=Status.choices,
        default=Status.RUNNING,
    )
    score = models.PositiveSmallIntegerField("Оценка 1–10", null=True, blank=True)
    verdict = models.CharField(
        "Вердикт",
        max_length=10,
        choices=Verdict.choices,
        blank=True,
    )
    confidence = models.FloatField("Уверенность", null=True, blank=True)
    result_text = models.TextField("Результат (текст)", blank=True)
    input_snapshot = models.JSONField("Вход для движка", null=True, blank=True)
    raw_response = models.JSONField("Сырой ответ движка", null=True, blank=True)
    error = models.TextField("Ошибка", blank=True)
    model_name = models.CharField("Модель", max_length=200, blank=True)
    duration_ms = models.PositiveIntegerField("Длительность, мс", null=True, blank=True)
    created_at = models.DateTimeField("Создан", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлён", auto_now=True)

    class Meta:
        verbose_name = "AI-предсказание"
        verbose_name_plural = "AI-предсказания"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(movie__isnull=False, rss_movie__isnull=True)
                    | models.Q(movie__isnull=True, rss_movie__isnull=False)
                ),
                name="ai_predict_prediction_single_source",
            )
        ]

    def __str__(self) -> str:
        if self.movie_id:
            subject = self.movie.title
        elif self.rss_movie_id:
            subject = self.rss_movie.title
        else:
            subject = "без фильма"
        return f"{subject} — {self.taste_profile or 'без профиля'} ({self.get_status_display()})"
