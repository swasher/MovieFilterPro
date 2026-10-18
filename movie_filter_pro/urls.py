from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.urls import path, include
from core.api import api as core_api
from vault.api import api as vault_api
from moviefilter.api import api as kinozal_api
from plex.api import api as plex_api
from django.http import HttpResponse
from django.urls import re_path


urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/core/', core_api.urls),
    path('api/vault/', vault_api.urls),
    path('api/kinozal/', kinozal_api.urls),
    path('api/plex/', plex_api.urls),
    path('', include('core.urls')),
]


if settings.ENABLE_BROWSER_RELOAD:
    # django_browser_reload APP
    urlpatterns += path("__reload__/", include("django_browser_reload.urls")),
if settings.ENABLE_DEBUG_TOOLBAR:
    # add debug_toolbar APP
    urlpatterns += [
        path('__debug__/', include('debug_toolbar.urls')),
    ]
if settings.DEBUG:
    # add serve for Media during development
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

    # add serve for Static during development
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

def frontend_fallback(request):
    index_file = settings.FRONT_BUILD_DIR / 'index.html'
    return HttpResponse(index_file.read_text(encoding='utf-8'))

if not settings.DEBUG:
    urlpatterns += [
        re_path(r'^.*$', frontend_fallback),
    ]
