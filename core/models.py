from django.db import models


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
    Один из шаблонов выбирается активным в `UserPreferences.ai_endpoint`.
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
