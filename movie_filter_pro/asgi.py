"""
ASGI config for MovieFilterPro project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/4.2/howto/deployment/asgi/
"""

# import os
#
# from django.core.asgi import get_asgi_application
#
# os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'movie_filter_pro.settings')
#
# application = get_asgi_application()


import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from django.urls import path
from moviefilter import consumers
from moviefilter.routing import websocket_urlpatterns

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'movie_filter_pro.settings')

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": AuthMiddlewareStack(
        # URLRouter([
        #     path("ws/log/", consumers.LogConsumer.as_asgi()),
        # ])
        URLRouter(
            websocket_urlpatterns
        )
    ),
})
