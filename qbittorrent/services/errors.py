from __future__ import annotations


class QbtError(Exception):
    """Ошибка qBittorrent-интеграции с кодом для API."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        hint: str | None = None,
        status_code: int = 502,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint
        self.status_code = status_code
