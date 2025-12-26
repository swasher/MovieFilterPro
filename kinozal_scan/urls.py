from django.urls import path
from kinozal_scan import views
from kinozal_scan import htmx_views
from kinozal_scan import deleting_since_date

# app_name = "kinozal-scan"

urlpatterns = [
    path('scan_page/', views.scan_page, name='scan_page'),
]

htmx = [
    path('scan/', htmx_views.scan, name='scan'),
    path('cancel/<str:task_id>', htmx_views.cancel_scan, name='cancel'),
    path('deleting_page', views.deleting_page, name='deleting_page'),
    path('run_deleting_since_date', deleting_since_date.run_deleting_since_date, name='run_deleting_since_date'),
]

urlpatterns += htmx
