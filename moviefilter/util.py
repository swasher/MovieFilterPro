import logging
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync


# logger = logging.getLogger('my_logger')
channel_layer = get_channel_layer()

debug_logger = logging.getLogger('debug_logger')
scan_logger = logging.getLogger('scan_logger')

def is_float(string):
    if string.replace(".", "").isnumeric():
        return True
    else:
        return False


def year_to_int(year: str) -> int:
    try:
        year = int(year)
    except ValueError:
        raise Exception('Year not int')
    return year


def get_object_or_none(klass, *args, **kwargs):
    """
    Use get() to return an object, or returns None if the object
    does not exist instead of throwing an exception.
    klass may be a Model, Manager, or QuerySet object. All other passed
    arguments and keyword arguments are used in the get() query.
    Like with QuerySet.get(), MultipleObjectsReturned is raised if more than
    one object is found.
    """
    queryset = klass._default_manager.all() if hasattr(klass, "_default_manager") else klass
    if not hasattr(queryset, "get"):
        klass__name = (
            klass.__name__ if isinstance(klass, type) else klass.__class__.__name__
        )
        raise ValueError(
            "First argument to get_object_or_none() must be a Model, Manager, "
            "or QuerySet, not '%s'." % klass__name
        )
    try:
        return queryset.get(*args, **kwargs)
    except queryset.model.DoesNotExist:
        return None


def not_match_rating(movie_rating: float | None, filter_rating: float | None) -> bool:
    """
    Возвращает True, если рейтинг фильмы ниже заданного.
    Если у фильма нет рейтинга, то фильм проходит проверку (возв. False)
    """
    if movie_rating:
        if movie_rating < filter_rating:
            return True
    return False


def send_log_to_websocket(log_message):
    async_to_sync(channel_layer.group_send)(
        "log_updates",
        {
            "type": "send_log_update",  # Это имя метода, который будет вызван в LogConsumer
            "content": log_message,
        },
    )


def log(message: str, logger_name: str = 'scan'):
    """
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
