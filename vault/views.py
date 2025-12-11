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

    # movies_list = [
    #     "Интерстеллар",
    #     "Начало",
    #     "Побег из Шоушенка",
    #     "Криминальное чтиво",
    #     "Форрест Гамп",
    #     "Бойцовский клуб",
    #     "Матрица",
    #     "Список Шиндлера",
    #     "Леон",
    #     "1+1",
    #     "Зеленая миля",
    #     "Властелин колец: Возвращение короля",
    #     "Темный рыцарь",
    #     "Крестный отец",
    #     "Пианист",
    #     "Гладиатор",
    #     "Титаник",
    #     "Паразиты",
    #     "Джентльмены",
    #     "Джокер",
    #     "Остров проклятых",
    #     "Семь",
    #     "Молчание ягнят",
    #     "Большой куш",
    #     "Карты, деньги, два ствола",
    #     "Достучаться до небес",
    #     "Игры разума",
    #     "Шерлок Холмс",
    #     "По соображениям совести",
    #     "Зверополис"
    # ]
    #
    # search_string = search_string.lower()
    # result = []
    #
    # for movie in movies_list:
    #     if search_string in movie.lower():
    #         result.append(movie)

    tmdb = get_tmdb_client()

    return result
