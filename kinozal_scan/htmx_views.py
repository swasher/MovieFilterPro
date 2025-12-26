import uuid
from pathlib import Path

from asgiref.sync import async_to_sync
from bs4 import BeautifulSoup
from django.db.models import Q
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.contrib import messages
from django.http import HttpResponse
from django.conf import settings
from django.views.decorators.http import require_http_methods, require_GET, require_POST

from moviefilter.models import UserPreferences
from .runtime import cancel_events, tasks
from .service import start_scan_task


# @login_required()
# @require_GET
# def scan(request):
#     """
#     Вызывается при нажатии на кнопку Scan
#     :param request:
#     :return:
#     """
#     pref = UserPreferences.get()
#     last_scan = pref.last_scan
#     start_page = pref.scan_from_page
#     user = request.user
#
#     # TODO Сдлать функцию-проверку всех необходимых параметров в preferences, если чего-то не хвататет, рисовать красный алерт.
#
#     try:
#         number_of_new_movies = kinozal_scan(start_page, last_scan, user)
#     except DetailsFetchError:
#         # Эта ошибка уже залогирована на более низком уровне с полным traceback.
#         # Здесь мы просто сообщаем пользователю о проблеме.
#         messages.error(request, 'Сканирование прервано. Не удалось получить данные со страницы фильма. Возможно, сайт недоступен или IP заблокирован. Проверьте error.log для деталей.')
#         return HttpResponse(status=500)
#     except Exception as e:
#         # Ловим любые другие непредвиденные ошибки
#         log(f'An unexpected error occurred in the scan view: {e}', logger_name=LogType.ERROR)
#         messages.error(request, f'Произошла непредвиденная ошибка: {e}')
#         return HttpResponse(status=500)
#     else:
#         log(f"Scan complete, new entries: {number_of_new_movies}")
#         pref.scan_from_page = None
#         pref.save()
#
#         # update last scan to now()
#         # UserPreferences.objects.filter(user=request.user).update(last_scan=datetime.now().date())
#         UserPreferences.objects.filter(pk=1).update(last_scan=datetime.now().date())
#
#         messages.success(request, f'Added {number_of_new_movies} movies.')
#         return HttpResponse(status=200)

@login_required
@require_GET
def scan(request):
    pref = UserPreferences.get()

    task_id = uuid.uuid4().hex
    user = request.user

    async_to_sync(start_scan_task)(
        task_id=task_id,
        start_page=pref.scan_from_page or 0,
        scan_to_date=pref.last_scan,
        user=user,
    )

    return HttpResponse(
        status=202,
        headers={
            "X-Task-ID": task_id
        }
    )


@require_POST
def cancel_scan(request, task_id):
    print('Scan was canceled by user.')
    event = cancel_events.get(task_id)
    if event:
        event.set()

    task = tasks.get(task_id)
    if task:
        task.cancel()  # ускоряет завершение await

    return HttpResponse(status=204)
