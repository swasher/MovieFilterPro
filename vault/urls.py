from django.urls import path
from vault import views

app_name = "vault"

urlpatterns = [
    path('vault/', views.vault, name='vault'),
    path('search_movies_dropdown/', views.search_movies_dropdown, name='search_movies_dropdown'),
    path('search_movies_fullpage/', views.search_movies_fullpage, name='search_movies_fullpage'),
    path('movie/<int:movie_id>/', views.movie, name='movie'),
    path('list_get_movies/<int:list_id>/', views.list_get_movies, name='list_get_movies'),

    path('list_create/<str:list_name>', views.list_create, name='list_create'),
    path('list_delete/<int:list_id>/', views.list_delete, name='list_delete'),
    path('list_rename/<int:list_id>/', views.list_rename, name='list_rename'),


]
