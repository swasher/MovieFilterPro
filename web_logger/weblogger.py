"""
Обеспечение логгинга, в том числе передача лога на фронтенд через websocker
"""

import logging
import threading
from contextlib import contextmanager
from datetime import datetime
from enum import Enum
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from web_logger.pg_bridge import publish_notification


class LogType(Enum):
    SCAN = 1
    ERROR = 2
    DEBUG = 3


def compact_timestamp() -> str:
    """Компактная метка даты/времени для строк лога: 25.10.26 10:35:22."""
    return datetime.now().strftime('%d.%m.%y %H:%M:%S')


# channel_layer = get_channel_layer()
debug_logger = logging.getLogger('debug_logger')
scan_logger = logging.getLogger('scan_logger')


# ------------------------------------ #
#          APPLICATION LAYER           #
#  Bridge-mode для HUEY-воркера       #
# ------------------------------------ #
#
# В HUEY-воркере (отдельный процесс) InMemoryChannelLayer не доставляет
# события до WebSocket-клиентов web-процесса. Поэтому в воркере log() и
# send_notification() маршрутизируются через PG LISTEN/NOTIFY (pg_bridge).
# Режим включается per-thread через контекстный менеджер bridge_mode(),
# чтобы не затронуть ручной скан в web-процессе.

_bridge_state = threading.local()


def _bridge_enabled() -> bool:
    return bool(getattr(_bridge_state, "enabled", False))


def enter_bridge_mode() -> None:
    _bridge_state.enabled = True


def exit_bridge_mode() -> None:
    _bridge_state.enabled = False


@contextmanager
def bridge_mode():
    """Включает маршрутизацию логов/уведомлений через PG-мост в текущем потоке."""
    enter_bridge_mode()
    try:
        yield
    finally:
        exit_bridge_mode()


# ------------------------------------ #
#         Персистентный лог скана      #
# ------------------------------------ #
#
# Когда скан выполняется в контексте scan_log_context(run_id), строки log()
# дополнительно пишутся в moviefilter.ScanLogEntry, чтобы была структурированная
# история (что сканировалось, когда и почему упало). DEBUG-строки в БД не пишутся.

_scan_state = threading.local()


def _current_scan_run_id():
    return getattr(_scan_state, "run_id", None)


@contextmanager
def scan_log_context(run_id):
    """Включает запись строк log() в ScanLogEntry для заданного запуска скана."""
    _scan_state.run_id = run_id
    try:
        yield
    finally:
        _scan_state.run_id = None


def _persist_scan_log_entry(run_id, logger_name: LogType, message: str) -> None:
    from moviefilter.models import ScanLogEntry

    level = ScanLogEntry.Level.ERROR if logger_name is LogType.ERROR else ScanLogEntry.Level.INFO
    try:
        ScanLogEntry.objects.create(run_id=run_id, level=level, message=message)
    except Exception:
        # Персистентный лог — вспомогательный, не должен ронять скан.
        debug_logger.debug("persist scan log entry failed", exc_info=True)


def send_log_to_websocket(log_message):
    # async_to_sync(channel_layer.group_send)(
    async_to_sync(get_channel_layer().group_send)(
        "log_updates",
        {
            "type": "send_log_update",  # Это имя метода, который будет вызван в LogConsumer
            "content": log_message,
        },
    )


def send_notification(payload: dict):
    """Sends a structured notification payload to the websocket group."""
    if _bridge_enabled():
        publish_notification(payload)
        return
    async_to_sync(get_channel_layer().group_send)(
        "log_updates",
        {
            "type": "send_notification",  # Имя нового метода-обработчика в LogConsumer
            "payload": payload,
        },
    )


async def asend_notification(payload: dict):
    """Асинхронная версия для отправки структурированных уведомлений."""
    await get_channel_layer().group_send(
        "log_updates",
        {
            "type": "send_notification",
            "payload": payload,
        },
    )


def send_match_log(event_type: str, **data):
    """Структурированное событие шага матчинга → WebSocket.

    Идёт через web_logger.pg_bridge (PG LISTEN/NOTIFY), потому что bulk-матчинг
    работает в отдельном HUEY-процессе, куда in-memory channel layer не достаёт.
    Никогда не бросает исключение: лог не должен ронять pipeline.
    """
    try:
        publish_notification({
            "type": "match_log",
            "event": event_type,
            **data,
        })
    except Exception:
        debug_logger.debug("send_match_log failed: %s", event_type, exc_info=True)


def log(message: str, logger_name: LogType = LogType.SCAN):
    """
    Logs a message to a specific log file AND to web-socket.
    DEBUG - замена print, особенно для production, если что-то не работает.
    ERROR - вывод полного trace в лог + кастомное сообщение, использование:
        log(f"Failed to do something: {some_variable}", logger_name=LogType.ERROR)
    SCAN - вывод информации во время парсинга

    Args:
        message: The message to log.
        logger_name: The name of the logger to use. Defaults to LogType.SCAN.
        exc_info: If True, exception info is added to the log message.
    """
    match logger_name:
        case LogType.DEBUG:
            log_level = 'DEBUG'
            debug_logger.debug(message, exc_info=False)
        case LogType.SCAN:
            log_level = 'INFO'
            scan_logger.info(message, exc_info=False)
        case LogType.ERROR:
            log_level = 'ERROR'
            logging.getLogger("django").error(f"\n{message}",
                                              exc_info=True)  # this line will add error message to django errors
        case _:
            raise ValueError(f"Invalid logger_name: {logger_name}. Must be a LogType member.")

    # log_level нужно добавлять, чтобы различать scan и debug сообщения на стороне фронта. Там эта часть удаляется.
    # Метка времени ставится после log_level, чтобы фронт по-прежнему фильтровал сообщения по префиксу.
    log_message = f"{log_level}: [{compact_timestamp()}] {message}"

    # Персистентный лог в БД (только внутри запуска скана; DEBUG не пишем).
    run_id = _current_scan_run_id()
    if run_id is not None and logger_name is not LogType.DEBUG:
        _persist_scan_log_entry(run_id, logger_name, message)

    if _bridge_enabled():
        publish_notification({"type": "log", "content": log_message})
    else:
        send_log_to_websocket(log_message)


async def alog(message: str, logger_name: LogType = LogType.SCAN):
    """Асинхронная версия для отправки логов."""
    match logger_name:
        case LogType.DEBUG:
            log_level = 'DEBUG'
            debug_logger.debug(message, exc_info=False)
        case LogType.SCAN:
            log_level = 'INFO'
            scan_logger.info(message, exc_info=False)
        case LogType.ERROR:
            log_level = 'ERROR'
            logging.getLogger("django").error(f"\n{message}", exc_info=True)
        case _:
            raise ValueError(f"Invalid logger_name: {logger_name}. Must be a LogType member.")

    # log_level нужно добавлять, чтобы различать scan и debug сообщения на стороне фронта. Там эта часть удаляется.
    # Метка времени ставится после log_level, чтобы фронт по-прежнему фильтровал сообщения по префиксу.
    log_message = f"{log_level}: [{compact_timestamp()}] {message}"

    await get_channel_layer().group_send(
        "log_updates",
        {
            "type": "send_log_update",
            "content": log_message,
        },
    )
