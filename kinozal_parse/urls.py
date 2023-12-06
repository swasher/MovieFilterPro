from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.urls import path, include
from django.contrib.auth.views import LoginView


urlpatterns = [
    path('login/', LoginView.as_view(template_name='login.html'), name='login'),
    path('admin/', admin.site.urls),
    path('', include('django.contrib.auth.urls')),
    path('', include('kinozal.urls')),
]

# For development only!
# if settings.DEBUG:
#     urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
if settings.DEBUG:
    # django_browser_reload APP
    urlpatterns += path("__reload__/", include("django_browser_reload.urls")),

    # add debug_toolbar APP
    # urlpatterns += [
    #     path('__debug__/', include('debug_toolbar.urls')),
    # ]

    # add serve for Media during development
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)[0],
    # urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT),

    # add serve for Static during development
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)