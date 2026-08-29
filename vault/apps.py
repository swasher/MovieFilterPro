from django.apps import AppConfig


class VaultConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'vault'

    verbose_name = 'Фильмотека'

    def ready(self):
        import vault.signals  # noqa: F401

        # одноразовая инициализация списков TMDB — без кнопки, без entrypoint.sh
        # не лезем в БД тут (migrate!), просто шедулим задачу — она сама проверит флаг/токен
        try:
            from vault.tasks import tmdb_lists_init

            tmdb_lists_init.schedule(delay=10)
        except Exception:
            pass
