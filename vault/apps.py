from django.apps import AppConfig


class VaultConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'vault'

    verbose_name = 'Фильмотека'

    # Я пока не стал использовать сигналы
    # def ready(self):
    #     """
    #     Импортируем сигналы при инициализации приложения.
    #     Это необходимо для автоматического создания системных списков.
    #     """
    #     import vault.signals  # noqa: F401
