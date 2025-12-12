from django.http import HttpResponse
from django.shortcuts import render, redirect

from tmdbapis import TMDbAPIs, FindResults, Video, Movie, TVShow
from tmdbapis.api3 import API3
from tmdbapis.api4 import API4
from tmdbapis.exceptions import Authentication, NotFound

from moviefilter.models import UserPreferences
from tmdb_adapter.client_singleton import get_tmdb_client


def vault(request):
    pref = UserPreferences.get()
    tmdb_api_key = pref.tmdb_api_key
    tmdb_v4_authenticated_access_token = pref.tmdb_v4_authenticated_access_token

    tmdb = TMDbAPIs(tmdb_api_key, v4_access_token=tmdb_v4_authenticated_access_token, language='RU')

    try:
        movie_lists = tmdb.created_lists()
    except Authentication:
        return redirect("/tmdb_auth/")

    # user_movies_lists = []
    # for spisok in movie_lists.results:
    #     user_movies_lists.append(spisok.name)

    return render(request, 'vault.html', context={'movie_lists': movie_lists})


def search_movies(request):
    print('\nSearch Movies')

    tmdb = get_tmdb_client()

    query = request.POST.get('query', '').strip()

    # Логика для отладки
    print(f"Поисковый запрос: '{query}'")

    try:
        movies = tmdb.movie_search(query)
    except NotFound:
        movies = None

    print(movies)

    return HttpResponse(render(request, "partial/search-responce.html", context={'movies': movies}))


def movie(request, movie_id):
    tmdb = get_tmdb_client()
    details = tmdb.movie(movie_id=movie_id)

    context = {
        "id": details.id,
        "imdb_id": details.imdb_id,
        "title": details.title,
        "original_title": details.original_title,
        "tagline": details.tagline,
        "overview": details.overview,
        "poster_path": details.poster_path,
        "genres": details.genres,
        "countries": details.countries,
        "release_date": details.release_date,
    }

    return HttpResponse(render(request, "partial/_movie_details.html", context=context))
