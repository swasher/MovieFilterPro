from django.shortcuts import render, redirect

from tmdbapis import TMDbAPIs, FindResults, Video, Movie, TVShow
from tmdbapis.api3 import API3
from tmdbapis.api4 import API4
from tmdbapis.exceptions import Authentication

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


def search_movies(request, search_string):

    tmdb = get_tmdb_client()
    result = tmdb.movie_search(search_string)

    print(result)

    return result
