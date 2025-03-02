from django.urls import path
from moviefilter import views
from moviefilter import plex
from moviefilter import htmx_views

# app_name = "moviefilter"

urlpatterns = [
    path('', views.rss, name='rss'),
    # DEPRECATED path('movies_low/', views.movies_low, name='movies_low'),
    # DEPRECATED path('parse_kinorium_csv/', views.parse_kinorium_csv, name='parse_kinorium_csv'),

    path('plex/<section>', plex.plex, name='plex'),
    path('plex_section/', plex.plex_section, name='plex_section'),

    path('kinorium/', views.kinorium, name='kinorium'),
    path('preferences/', views.user_preferences_update, name='user_preferences'),
    path('scan_page/', views.scan_page, name='scan_page'),
    path('tst/', views.tst, name='tst'),
    # path('order_print/<orderid>', views.order_print, name='order_print'),
]

htmx = [
    path('scan/', htmx_views.scan, name='scan'),
    path('reset_rss/', htmx_views.reset_rss, name='reset_rss'),
    path('clear_log/', htmx_views.clear_log, name='clear_log'),
    path('ignore/<pk>', htmx_views.ignore_movie, name='ignore'),
    path('defer/<pk>', htmx_views.defer, name='defer'),
    path('wait_trains/<pk>', htmx_views.wait_trains, name='wait_trains'),
    path('kinorium_table_data/', htmx_views.kinorium_table_data, name='kinorium_table_data'),
    path('get_rss_table_data/', htmx_views.rss_table_data, name='get_rss_table_data'),
    path('get_log/<str:log_type>', htmx_views.get_log, name='get_log'),

    path('kinorium_search/<int:kinozal_id>', htmx_views.kinorium_search, name='kinorium_search'),

    path('kinozal_available_torrents/<int:kinozal_id>', htmx_views.kinozal_download, name='kinozal_download'),
    path('get_torrent_file/<int:kinozal_id>', htmx_views.get_torrent_file, name='get_torrent_file'),
]

urlpatterns += htmx
