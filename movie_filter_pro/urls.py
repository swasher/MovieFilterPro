from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.urls import path, include
from core.api import api as core_api
from vault import views as vault_views
from vault.api import api as vault_api
from moviefilter.api import api as kinozal_api


urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/core/', core_api.urls),
    path('api/vault/', vault_api.urls),
    path('api/kinozal/', kinozal_api.urls),
    # Legacy unprefixed Vault routes kept for compatibility (old links/bookmarks).
    path('movies/', vault_views.MovieListView.as_view()),
    path('movies/<slug:slug>/', vault_views.MovieDetailView.as_view()),
    path('genre/<slug:slug>/', vault_views.MovieByGenreView.as_view()),
    path('search/', vault_views.SearchView.as_view()),
    path('person/<int:pk>/', vault_views.PersonDetailView.as_view()),
    path('my-lists/', vault_views.MyListsView.as_view()),
    path('list/system/<str:system_list>/', vault_views.SystemListDetailView.as_view()),
    path('list/<int:pk>/', vault_views.ListDetailView.as_view()),
    path('list/create/', vault_views.ListCreateView.as_view()),
    path('list/<int:pk>/edit/', vault_views.ListUpdateView.as_view()),
    path('list/<int:pk>/delete/', vault_views.ListDeleteView.as_view()),
    path('htmx/toggle-status/', vault_views.toggle_movie_status),
    path('htmx/rate-movie/', vault_views.rate_movie),
    path('htmx/remove-rating/', vault_views.remove_rating),
    path('htmx/add-to-list/', vault_views.add_to_list),
    path('htmx/remove-from-list/', vault_views.remove_from_list),
    path('htmx/toggle-list-privacy/', vault_views.toggle_list_privacy),
    path('', include('moviefilter.urls')),
    path('', include('tmdb_adapter.urls')),
    path('', include('core.urls')),
    path('vault/', include('vault.urls')),
    path('', include('plex.urls')),
    path('', include('tmdb.urls')),
    path('', include('kinorium.urls')),
    path('', include('web_logger.urls')),
    path('', include('kinozal_scan.urls')),
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
