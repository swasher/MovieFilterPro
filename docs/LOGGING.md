## Логирование

В проекте есть несколько каналов логирования:

1. Логирование в систему вебсокетов + файл:

        from web_logger import log
        log("some text")   

Такой лог уйдет одновременно через websocket на фронт и отобразится в окошке логи, 
а также будет записан в файл `logs/scan.log`

Есть также второй параметр у log - log_level. Может принимать три значения:

    class LogType(Enum):
        SCAN = 1
        ERROR = 2
        DEBUG = 3

DEBUG - замена print, особенно для production, если что-то не работает.
ERROR - вывод полного trace в лог + кастомное сообщение, использование:
    log(f"Failed to do something: {some_variable}", logger_name=LogType.ERROR)
SCAN - вывод информации во время парсинга


2. Условный лог (их можно создать несколько для разных нужд). Разновидность простого лога Django. 
Я сделал bool переменную в `settings.py` с названием `KINOZAL_SCAN_PRINT`.
Когда она True то такой лог печатает в консоль:

        kinozal_logger = logging.getLogger('kinozal')
        kinozal_logger.debug("Сообщение")

Удобно использовать для отладки определенных механизмов, в данном случае парсера кинозала.

