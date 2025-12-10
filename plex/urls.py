from django.urls import path
from . import views


# app_name = "moviefilter"

urlpatterns = [
    path('plex/<section>', views.plex, name='plex'),
    path('plex_section/', views.plex_section, name='plex_section'),
]

