from plexapi.server import PlexServer
from .models import UserPreferences
from django.contrib.auth.decorators import login_required
from django.shortcuts import render


def plex_section(request):
    user = request.user
    prefs = UserPreferences.objects.get(user=user)
    baseurl = prefs.plex_address
    token = prefs.plex_token
    try:
        plexserver = PlexServer(baseurl, token)
    except:
        return render(request, 'plex.html', {'error': 'Plex Server not found: '+baseurl})

    sections_obj_list = plexserver.library.sections()
    # [<MovieSection:5:Erotic>, <MovieSection:3:Review>, <MovieSection:1:Фильмы>, <ShowSection:2:Сериалы>, <MusicSection:4:Музыка>]
    sections = [x.title for x in sections_obj_list]

    return render(request, 'plex_sections.html', {'sections': sections})


@login_required
def plex(request, section: str):
    user = request.user
    prefs = UserPreferences.objects.get(user=user)
    baseurl = prefs.plex_address
    token = prefs.plex_token
    try:
        plexserver = PlexServer(baseurl, token)
    except:
        return render(request, 'plex.html', {'error': 'Plex Server not found: '+baseurl})

    # список секций
    # plex.library._sectionsByTitle

    # m = plex.library.section('Фильмы')
    m = plexserver.library.section(section)

    movies = m.search()
    for mov in movies:
        print(mov)
    return render(request, 'plex.html', {'movies': movies})