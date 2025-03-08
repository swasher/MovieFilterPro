# middleware.py
import os


class DevBannerMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Определяем окружение по hostname и Добавляем в контекст всех шаблонов
        request.is_dev = 'PyCharm' in os.environ

        response = self.get_response(request)
        return response
