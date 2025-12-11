from django.urls import path
from vault import views

urlpatterns = [
    path('vault/', views.vault, name='vault'),
    path('search_movies/', views.search_movies, name='search_movies'),
]
