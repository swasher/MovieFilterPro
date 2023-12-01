from django.urls import path
from kinozal import views

app_name = "kinozal"

urlpatterns = [
    path('', views.movies, name='movies'),
    path('movies_low/', views.movies_low, name='movies_low'),
    path('upload_csv/', views.upload_csv, name='upload_csv'),
    path('scan_page/', views.scan_page, name='scan_page'),
    path('scan/', views.scan, name='scan'),
    path('scan/', views.scan, name='scan'),
    path('reset_rss/', views.reset_rss, name='reset_rss'),
    path('preferences/', views.user_preferences_update, name='user_preferences'),
    # path('order_print/<orderid>', views.order_print, name='order_print'),
]

# htmx = [
#     path('order_edit/', views.order_edit, name='order_edit'),
#     path('order_edit/<int:pk>/', views.order_edit, name='order_edit'),
#     path('detail_inline/', views.detail_inline, name='detail_inline'),
#     path('add_detail_formset/<int:current_total_formsets>', views.add_detail_formset, name='add_detail_formset')
# ]
#
# urlpatterns += htmx