import requests
from bs4 import BeautifulSoup
from datetime import date, datetime
from typing import List, Type

from .classes import KinozalMovie
from .classes import LinkConstructor


def parse(site: LinkConstructor, scan_to_date):
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
                s = m.find('a')
                d = m.find_all('td', 's')[-1].text.split(' в ')[0]  # '27.11.2023'
                movie_date = datetime.strptime(d, '%d.%m.%Y').date()

                if movie_date < scan_to_date:
                    return movies

                txt = s.text.split(' / ')
                if txt[1].isdigit() and len(txt[1]) == 4:
                    title = txt[0]
                    original_title = ''
                    year = txt[1]
                else:
                    title = txt[0]
                    original_title = txt[1]
                    year = txt[2]

                # 'Красная жара / Red Heat / 1988 / ПМ / UHD / BDRip (1080p)'
                # 'Наследие / 2023 / РУ, СТ / WEB-DL (1080p)'
                link = s['href']
                print(title, original_title.encode('utf-8'), year, link)
                m = KinozalMovie(title, original_title, year, d)
                movies.append(m)

            site.next_page()

        else:
            # log the error response
            # in case of 4xx or 5xx
            print(response)
            # todo А так вообще можно?
            raise Exception(response)
