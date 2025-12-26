from django.urls import path
from kinorium import views
from kinorium import htmx_views


app_name = "kinorium"

urlpatterns = [
    path('table/', views.table, name='table'),
]

htmx = [
    path('kinorium_table_data/', htmx_views.kinorium_table_data, name='table_data'),
    path('kinorium_search/<int:kinozal_id>', htmx_views.kinorium_search, name='search'),
]

urlpatterns += htmx
