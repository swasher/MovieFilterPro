from django.apps import AppConfig


class VaultConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'vault'

    verbose_name = 'Фильмотека'

    def ready(self):
        import vault.signals  # noqa: F401
