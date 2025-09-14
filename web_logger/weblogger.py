"""
Обеспечение логгинга, в том числе передача лога на фронтенд через websocker
TODO Перенести все, связанное с этим, в отдельный пакет.
"""

import logging
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

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


def log(message: str, logger_name: str = 'scan'):
    """
    wlog - aka web-log, то есть логирует в веб (через вебсокет).
    Logs a message to a specific log file AND to web-socket.

    Args:
        message: The message to log.
        logger_name: The name of the logger to use ('debug' or 'scan'). Defaults to 'debug'.
        show_log_level: Whether to include the log level in the message sent to the WebSocket.
    """
    if logger_name == 'debug':
        log_level = 'DEBUG'
        debug_logger.debug(message)
    elif logger_name == 'scan':
        log_level = 'INFO'
        scan_logger.info(message)
    elif logger_name == 'error':
        log_level = 'ERROR'
        logging.getLogger('django').error(message)  # this line will add error message to django errors
    else:
        log_level = 'ERROR'
        raise ValueError("Invalid logger_name. Must be 'debug' or 'scan' or 'error'.")

    # log_level нужно добавлять, чтобы различать scan и debug сообщения на стороне фронта. Там эта часть удаляется.
    log_message = f"{log_level}: {message}"
    send_log_to_websocket(log_message)
