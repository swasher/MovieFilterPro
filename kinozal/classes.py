from urllib.parse import urlencode, quote_plus
from collections import namedtuple


KinozalMovie = namedtuple('Movie', 'title original_title year date')


class LinkConstructor:
    """
    https: // kinozal.tv / browse.php?c = 1002 & v = 3 & page = 74

    Parameters:
    c = 1001 - Все сериалы
    c = 1002 - Все фильмы
    c = 1003 - Все мультфильмы

    v = 3 - Рипы HD(1080 и 720)
    v = 7 - 4K

    page - номер страницы

    s - search by name
    """

    head = 'https://kinozal.tv/browse.php?'

    def __init__(self, c=1002, v=3, page=0):
        self.c = c
        self.v = v
        self.page = page

    def url(self):
        payload = {'c': self.c, 'v': self.v, 'page': self.page}
        params = urlencode(payload, quote_via=quote_plus)
        # quote_plus - заменяет пробелы знаками +
        link = f"https://kinozal.tv/browse.php?{params}"
        return link

    def prev_page(self):
        if self.page > 1:
            self.page -= 1
            return self.url()
        else:
            raise Exception("Can't get previous page")

    def next_page(self):
        self.page += 1
        return self.url()
