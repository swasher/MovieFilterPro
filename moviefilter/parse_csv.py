import csv
from typing import Type
from io import StringIO
from django.core.files.uploadedfile import InMemoryUploadedFile
from .util import year_to_int
from .models import KinoriumMovie
from .classes import KinoriumMovieDataClass


def upload_to_dictreader(requst_file):
    content = requst_file.read()
    data = content.decode('utf-16', 'strict')
    dict_reader_obj = csv.DictReader(StringIO(data, newline=''), delimiter='\t')
    return dict_reader_obj


def display(i: int):
    """
    Reverse function - convert int to appropriate string label from KinoriumMovie.STATUS
    """
    return dict((x, y) for x, y in KinoriumMovie.STATUS)[i]


def parse_file_movie_list(file: InMemoryUploadedFile) -> list[KinoriumMovieDataClass]:

    movie_lists_data = upload_to_dictreader(file)
    result = []

    for row in movie_lists_data:
        m = KinoriumMovieDataClass()
        t = row['Type']

        list_title = row['ListTitle']
        match list_title:
            case 'Буду смотреть':
                m.status = KinoriumMovie.WILL_WATCH
            case 'Не буду смотреть':
                m.status = KinoriumMovie.DECLINED
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
    result = []

    for row in votes_data:
        m = KinoriumMovieDataClass()
        t = row['Type']
        if t == 'Фильм':
            m.title = row['Title']
            m.original_title = row['Original Title']
            m.year = year_to_int(row['Year'])
            m.status = KinoriumMovie.WATCHED
            print(f'FOUND: {m.title} - {m.original_title} - {m.year} [{display(m.status)}]')
            result.append(m)

    return result
