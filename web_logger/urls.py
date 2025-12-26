from django.urls import path
from web_logger import htmx_views

app_name = "web-logger"

urlpatterns = []

htmx = [
    path('get_log/<str:log_type>', htmx_views.get_log, name='get_log'),
    path('clear_log/', htmx_views.clear_log, name='clear_log'),
]

urlpatterns += htmx
