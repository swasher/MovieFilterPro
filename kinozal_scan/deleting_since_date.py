import json

from django.http import HttpResponse, JsonResponse
from datetime import datetime, date
from django.db.models import Q
from moviefilter.models import MovieRSS

"""
Если в парсинге что-то пошло не так, например, он напарсил фильмы с пустнымы данными,
можно с по помощью этого скрипта удалить фильмы, добавленные с текущей даты по определённую дату.
"""


def delete_movies_since_date(since_date: date) -> int:
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

    return count


def run_deleting_since_date(request):
    # since_date_str = '2025-01-10'
    # since_date = datetime.strptime(since_date_str, '%Y-%m-%d').date()

    try:
        # 1. Получаем JSON из тела запроса
        date_str = request.POST.get('date')

        # 2. Извлекаем дату
        if not date_str:
            return HttpResponse('<div class="alert alert-danger">Ошибка: Дата не указана</div>')

        # 3. Преобразовываем дату в объект
        since_date = datetime.strptime(date_str, '%Y-%m-%d').date()

    except json.JSONDecodeError as e:
        return HttpResponse(
            f'<div class="alert alert-danger">'
            f'<h4><i class="bi bi-bug me-2"></i>Ошибка JSON</h4>'
            f'<p>Не удалось декодировать тело запроса (JSONDecodeError).</p>'
            f'<hr>'
            f'<p class="mb-0"><strong>Текст ошибки:</strong> {e}</p>'
            f'<p class="mt-2 small text-muted text-break"><strong>Body:</strong> {request.body.decode("utf-8", errors="replace")}</p>'
            f'</div>'
        )

    except ValueError:
        return HttpResponse('<div class="alert alert-danger">Неверный формат даты. Используйте YYYY-MM-DD</div>')

    if request.method == 'POST':
        try:
            print('Start deleting movies since date:', since_date)
            result_int = delete_movies_since_date(since_date)  # Вызовите функцию удаления
            # 5. Возвращаем результат
            return HttpResponse(
                f'<div class="alert alert-success">'
                f'<h4><i class="bi bi-check-circle me-2"></i>Успешно</h4>'
                f'<p>Удалены фильмы с <strong>{since_date.strftime("%d.%m.%Y")}</strong> по <strong>{datetime.now().strftime("%d.%m.%Y")}</strong>.</p>'
                f'<hr>'
                f'<p class="mb-0">Количество удаленных записей: <strong>{result_int}</strong></p>'
                f'</div>'
            )
        except Exception as e:
            return HttpResponse(
                f'<div class="alert alert-danger">'
                f'<h4><i class="bi bi-exclamation-triangle me-2"></i>Ошибка выполнения</h4>'
                f'<p>{e}</p>'
                f'</div>'
            )
    else:
        return HttpResponse("Недопустимый метод", status=400)
