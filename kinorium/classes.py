from dataclasses import dataclass


@dataclass
class KinoriumMovieDataClass:
    title: str = None
    original_title: str = None
    year: str = None
    status: int = None
