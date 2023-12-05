from django.urls import path
from kinozal import views

app_name = "kinozal"

urlpatterns = [
    path('', views.movies, name='movies'),
    path('movies_low/', views.movies_low, name='movies_low'),
    path('parse_kinorium_csv/', views.parse_kinorium_csv, name='parse_kinorium_csv'),
    path('scan_page/', views.scan_page, name='scan_page'),
    path('plex/', views.plex, name='plex'),
    path('preferences/', views.user_preferences_update, name='user_preferences'),
    # path('order_print/<orderid>', views.order_print, name='order_print'),
]

htmx = [
    path('scan/', views.scan, name='scan'),
    path('reset_rss/', views.reset_rss, name='reset_rss'),
    path('ignore/<pk>', views.ignore_movie, name='ignore')
]

urlpatterns += htmx
