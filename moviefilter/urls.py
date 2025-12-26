from django.urls import path
from moviefilter import views
from moviefilter import htmx_views
from moviefilter import deleting_since_date
from django.conf import settings
from django.conf.urls.static import static

# app_name = "moviefilter"

urlpatterns = [
    path('', views.rss, name='rss'),
    path('scan_page/', views.scan_page, name='scan_page'),
    path('tst/', views.tst, name='tst'),
]

htmx = [
    path('scan/', htmx_views.scan, name='scan'),
    path('cancel_scan/<str:task_id>/', htmx_views.cancel_scan, name='cancel_scan'),
    path('reset_rss/', htmx_views.reset_rss, name='reset_rss'),
    path('clear_log/', htmx_views.clear_log, name='clear_log'),
    path('ignore/<pk>', htmx_views.ignore_movie, name='ignore'),
    path('defer/<pk>', htmx_views.defer, name='defer'),
    path('wait_trains/<pk>', htmx_views.wait_trains, name='wait_trains'),
    path('get_rss_table_data/', htmx_views.rss_table_data, name='get_rss_table_data'),
    path('get_log/<str:log_type>', htmx_views.get_log, name='get_log'),
    path('kinozal_available_torrents/<int:kinozal_id>', htmx_views.kinozal_download, name='kinozal_download'),
    path('get_torrent_file/<int:kinozal_id>', htmx_views.get_torrent_file, name='get_torrent_file'),

    path('run_deleting_since_date/', deleting_since_date.run_deleting_since_date, name='run_deleting_since_date'),

    path('total_downloads/', htmx_views.total_downloads_for_movie, name='total_downloads_for_movie'),
]

urlpatterns += htmx
