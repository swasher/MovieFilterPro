import csv
from io import StringIO
from django.core.files.uploadedfile import InMemoryUploadedFile
from .util import year_to_int
from moviefilter.models import Kinorium
from .classes import KinoriumMovieDataClass


def upload_to_dictreader(requst_file):
    content = requst_file.read()
    try:
        data = content.decode('utf-16', 'strict')
        dict_reader_obj = csv.DictReader(StringIO(data, newline=''), delimiter='\t')
        return dict_reader_obj
    except (UnicodeDecodeError, TypeError):
        return None


def display(i: int):
    """
    Reverse function - convert int to appropriate string label from KinoriumMovie.STATUS
    """
    return dict((x, y) for x, y in Kinorium.STATUS)[i]


def parse_file_movie_list(file: InMemoryUploadedFile) -> list[KinoriumMovieDataClass] | None:

    movie_lists_data = upload_to_dictreader(file)
    if not movie_lists_data:
        return None

    result = []

    for row in movie_lists_data:
        m = KinoriumMovieDataClass()
        t = row['Type']

        list_title = row['ListTitle']
        match list_title:
            case 'Буду смотреть':
                m.status = Kinorium.WILL_WATCH
            case 'Не буду смотреть':
                m.status = Kinorium.DECLINED
            case _:
                m.status = None

        if t == 'Фильм' and m.status:
            m.title = row['Title']
            m.original_title = row['Original Title']
            m.year = year_to_int(row['Year'])
            print(f'FOUND: {m.title} - {m.original_title} - {m.year} [{display(m.status)}]')
            result.append(m)

    return result


def parse_file_votes(file: InMemoryUploadedFile) -> list[KinoriumMovieDataClass]:

    votes_data = upload_to_dictreader(file)
    if not votes_data:
        return None

    result = []

    for row in votes_data:
        m = KinoriumMovieDataClass()
        t = row['Type']
        if t == 'Фильм':
            m.title = row['Title']
            m.original_title = row['Original Title']
            m.year = year_to_int(row['Year'])
            m.status = Kinorium.WATCHED
            print(f'FOUND: {m.title} - {m.original_title} - {m.year} [{display(m.status)}]')
            result.append(m)

    return result
