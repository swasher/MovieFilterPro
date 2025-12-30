from django.urls import path
from . import views

app_name = 'vault'

urlpatterns = [
    # Главная страница и список фильмов
    path('', views.MovieListView.as_view(), name='movie_list'),
    path('movies/', views.MovieListView.as_view(), name='movie_list'),
    path('movies/<slug:slug>/', views.MovieDetailView.as_view(), name='movie_detail'),
    path('genre/<slug:slug>/', views.MovieByGenreView.as_view(), name='movie_by_genre'),

    # Поиск
    path('search/', views.SearchView.as_view(), name='search'),

    # Персоны
    path('person/<int:pk>/', views.PersonDetailView.as_view(), name='person_detail'),

    # Пользовательские списки
    path('my-lists/', views.MyListsView.as_view(), name='my_lists'),
    path('list/<int:pk>/', views.ListDetailView.as_view(), name='list_detail'),
    path('list/create/', views.ListCreateView.as_view(), name='list_create'),
    path('list/<int:pk>/edit/', views.ListUpdateView.as_view(), name='list_edit'),
    path('list/<int:pk>/delete/', views.ListDeleteView.as_view(), name='list_delete'),

    # HTMX эндпоинты для быстрых действий
    path('htmx/toggle-status/', views.toggle_movie_status, name='htmx_toggle_status'),
    path('htmx/rate-movie/', views.rate_movie, name='htmx_rate_movie'),
    path('htmx/remove-rating/', views.remove_rating, name='htmx_remove_rating'),
    path('htmx/add-to-list/', views.add_to_list, name='htmx_add_to_list'),
    path('htmx/remove-from-list/', views.remove_from_list, name='htmx_remove_from_list'),
    path('htmx/toggle-list-privacy/', views.toggle_list_privacy, name='htmx_toggle_list_privacy'),

    # Отзывы
    path('movie/<slug:slug>/review/', views.CreateReviewView.as_view(), name='create_review'),
    path('htmx/like-review/<int:pk>/', views.like_review, name='htmx_like_review'),
]
