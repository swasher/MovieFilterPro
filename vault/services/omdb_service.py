from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation
from typing import TypedDict

import requests
from django.conf import settings

logger = logging.getLogger("vault.omdb_sync")


class OMDBRatings(TypedDict, total=False):
    imdb_rating: Decimal | None
    imdb_votes: int | None
    rotten_tomatoes: int | None
    metacritic: int | None
    raw: dict


# ------------------------------------ #
#          APPLICATION LAYER           #
# ------------------------------------ #


class OMDBService:
    """Клиент OMDB API для получения рейтингов по IMDb ID.

    Использует OMDB_API_KEY из settings (.env).
    Читает массив Ratings, а не верхнеуровневые поля.
    """

    BASE_URL = "https://www.omdbapi.com/"

    @classmethod
    def fetch_ratings(cls, imdb_id: str) -> OMDBRatings | None:
        imdb_id = (imdb_id or "").strip()
        if not imdb_id:
            return None

        api_key = getattr(settings, "OMDB_API_KEY", "") or ""
        api_key = api_key.strip()
        if not api_key:
            logger.warning("OMDB_API_KEY not configured, skip omdb fetch for %s", imdb_id)
            return None

        try:
            resp = requests.get(
                cls.BASE_URL,
                params={"i": imdb_id, "apikey": api_key},
                timeout=10,
            )
        except Exception as exc:
            logger.warning("OMDB request failed for %s: %s", imdb_id, exc, exc_info=True)
            return None

        if resp.status_code != 200:
            logger.warning("OMDB non-200 for %s: %s %s", imdb_id, resp.status_code, resp.text[:300])
            return None

        try:
            data = resp.json()
        except Exception:
            logger.warning("OMDB invalid JSON for %s", imdb_id)
            return None

        if data.get("Response") == "False":
            logger.info("OMDB Response=False for %s: %s", imdb_id, data.get("Error"))
            return None

        ratings_raw = data.get("Ratings") or []
        parsed = cls._parse_ratings_array(ratings_raw)
        parsed["imdb_votes"] = cls._parse_imdb_votes(data.get("imdbVotes"))
        parsed["raw"] = data
        logger.info(
            "OMDB fetched %s: imdb=%s votes=%s rt=%s meta=%s",
            imdb_id,
            parsed.get("imdb_rating"),
            parsed.get("imdb_votes"),
            parsed.get("rotten_tomatoes"),
            parsed.get("metacritic"),
        )
        return parsed

    # ------------------------------------ #
    #            DOMAIN LAYER              #
    # ------------------------------------ #

    @staticmethod
    def _parse_ratings_array(ratings: list[dict]) -> OMDBRatings:
        """Парсит массив Ratings из OMDB.

        Пример:
          [ {"Source": "Internet Movie Database", "Value": "7.0/10"},
            {"Source": "Rotten Tomatoes", "Value": "87%"},
            {"Source": "Metacritic", "Value": "68/100"} ]
        """
        imdb_rating: Decimal | None = None
        rotten: int | None = None
        meta: int | None = None

        for entry in ratings or []:
            source = (entry.get("Source") or "").strip()
            value = (entry.get("Value") or "").strip()
            if not source or not value:
                continue

            source_lower = source.lower()
            if source_lower == "internet movie database":
                imdb_rating = OMDBService._parse_imdb_value(value)
            elif source_lower == "rotten tomatoes":
                rotten = OMDBService._parse_percent(value)
            elif source_lower == "metacritic":
                meta = OMDBService._parse_metacritic_value(value)

        return {
            "imdb_rating": imdb_rating,
            "rotten_tomatoes": rotten,
            "metacritic": meta,
        }

    @staticmethod
    def _parse_imdb_value(value: str) -> Decimal | None:
        """'7.0/10' -> Decimal('7.0')"""
        try:
            # может быть "7.0/10" или "N/A"
            if "/" in value:
                value = value.split("/")[0].strip()
            if value.upper() == "N/A" or not value:
                return None
            dec = Decimal(value)
            if dec < 0 or dec > Decimal("99.9"):
                return None
            return dec.quantize(Decimal("0.1"))
        except (InvalidOperation, ValueError, AttributeError):
            return None

    @staticmethod
    def _parse_imdb_votes(value: str | None) -> int | None:
        """'124,409' -> 124409, 'N/A' -> None"""
        try:
            if value is None:
                return None
            cleaned = str(value).strip().replace(",", "").strip()
            if not cleaned or cleaned.upper() == "N/A":
                return None
            iv = int(cleaned)
            if iv < 0:
                return None
            return iv
        except (ValueError, AttributeError):
            return None

    @staticmethod
    def _parse_percent(value: str) -> int | None:
        """'87%' -> 87"""
        try:
            cleaned = value.strip().rstrip("%").strip()
            if cleaned.upper() == "N/A" or not cleaned:
                return None
            iv = int(cleaned)
            if 0 <= iv <= 100:
                return iv
            return None
        except (ValueError, AttributeError):
            return None

    @staticmethod
    def _parse_metacritic_value(value: str) -> int | None:
        """'68/100' -> 68"""
        try:
            if "/" in value:
                value = value.split("/")[0].strip()
            if value.upper() == "N/A" or not value:
                return None
            iv = int(value)
            if 0 <= iv <= 100:
                return iv
            return None
        except (ValueError, AttributeError):
            return None
