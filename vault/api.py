from ninja import NinjaAPI, Schema

from vault.models import Movie


class MovieOut(Schema):
    id: int
    title: str
    original_title: str | None = None
    year: int | None = None
    slug: str


api = NinjaAPI(title="Vault API", version="1.0")


@api.get("/movies", response=list[MovieOut])
def list_movies(request, limit: int = 50):
    qs = (
        Movie.objects.filter(status=Movie.Status.RELEASED)
        .order_by("-year", "title")[:limit]
    )
    return [
        MovieOut(
            id=movie.id,
            title=movie.title,
            original_title=movie.original_title,
            year=movie.year,
            slug=movie.slug,
        )
        for movie in qs
    ]
