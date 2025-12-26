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
    path('cancel_scan/<str:task_id>/', htmx_views.cancel_scan, name='cancel_scan'),
    path('run_deleting_since_date/', deleting_since_date.run_deleting_since_date, name='run_deleting_since_date'),
]

urlpatterns += htmx
