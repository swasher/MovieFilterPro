from dataclasses import dataclass
import datetime
from typing import Any, List


@dataclass
class KinozalMovie:
    kinozal_id: int = None
    title: str = None
    original_title: str = None
    year: str = None
    date_added: datetime.date = None
    dubbed: bool = None
    imdb_id: str = None
    imdb_rating: float = None
    kinopoisk_id: int = None
    kinopoisk_rating: float = None
    genres: str = None
    countries: str = None
    director: str = None
    actors: List[str] = None
    plot: str = None
    translate: str = None
    poster: str = None
    priority: bool = None
    kinorium_partial_match: bool = None


@dataclass
class KinozalSearch:
    id: int = None
    header: str = None
    size: str = None
    seed: int = None
    peer: int = None
    created: str = None
    link: str = None
    is_4k: bool = None
    is_sdr: bool = None
