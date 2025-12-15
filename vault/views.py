from django.http import HttpResponse
from django.shortcuts import render, redirect

from tmdbapis import TMDbAPIs, FindResults, Video, Movie, TVShow
from tmdbapis.api3 import API3
from tmdbapis.api4 import API4
from tmdbapis.exceptions import Authentication, NotFound

from moviefilter.models import UserPreferences
from tmdb_adapter.client_singleton import get_tmdb_client, get_tmdb_config


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


def search_movies_dropdown(request):
    print('\nSearch Movies')

    tmdb = get_tmdb_client()

    query = request.POST.get('query', '').strip()

    # Логика для отладки
    print(f"Поисковый запрос: '{query}'")

    try:
        movies = tmdb.movie_search(query)
    except NotFound:
        movies = None

    print('FOUND:', len(movies if movies is not None else []))

    return HttpResponse(render(request, "partial/search_dropdown.html", context={'movies': movies}))


def search_movies_fullpage(request):
    print('\nSearch Movies')

    tmdb = get_tmdb_client()

    query = request.POST.get('query', '').strip()

    # Логика для отладки
    print(f"Поисковый запрос: '{query}'")

    try:
        movies = tmdb.movie_search(query)
    except NotFound:
        movies = None

    print('FOUND:', len(movies) if movies is not None else 0)

    config = get_tmdb_config()
    imageurl = config.secure_base_image_url
    poster_size = 'w154'

    return HttpResponse(render(request, "partial/search_grid.html", context={'movies': movies, 'imageurl': "/".join([imageurl, poster_size])}))


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


def list_get_movies(request, list_id):
    tmdb = get_tmdb_client()

    movies_in_list = tmdb.list(list_id=list_id).results

    config = get_tmdb_config()
    imageurl = config.secure_base_image_url
    poster_size = 'w154'

    return HttpResponse(render(request, "partial/search_grid.html",
                               context={'movies': movies_in_list, 'imageurl': "/".join([imageurl, poster_size])}))


def list_create(request, list_name):
    tmdb = get_tmdb_client()
    ...


def list_delete(request, list_id):
    tmdb = get_tmdb_client()
    ...

def list_rename(request, list_id, new_name):
    tmdb = get_tmdb_client()
    new_name = request.GET.get('new_name')
    """
        <!-- GET запрос -->
        <a href="{% url 'list_rename' list_id=some_list_id %}?new_name=НовоеИмя">
          Переименовать
        </a>
        
        <!-- POST запрос -->
        <form method="post" action="{% url 'list_rename' list_id=some_list_id %}">
          {% csrf_token %}
          <input type="text" name="new_name" value="НовоеИмя">
          <button type="submit">Переименовать</button>
        </form>    
    """
    ...


