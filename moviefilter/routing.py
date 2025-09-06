# moviefilter/routing.py
from django.urls import re_path
from . import websocket_consumers
websocket_urlpatterns = [
    re_path(r"ws/log/$", websocket_consumers.LogConsumer.as_asgi()),
]
