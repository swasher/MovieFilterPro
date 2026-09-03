from __future__ import annotations

import threading
import time


class TmdbRateLimiter:
    """Глобальный лимитер TMDB: не чаще 2 запросов в секунду (0.5 сек между вызовами).

    Один на весь процесс (WEB и HUEY воркер — разные процессы, каждый свой лимитер,
    но в каждом процессе — общий для read и write). Потокобезопасен.
    """

    MIN_INTERVAL = 0.5  # 2 req/sec, запас в 2 раза от лимита TMDB 4/sec
    _lock = threading.Lock()
    _last_call = 0.0

    @classmethod
    def wait(cls) -> None:
        with cls._lock:
            now = time.monotonic()
            elapsed = now - cls._last_call
            if elapsed < cls.MIN_INTERVAL:
                time.sleep(cls.MIN_INTERVAL - elapsed)
            cls._last_call = time.monotonic()
