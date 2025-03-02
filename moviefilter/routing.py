# moviefilter/routing.py
from django.urls import re_path
from . import consumers
websocket_urlpatterns = [
    re_path(r"ws/log/$", consumers.LogConsumer.as_asgi()),
]
