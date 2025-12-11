from django.urls import path
from . import auth, views

app_name = 'tmdb'

urlpatterns = [

    # auth
    path("tmdb/auth/", auth.tmdb_auth, name="auth"),
    path("tmdb/auth/create_auth_link/", auth.tmdb_start, name="start"),
    path("tmdb/auth/approve_link/", auth.tmdb_approve, name="approve"),
    path("tmdb/auth/logout/", auth.tmdb_logout, name="logout"),



    # Страницы списков
    # path("tmdb/lists/", views.list_list, name="list_list"),
    # path("tmdb/lists/create/", views.list_create, name="list_create"),
    # path("tmdb/lists/<int:list_id>/", views.list_detail, name="list_detail"),
    #
    # # Операции со списками
    # path("tmdb/lists/<int:list_id>/rename/", views.list_rename, name="list_rename"),
    # path("tmdb/lists/<int:list_id>/delete/", views.list_delete, name="list_delete"),
    #
    # # Фильмы внутри списка (HTML фрагменты для HTMX)
    # path("tmdb/lists/<int:list_id>/items/", views.list_items_partial, name="list_items"),
    # path("tmdb/lists/<int:list_id>/items/add/", views.list_item_add, name="list_item_add"),
    # path(
    #     "tmdb/lists/<int:list_id>/items/<int:item_id>/delete/",
    #     views.list_item_delete,
    #     name="list_item_delete"
    # ),
]
