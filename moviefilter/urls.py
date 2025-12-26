from django.urls import path
from moviefilter import views
from moviefilter import htmx_views

# app_name = "moviefilter"

urlpatterns = [
    path('', views.rss, name='rss'),
]

htmx = [
    path('reset_rss/', htmx_views.reset_rss, name='reset_rss'),
    path('ignore/<pk>', htmx_views.ignore_movie, name='ignore'),
    path('defer/<pk>', htmx_views.defer, name='defer'),
    path('wait_trains/<pk>', htmx_views.wait_trains, name='wait_trains'),
    path('get_rss_table_data/', htmx_views.rss_table_data, name='get_rss_table_data'),
    path('kinozal_available_torrents/<int:kinozal_id>', htmx_views.kinozal_download, name='kinozal_download'),
    path('get_torrent_file/<int:kinozal_id>', htmx_views.get_torrent_file, name='get_torrent_file'),
    path('total_downloads/', htmx_views.total_downloads_for_movie, name='total_downloads_for_movie'),
]

urlpatterns += htmx
