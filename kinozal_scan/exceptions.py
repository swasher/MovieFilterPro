class ScanCancelled(Exception):
    """Custom exception raised when scanning cancelling task is called by user from browser (clicked Cancel button)"""
    pass


class DetailsFetchError(Exception):
    """Custom exception for critical errors during movie details fetching."""
    pass


class KinozalRateLimitError(RuntimeError):
    """
    Сайт Kinozal ответил 429 Too Many Requests.

    Скан останавливается сразу после первого 429: ретраи в забаненное окно
    только продлевают блокировку. Прогресс уже сохранён чекпойнтом
    (UserPreferences.last_scan_kinozal_id), так что следующий запуск продолжит
    с того же места.
    """
    pass
