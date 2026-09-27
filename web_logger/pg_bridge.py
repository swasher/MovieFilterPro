"""
Мост уведомлений между процессами через PostgreSQL LISTEN/NOTIFY.

HUEY-воркер и web-процесс — разные процессы, поэтому InMemoryChannelLayer
не доставляет события воркера до WebSocket-клиентов. Схема:

    publisher (любой процесс)  --SELECT pg_notify-->  PostgreSQL
    web-процесс: listener-поток --LISTEN--> group_send("log_updates") --> WS

Синхронный psycopg в отдельном потоке выбран сознательно: он не зависит от
Windows Proactor/Selector event loop policy и работает из sync-контекстов.
"""

from __future__ import annotations

import json
import logging
import threading
import time

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

logger = logging.getLogger("web_logger.pg_bridge")

NOTIFY_CHANNEL = "ws_notifications"
GROUP_NAME = "log_updates"
MAX_PAYLOAD_BYTES = 7900  # лимит payload NOTIFY — 8000 байт
RECONNECT_DELAY_SECONDS = 5

_listener_thread: threading.Thread | None = None
_listener_lock = threading.Lock()


# ------------------------------------ #
#          APPLICATION LAYER           #
# ------------------------------------ #


def publish_notification(payload: dict) -> None:
    """Публикует payload через pg_notify. Работает из любого процесса/потока.

    Исключения намеренно не глотаются здесь: вызывающий код решает,
    критична ли ошибка (send_match_log оборачивает вызов try/except).
    NOTIFY внутри транзакции доставляется в момент COMMIT, при autocommit — сразу.
    """
    data = _build_payload_json(payload)
    if data is None:
        return

    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_notify(%s, %s)", (NOTIFY_CHANNEL, data))


def start_listener_thread() -> None:
    """Идемпотентно поднимает фоновый LISTEN-поток в текущем процессе."""
    global _listener_thread
    with _listener_lock:
        if _listener_thread is not None and _listener_thread.is_alive():
            return
        _listener_thread = threading.Thread(
            target=_listener_loop,
            name="pg-notify-listener",
            daemon=True,
        )
        _listener_thread.start()
        logger.info("PG_BRIDGE_LISTENER_STARTED")


# ------------------------------------ #
#            DOMAIN LAYER              #
# ------------------------------------ #


def _build_payload_json(payload: dict) -> str | None:
    """Сериализует payload; слишком большие отбрасываются (лимит NOTIFY)."""
    try:
        data = json.dumps(payload, ensure_ascii=False, default=str)
    except Exception:
        logger.warning("PG_BRIDGE_BAD_PAYLOAD | payload=%r", payload, exc_info=True)
        return None
    size = len(data.encode("utf-8"))
    if size > MAX_PAYLOAD_BYTES:
        logger.warning("PG_BRIDGE_PAYLOAD_TOO_BIG | bytes=%s | type=%s", size, payload.get("type"))
        return None
    return data


def _listener_loop() -> None:
    while True:
        try:
            _listen_once()
        except Exception:
            logger.warning(
                "PG_BRIDGE_LISTEN_FAILED | retry in %ss", RECONNECT_DELAY_SECONDS, exc_info=True
            )
        time.sleep(RECONNECT_DELAY_SECONDS)


def _listen_once() -> None:
    import psycopg

    with psycopg.connect(_build_conninfo(), autocommit=True) as connection:
        connection.execute(f"LISTEN {NOTIFY_CHANNEL}")
        logger.info("PG_BRIDGE_LISTENING | channel=%s", NOTIFY_CHANNEL)
        for notify in connection.notifies():
            _deliver_notification(notify.payload)


def _build_conninfo() -> str:
    """Строка подключения из Django DATABASES['default'] (без ORM-специфичных ключей)."""
    import psycopg

    from django.conf import settings

    db = settings.DATABASES["default"]
    raw_params = {
        "dbname": db.get("NAME"),
        "user": db.get("USER"),
        "password": db.get("PASSWORD"),
        "host": db.get("HOST"),
        "port": db.get("PORT"),
    }
    options = db.get("OPTIONS")
    if isinstance(options, dict) and options.get("sslmode"):
        raw_params["sslmode"] = options["sslmode"]

    params = {}
    for key, value in raw_params.items():
        text = str(value).strip() if value not in (None, "") else ""
        if text:
            params[key] = text
    return psycopg.conninfo.make_conninfo("", **params)


def _deliver_notification(raw_payload: str) -> None:
    """Payload из PG → локальные WebSocket-клиенты web-процесса."""
    try:
        payload = json.loads(raw_payload)
    except ValueError:
        logger.warning("PG_BRIDGE_BAD_JSON | payload=%s", (raw_payload or "")[:200])
        return
    if not isinstance(payload, dict):
        return

    layer = get_channel_layer()
    if layer is None:
        return
    try:
        async_to_sync(layer.group_send)(
            GROUP_NAME,
            {
                "type": "send_notification",
                "payload": payload,
            },
        )
    except Exception:
        logger.warning("PG_BRIDGE_DELIVER_FAILED | payload=%r", payload, exc_info=True)
