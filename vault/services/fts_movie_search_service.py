from __future__ import annotations

import re

from django.db import connection


class FTSMovieSearchService:
    """Full-text search over Movie via SQLite FTS5 (case-insensitive, incl. Cyrillic)."""

    FTS_TABLE = "movie_fts"
    _TOKEN_RE = re.compile(r"\w+", re.UNICODE)

    # ------------------------------------ #
    #          APPLICATION LAYER           #
    # ------------------------------------ #

    @classmethod
    def is_available(cls) -> bool:
        return connection.vendor == "sqlite"

    @classmethod
    def build_match_query(cls, query: str, include_plot: bool = True) -> str:
        tokens = cls._TOKEN_RE.findall(query or "")
        match_expr = " ".join(f"{token}*" for token in tokens)
        if not match_expr:
            return ""
        if include_plot:
            return match_expr
        return f"{{title original_title}} : {match_expr}"

    @classmethod
    def search(cls, query: str, include_plot: bool = True) -> list[int]:
        """Возвращает id фильмов, отсортированные по релевантности FTS5."""
        if not cls.is_available():
            return []
        match_query = cls.build_match_query(query, include_plot=include_plot)
        if not match_query:
            return []
        sql = f"SELECT rowid FROM {cls.FTS_TABLE} WHERE {cls.FTS_TABLE} MATCH %s ORDER BY rank"
        with connection.cursor() as cursor:
            cursor.execute(sql, (match_query,))
            return [row[0] for row in cursor.fetchall()]