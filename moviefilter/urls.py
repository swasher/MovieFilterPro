from django.urls import path
from moviefilter import views
from moviefilter import htmx_views
from moviefilter import auth

# app_name = "moviefilter"

urlpatterns = [
    path('', views.movies, name='movies'),
    # DEPRECATED path('movies_low/', views.movies_low, name='movies_low'),
    # DEPRECATED path('parse_kinorium_csv/', views.parse_kinorium_csv, name='parse_kinorium_csv'),
    path('plex/', views.plex, name='plex'),
    path('kinorium/', views.kinorium, name='kinorium'),
    path('preferences/', views.user_preferences_update, name='user_preferences'),
    # path('order_print/<orderid>', views.order_print, name='order_print'),
]

htmx = [
    path('scan/', views.scan, name='scan'),
    path('reset_rss/', htmx_views.reset_rss, name='reset_rss'),
    path('ignore/<pk>', views.ignore_movie, name='ignore'),
    path('kinorium_table_data/', htmx_views.kinorium_table_data, name='kinorium_table_data'),
    path('get_rss_table_data/<str:prio>', htmx_views.rss_table_data, name='get_rss_table_data'),
]

urlpatterns += htmx

