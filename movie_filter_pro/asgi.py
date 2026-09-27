import os
from django.core.asgi import get_asgi_application
from starlette.staticfiles import StaticFiles
from starlette.routing import Mount
from starlette.applications import Starlette
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from web_logger.routing import websocket_urlpatterns
from web_logger.pg_bridge import start_listener_thread

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'movie_filter_pro.settings')

# Django-приложение
django_asgi_app = get_asgi_application()

# Статические файлы через WhiteNoise (STATIC)
# whitenoise_app = WhiteNoise(django_asgi_app, root='collectstatic')
# whitenoise_app.add_files('collectstatic', prefix='static/')

# HTTP-приложение = media + static + Django
http_app = Starlette(
    routes=[    
        Mount("/media", app=StaticFiles(directory="media"), name="media"),
        Mount("/", app=django_asgi_app),
    ]
)

# Финальный ASGI-роутер
application = ProtocolTypeRouter({
    "http": http_app,
    "websocket": AuthMiddlewareStack(
        URLRouter(websocket_urlpatterns)
    ),
})

# Мост PG LISTEN/NOTIFY: доставка событий из HUEY-процесса в WebSocket
# (см. web_logger/pg_bridge.py и PLANS_MATCHING_LOG.md, Шаг 0).
start_listener_thread()
