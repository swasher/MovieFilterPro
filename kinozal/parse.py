import requests
from bs4 import BeautifulSoup
from datetime import date, datetime, timedelta
from typing import List, Type

from .classes import KinozalMovie
from .classes import LinkConstructor

from .util import is_float


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

        print(f'GRAB URL: {site.url()}')

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

                kinozal_id: int = int(s['href'].split('id=')[1])

                date_added = m.find_all('td', 's')[-1].text.split(' в ')[0]  # '27.11.2023' or 'сегодня' or 'вчера' or 'сейчас'
                match date_added:
                    case 'сегодня' | 'сейчас':
                        date_added = datetime.now().date()
                    case 'вчера':
                        date_added = (datetime.now() - timedelta(days=1)).date()
                    case _:
                        date_added = datetime.strptime(date_added, '%d.%m.%Y').date()

                if date_added < scan_to_date:
                    return movies

                header = s.text.split(' / ')
                if header[2].isdigit() and len(header[2]) == 4:  # normal format
                    title = header[0]
                    original_title = header[1]
                    year = header[2]

                elif 'РУ' in header[2].split(', '):  # русский формат без original title
                    title = header[0]
                    original_title = ''
                    year = header[1]

                elif len(header[2]) == 9 and '-' in header[2]:  # год в заголовке как диапазон: "Голый пистолет (Коллекция) / Naked Gun: Collection / 1982-1994 / ПМ, ПД..."
                    title = header[0]
                    original_title = header[1]
                    year = header[2]
                else:
                    raise Exception(f'Can\'t parse header in id={kinozal_id}')

                print(f'FOUND [{date_added:%d.%m.%y}]: {title} - {year}')

                m = KinozalMovie(kinozal_id, title, original_title, year, date_added)

                movies.append(m)

            site.next_page()

        else:
            # log the error response
            # in case of 4xx or 5xx
            print(response)
            # todo А так вообще можно?
            raise Exception(response)


def get_details(m: KinozalMovie) -> KinozalMovie:
    site = LinkConstructor(id=m.kinozal_id)

    response = requests.get(site.detail_url())

    if response.ok:
        soup = BeautifulSoup(response.content, "html.parser")

        imdb_part = soup.select_one('a:-soup-contains("IMDb")')
        if imdb_part:
            # todo weak assumption for [4]; may be need add some checks
            m.imdb_id = imdb_part['href'].split('/')[4]
            rating = imdb_part.find('span').text
            m.imdb_rating = float(rating) if is_float(rating) else 10
        else:
            m.imdb_id = None
            m.imdb_rating = None

        kinopoisk_part = soup.select_one('a:-soup-contains("Кинопоиск")')
        if kinopoisk_part:
            # todo weak assumption for [4]; may be need add some checks
            m.kinopoisk_id = kinopoisk_part['href'].split('/')[4]
            rating = kinopoisk_part.find('span').text
            m.kinopoisk_rating = float(rating) if is_float(rating) else 10
        else:
            m.kinopoisk_id = None
            m.kinopoisk_rating = None

        m.genres = soup.select_one('b:-soup-contains("Жанр:")').find_next_sibling().text

        m.countries = soup.select_one('b:-soup-contains("Выпущено:")').find_next_sibling().text

        m.director = soup.select_one('b:-soup-contains("Режиссер:")').find_next_sibling().text

        m.actors = soup.select_one('b:-soup-contains("В ролях:")').find_next_sibling().text

        m.plot = soup.select_one('b:-soup-contains("О фильме:")').next_sibling.text.strip()

        translate_search = (soup.select_one('b:-soup-contains("Перевод:")'))
        if translate_search:
            m.translate = translate_search.next_sibling.strip()

        poster = soup.find('img', 'p200').attrs['src']
        if poster[:4] != 'http':
            poster = 'https://kinozal.tv' + poster
        m.poster = poster

        return m