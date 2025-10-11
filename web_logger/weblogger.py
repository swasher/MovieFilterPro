"""
Обеспечение логгинга, в том числе передача лога на фронтенд через websocker
TODO Перенести все, связанное с этим, в отдельный пакет.
"""

import logging
from enum import Enum
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer


class LogType(Enum):
    SCAN = 1
    ERROR = 2
    DEBUG = 3

# channel_layer = get_channel_layer()
debug_logger = logging.getLogger('debug_logger')
scan_logger = logging.getLogger('scan_logger')


def send_log_to_websocket(log_message):
    # async_to_sync(channel_layer.group_send)(
    async_to_sync(get_channel_layer().group_send)(
        "log_updates",
        {
            "type": "send_log_update",  # Это имя метода, который будет вызван в LogConsumer
            "content": log_message,
        },
    )


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
            logging.getLogger("django").error(f"\n{message}", exc_info=True)  # this line will add error message to django errors
        case _:
            raise ValueError(f"Invalid logger_name: {logger_name}. Must be a LogType member.")

    # log_level нужно добавлять, чтобы различать scan и debug сообщения на стороне фронта. Там эта часть удаляется.
    log_message = f"{log_level}: {message}"
    send_log_to_websocket(log_message)
