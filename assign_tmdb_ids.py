"""

Этот кусок кода анализирует файл result.txt, созданный parse_csv.py, и добавляет два столбца -
- tmdb_id
- error

Если tmdb_id не был найден, или есть сомнения в его валидности, столбец error содержит описание ошибки

"""
import csv
import os
import re
from dotenv import load_dotenv
from dataclasses import dataclass
from dataclass_csv import DataclassReader
from classes import KinoriumMovie, Status
from tmdbapis import TMDbAPIs, Movie, AlternativeTitle
from tmdbapis import exceptions as tmdb_ex
from dataclass_csv import DataclassWriter

load_dotenv()
apikey = os.environ.get('TMDB_API')
api_read_access_token = os.environ.get('API_READ_ACCESS TOKEN')
v4_access_token = os.environ.get('V4_ACCESS_TOKEN')  # Authenticated Token



tmdb = TMDbAPIs(apikey, language='RU')


def normalize_title(title: str) -> str:
    title = title.lower()
    title = re.sub(r"[,.]", "", title)
    title = re.sub(r"ё", "е", title)
    title = title.strip()
    title = re.sub(r'\s+', ' ', title)  # remove double spaces
    return title


def open_csv(input_csv: str) -> list[KinoriumMovie]:
    with open(input_csv) as content:
        movie_lists_data = csv.DictReader(content, delimiter='\t')

        if not movie_lists_data:
            return None

        result = []

        for row in movie_lists_data:
            m = KinoriumMovie()

            m.kinorium_backup_id = row['kinorium_backup_id']
            m.type = row['type']
            m.title = row['title']
            m.original_title = row['original_title']
            m.year = row['year']
            m.status = Status(int(row['status']))
            m.my_vote = row['my_vote']
            m.list_title = row['lists']

            # print(f'FOUND: {m.title} - {m.original_title} - {m.year} [{m.list_title}]')
            result.append(m)

    return result


# def open_csv(input_csv):
#     with open(input_csv) as content:
#         reader = DataclassReader(content, KinoriumMovie, dialect='excel-tab')
#         for row in reader:
#             print(row)


def get_one_movie_strict(query: str, year: int, kinor_movie: KinoriumMovie) -> Movie:
    """
    Ищем по заданному строке и году, и потом в полученных результатах ищем строгое совпадение
    по английскому и русскому названиям
    """
    try:
        response = tmdb.movie_search(query=query, primary_release_year=year, include_adult=True)
    except tmdb_ex.NotFound:
        # print('  GET STRICT - No result')
        ...
    else:
        # print(f'Total_pages: {response.total_pages}')
        # response.load_next() - для загрузки следующей страницы
        # Пока total_pages не обрабатываем - можно сделать потом. Кроме того, чаще всего правильный ответ будет в первых позициях.
        # print(f'  total_results: {response.total_results}')

        for m in response.results:  # type: Movie

            # Поиск соответствий
            kinor_orig_title = normalize_title(kinor_movie.original_title)
            kinor_title = normalize_title(kinor_movie.title)
            found_orig_title = normalize_title(m.original_title)
            found_title = normalize_title(m.title)
            if kinor_orig_title == found_orig_title and kinor_title == found_title:
                print(f'  GET ONE: id={m.id}, Orig: {m.original_title}, Ru: {m.title}, Year: {m.release_date.year}')
                return m


def get_one_movie_alternate(query: str, year: int, kinor_movie: KinoriumMovie) -> Movie:
    """
    Ищем по заданному строке и году, и потом в полученных результатах, для каждого фильма вытаскиваем ВСЕ
    алтернативные названия, и проверяем чтобы русское совпадало с title, а английское - с одним из альтернативных.
    """
    try:
        response = tmdb.movie_search(query=query, primary_release_year=year, include_adult=True)
    except tmdb_ex.NotFound:
        # print('  GET ALT - No result')
        ...
    else:
        # print(f'Total_pages: {response.total_pages}')
        # response.load_next() - для загрузки следующей страницы
        # Пока total_pages не обрабатываем - можно сделать потом. Кроме того, чаще всего правильный ответ будет в первых позициях.
        # print(f'  total_results: {response.total_results}')

        for m in response.results:  # type: Movie

            alternative_titles = []
            for i in m.alternative_titles:  # type: AlternativeTitle
                _ = normalize_title(i.title)
                alternative_titles.append(_)

            # Поиск соответствий
            kinor_orig_title = normalize_title(kinor_movie.original_title)
            kinor_title = normalize_title(kinor_movie.title)
            found_title = normalize_title(m.title)
            if kinor_orig_title in alternative_titles and kinor_title == found_title:
                print(f'  GET ONE: id={m.id}, Orig: {m.original_title}, Ru: {m.title}, Year: {m.release_date.year}')
                return m


def get_one_movie_rus(query: str, years: list[int], kinor_movie: KinoriumMovie) -> Movie:
    """
    Ищем только по русскому названию (это когда original_title - пустое)
    """
    for year in years:
        try:
            response = tmdb.movie_search(query=query, primary_release_year=year, include_adult=True)
        except tmdb_ex.NotFound:
            # print('  GET ALT - No result')
            ...
        else:
            # print(f'Total_pages: {response.total_pages}')
            # response.load_next() - для загрузки следующей страницы
            # Пока total_pages не обрабатываем - можно сделать потом. Кроме того, чаще всего правильный ответ будет в первых позициях.
            # print(f'  total_results: {response.total_results}')

            for m in response.results:  # type: Movie

                # Поиск соответствий
                kinor_title = normalize_title(kinor_movie.title)
                found_title = normalize_title(m.title)
                if kinor_title == found_title:
                    print(f'  GET ONE: id={m.id}, Orig: {m.original_title}, Ru: {m.title}, Year: {m.release_date.year}')
                    return m

def search_algorithm(movie: KinoriumMovie) -> Movie | None:
    """
    Вырисовывается такая картина.
    primary_release_year=movie.year - возвращает фильмы только этого года.
    year=movie.year - возвращает целую кучу фильмов разных годов. Логика непонятна.

    В свойствах Movie:
    original_title - всегда на языке оригинала (японский, китайский, etc)
    title - на том языке, который указан в инициализации tmdb (language='RU')

    В свойствах Kinorium:
    original_title - или отсутствует (если русский фильм), или на языке ориганала (японский, китайский, etc). Но часто написано латиницей, вместо иероглифов.
    title - вседа русский

    1. Если есть orig_title И title

        - (A) запрос в заданном годе по orig_title
        - ищем по совпадению обоих названий   -> ВЫХОД 100%

        - (B) запрос в +-1 год по orig_title
        - ищем по совпадению обоих названий   -> ВЫХОД 100%

        - (C) запрос в заданном годе по title
        - для каждого фильма вытаскиваем alternate_titles
        - ищем по совпадению обоих названий   -> ВЫХОД 100%

        - (D) запрос в +-1 год по title
        - для каждого фильма вытаскиваем alternate_titles
        - ищем по совпадению обоих названий   -> ВЫХОД 100%

        - дальше надо продумать алгоритм, что делать, если у нас совпадает только orig или только title

        - (E) дальше запрос по original_title без года
        - если в ответе совпадают title и original_title -> ВЫХОД RECOMENDED

    2. Если есть только title

        - (RU-A) запрос в заданном годе по title
        - ищем совпадение только по title - ВЫХОД 100%

        - (RU-B) запрос в годе +-1 по title
        - ищем совпадение только по title - ВЫХОД 100%
    """
    if movie.original_title:
        # поиск по русскому+английкому

        # (A)
        query = movie.original_title
        year = movie.year
        results = get_one_movie_strict(query, year, movie)
        if results:
            return results

        # (B)
        query = movie.original_title
        y = int(movie.year)
        years = [y-1, y+1]
        for year in years:
            results = get_one_movie_strict(query, year, movie)
            if results:
                return results

        # (C)
        query = movie.title
        year = movie.year
        results = get_one_movie_alternate(query, year, movie)
        if results:
            return results

        # (D)
        query = movie.title
        y = int(movie.year)
        years = [y-1, y+1]
        for year in years:
            results = get_one_movie_strict(query, year, movie)
            if results:
                return results

        # (E)
        ...

    else:
        # если original_title отсутствует, значит есть только русский title

        # (RU-A)
        query = movie.title
        years = movie.year
        results = get_one_movie_rus(query, [years], movie)
        if results:
            return results

        # (RU-B)
        query = movie.title
        y = int(movie.year)
        years = [y-1, y+1]
        results = get_one_movie_rus(query, years, movie)
        if results:
            return results


def search_id(loaded_csv: list[KinoriumMovie]) -> list[KinoriumMovie]:
    for movie in loaded_csv[:5]:
        print(f'Search for: {movie.original_title} - {movie.title} - {movie.year}')

        result = search_algorithm(movie)

        """
        TMDb имеет такие предустановленные параметры:
        - рейтинг
        - список Watchlist
        - список Favorites
        
        Т.е. наши имеющиеся данные нужно преобразовать соответственно.
        Буду смотреть = Watchlist
        Любимые фильмы = Favorites
        Улюблені серіали = Favorites
        """

        if result:
            movie.tmdb_id = result.id
        else:
            print('  Not found')

    return loaded_csv


if __name__ == '__main__':
    input_csv = 'combined.csv'
    output_csv = 'combined_with_tmdb.csv'

    loaded_csv = open_csv(input_csv)
    csv_with_id = search_id(loaded_csv)

    with open(output_csv, "w") as csvfile:
        w = DataclassWriter(csvfile, csv_with_id, KinoriumMovie, dialect='excel-tab', lineterminator='\n')
        w.write()
