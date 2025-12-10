from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.urls import path, include
from django.contrib.auth.views import LoginView
from moviefilter import auth

urlpatterns = [
    path('login/', LoginView.as_view(template_name='login.html'), name='login'),
    path('logout/', auth.user_logout, name="logout"),
    path('admin/', admin.site.urls),
    path('', include('django.contrib.auth.urls')),
    path('', include('moviefilter.urls')),
    path('', include('tmdb_adapter.urls')),
    path('', include('core.urls')),
    path('', include('plex.urls')),
    path('', include('vault.urls')),
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
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)[0],
    # urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT),

    # add serve for Static during development
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
