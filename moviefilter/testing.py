from datetime import datetime
from django.http import HttpResponse
from django.shortcuts import render
from one_time_scripts.deleting_since_date import delete_movies_since_date  # Импортируйте ваш скрипт как модуль


def run_deleting_since_date(request):
    since_date_str = '2025-01-10'
    since_date = datetime.strptime(since_date_str, '%Y-%m-%d').date()

    if request.method == 'POST':
        try:
            result_string = delete_movies_since_date(since_date)  # Вызовите функцию напрямую
            return HttpResponse(result_string)
        except Exception as e:
            return HttpResponse(f"Ошибка при запуске скрипта: {e}", status=500)
    else:
        return HttpResponse("Недопустимый метод", status=400)
