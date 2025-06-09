# Удадяем из базы все записи, сделанные после 10.01.25, включая эту дату
# Поле называется "date_added"
# Эти фильмы отсканились с пустыми жанрами, актерами, описаниями и т.д

from movie_filter_pro import wsgi
from datetime import datetime, date
from django.db.models import Q
from moviefilter.models import MovieRSS

# PRIORITY = (
#     (LOW, 'Низкий'),
#     (HIGH, 'Обычный'),
#     (DEFER, 'Отложено'),
#     (SKIP, 'Отказ'),
#     (WAIT_TRANS, 'Жду дубляж'),
#     (TRANS_FOUND, 'Найден дубляж или ПМ'),
# )


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




if __name__ == '__main__':
    since_date_str = '2025-01-09'
    since_date = datetime.strptime(since_date_str, '%Y-%m-%d').date()
    delete_movies_since_date(since_date)
