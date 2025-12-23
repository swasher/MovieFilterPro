import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer

logger = logging.getLogger(__name__)


class LogConsumer(AsyncWebsocketConsumer):

    # def __init__(self, *args, **kwargs):
    #     super().__init__(*args, **kwargs)
    #     # self.channel_layer = get_channel_layer()  # Добавляем здесь
    #     self.LOG_FILE_PATH = os.path.join(settings.BASE_DIR, 'logs/full.log')

    async def connect(self):
        await self.channel_layer.group_add('log_updates', self.channel_name)
        await self.accept()
        # await self.send_initial_log()  # отправляем стартовый лог после коннекта

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard('log_updates', self.channel_name)

    async def send_log_update(self, event):
        log_content = event['content']
        await self.send(text_data=json.dumps({
            'type': 'log',  # Добавляем тип для фронтенда
            'content': log_content,
        }))

    async def send_notification(self, event):
        """Обрабатывает событие уведомления и отправляет его клиенту."""
        payload = event['payload']
        # Просто пересылаем payload, который уже является словарем
        await self.send(text_data=json.dumps(payload))


    # def get_log_file_content(self):
    #     """Читает содержимое log_file.log."""
    #     try:
    #         with open(self.LOG_FILE_PATH, 'r') as f:
    #             return f.read()
    #     except FileNotFoundError:
    #         return ""
    #
    # DEPRECATED: Начальный лог отправляется через htmx
    # async def send_initial_log(self):
    #     """Отправляет начальный лог в чаннел."""
    #     initial_log = self.get_log_file_content()
    #     log_lines = initial_log.strip().split('\n')
    #     for line in log_lines:
    #         # await self.channel_layer.send(
    #         await self.channel_layer.group_send(
    #             # self.channel_name,
    #             "log_updates",
    #             {
    #                 "type": "send_log_update",
    #                 "content": line,
    #             },
    #         )
