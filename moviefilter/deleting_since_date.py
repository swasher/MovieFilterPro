from django.http import HttpResponse
from datetime import datetime, date
from django.db.models import Q
from moviefilter.models import MovieRSS

"""
Если в парсинге что-то пошло не так, например, он напарсил фильмы с пустнымы данными,
можно с по помощью этого скрипта удалить фильмы, добавленные после определённой даты.
"""


def delete_movies_since_date(since_date: date):
    # Извлекаем значения HIGH и LOW из PRIORITY вручную
    reverse_map = {label: value for value, label in MovieRSS.PRIORITY}
    HIGH = reverse_map['Обычный']
    LOW = reverse_map['Низкий']

    movies = MovieRSS.objects.filter(date_added__gte=since_date).filter(Q(priority=HIGH) | Q(priority=LOW))
    count = movies.count()

    return_string = ''

    for m in movies:
        print(m.title, m.date_added, m.priority)
        return_string += f"{m.title} - {m.date_added} - {m.priority}<br>"

    movies.delete()

    print(f"\n{count} movies deleted.")
    return_string += f"{count} movies deleted."

    return return_string


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
