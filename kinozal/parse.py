import requests
from bs4 import BeautifulSoup
from datetime import date, datetime, timedelta
from typing import List, Type

from .classes import KinozalMovie
from .classes import LinkConstructor


def parse_browse(site: LinkConstructor, scan_to_date):
    """
    Принимает URL и дату, до которой будет сканировать.
    URL - это объект Link_constructor
    """

    movies: List[KinozalMovie] = []

    while True:

        # download the HTML document
        # with an HTTP GET request
        response = requests.get(site.url())

        if response.ok:
            soup = BeautifulSoup(response.content, "html.parser")

            movies_elements = soup.find_all('tr', 'bg')

            for m in movies_elements:
                """
                movie head format:
                
                'Красная жара / Red Heat / 1988 / ПМ / UHD / BDRip (1080p)' - обычно такой форма
                'Наследие / 2023 / РУ, СТ / WEB-DL (1080p)'                 - если русский, то нет original_title
                'Телекинез / 2022-2023 / РУ / WEB-DL (1080p)'               - встречается и такое (тогда берем первые 4 цифры)
                
                """
                s = m.find('a')
                date_added = m.find_all('td', 's')[-1].text.split(' в ')[0]  # '27.11.2023' or 'сегодня' or 'вчера' or 'сейчас'

                match date_added:
                    case 'сегодня' | 'сейчас':
                        movie_date = datetime.now().date()
                    case 'вчера':
                        movie_date = (datetime.now() - timedelta(days=1)).date()
                    case _:
                        movie_date = datetime.strptime(date_added, '%d.%m.%Y').date()

                if movie_date < scan_to_date:
                    return movies

                txt = s.text.split(' / ')
                if txt[2].isdigit() and len(txt[2]) == 4:  # normal format
                    title = txt[0]
                    original_title = txt[1]
                    year = txt[2]

                elif 'РУ' in txt[2].split(', '):  # русский формат без original title
                    title = txt[0]
                    original_title = ''
                    year = txt[1]

                kinozal_id: int = int(s['href'].split('id=')[1])
                print(title, original_title.encode('utf-8'), year, kinozal_id)

                m = KinozalMovie(kinozal_id, title, original_title, year, date_added)
                m = parse_detail(kinozal_id, m)

                movies.append(m)

            site.next_page()

        else:
            # log the error response
            # in case of 4xx or 5xx
            print(response)
            # todo А так вообще можно?
            raise Exception(response)


def parse_detail(id: int, m: KinozalMovie) -> KinozalMovie:
    site = LinkConstructor(id=id)

    response = requests.get(site.detail_url())

    if response.ok:
        soup = BeautifulSoup(response.content, "html.parser")

        imdb_part = soup.select_one('a:-soup-contains("IMDb")')
        if imdb_part:
            # todo weak assumption for [4]; may be need add some checks
            m.imdb_id = imdb_part['href'].split('/')[4]
            m.imdb_rating = imdb_part.find('span').text
        else:
            m.imdb_id = None
            m.imdb_rating = None
        print('IMDb id:', m.imdb_id)
        print('IMDb rating:', m.imdb_rating)

        kinopoisk_part = soup.select_one('a:-soup-contains("Кинопоиск")')
        if kinopoisk_part:
            # todo weak assumption for [4]; may be need add some checks
            m.kinopoisk_id = kinopoisk_part['href'].split('/')[4]
            m.kinopoisk_rating = kinopoisk_part.find('span').text
        else:
            m.kinopoisk_id = None
            m.kinopoisk_rating = None
        print('kinopoisk id:', m.kinopoisk_id)
        print('kinopoisk rating:', m.kinopoisk_rating)

        print('\nGenres:')  # WORKED
        m.genres = soup.select_one('b:-soup-contains("Жанр:")').find_next_sibling().text
        print(m.genres)

        print('\nCountries:')  # WORKED
        m.countries = soup.select_one('b:-soup-contains("Выпущено:")').find_next_sibling().text
        print(m.countries)

        print('\nDirector:')  # WORKED
        m.director = soup.select_one('b:-soup-contains("Режиссер:")').find_next_sibling().text
        print(m.director)

        print('\nActors:')  # WORKED
        m.actors = soup.select_one('b:-soup-contains("В ролях:")').find_next_sibling().text
        print(m.actors)

        print('\nPlot:')  # WORKED
        m.plot = soup.select_one('b:-soup-contains("О фильме:")').next_sibling.text.strip()
        print(m.plot)

        print('\nTranslate:')  #
        translate_search = (soup.select_one('b:-soup-contains("Перевод:")'))
        if translate_search:
            m.translate = translate_search.next_sibling.strip()
            print(m.translate)

        print('\nPoster:')  # WORKED
        poster = soup.find('img', 'p200').attrs['src']
        if poster[:4] != 'http':
            poster = 'https://kinozal.tv' + poster
        m.poster = poster
        print(m.poster)
        print('=====================\n\n')

        return m