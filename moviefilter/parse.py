import dataclasses
import requests
import logging
import re
from bs4 import BeautifulSoup
from datetime import date, datetime, timedelta
from urllib.parse import urlencode, quote_plus

from .classes import KinozalMovie
from .classes import LinkConstructor
from .classes import KinozalSearch

from .util import is_float
from .models import Country, MovieRSS

from .checks import exist_in_kinorium, exist_in_kinozal, check_users_filters, need_dubbed
from movie_filter_pro.settings import HIGH, LOW, DEFER, SKIP, WAIT_TRANS, TRANS_FOUND

logger = logging.getLogger('my_logger')


def kinozal_scan(site: LinkConstructor, scan_to_date: date, user):

    last_day_reached = False
    last_page_reached = False
    counter = 0
    while not last_day_reached and site.page <= 100:

        # Получаем список всех фильмов со страницы. Если достигли нужной даты, то last_day_reached возврашается как True
        movies, last_day_reached = parse_page(site, scan_to_date)

        # Проверяем список по фильтрам, и получаем отфильтрованный и заполненный список, который можно уже заносить в базу.
        # movie_audit удаляет из списка movies фильмы, не прошедшие проверку, а так-же заполняет каждый movie дополнительными данными.
        movies = movie_audit(movies, user)

        # записываем фильмы в базу
        if movies:
            # logger.debug(f"SAVE TO DB")
            # logger.info(f"SAVE TO DB infoinfoinfoinfoinfo")
            # logger.error(f"SAVE TO DB ERROR ERROR ERROR ERROR ERROR ")
            print(f'SAVE TO DB: [{len(movies)} movies]')

            counter += len(movies)
            for m in movies:
                # todo использовать bulk_create
                MovieRSS.objects.get_or_create(title=m.title, original_title=m.original_title, year=m.year,
                                               defaults=dataclasses.asdict(m))
        print('')

        # переходим к сканированию следующей странице
        site.next_page()

    return counter


def parse_page(site: LinkConstructor, scan_to_date) -> (list[KinozalMovie], bool):
    """
    Принимает URL и дату, до которой будет сканировать.
    URL - это объект Link_constructor
    """
    END_DATE_REACHED = True
    END_DATE_NOT_REACHED = False

    movies: list[KinozalMovie] = []

    # download the HTML document
    # with an HTTP GET request
    response = requests.get(site.url())

    print(f'GRAB URL: {site.url()}')
    logger.info(f'GRAB URL: {site.url()}')

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
                return movies, END_DATE_REACHED

            # фильм имеет `нормальную` озвучку - дубляж или профессиональный многоголосый
            if 'ПМ' in s.text or 'ДБ' in s.text:
                dubbed = True
            else:
                dubbed = False

            header = s.text.split(' / ')
            if header[2].strip().isdigit() and len(header[2].strip()) == 4:  # normal format
                title = header[0].strip()
                original_title = header[1].strip()
                year = header[2].strip()

            elif 'РУ' in header[2].split(', '):  # 	До звезды / 2023 / РУ / WEB-DL (1080p)  - русский формат без original title
                title = header[0].strip()
                original_title = ''
                year = header[1].strip()

            elif header[1].strip().isdigit() and len(header[1].strip()) == 4:  # Карточный долг / 2023 / ДБ / WEB-DL (1080p) - фильм казахский, РУ нет, но и title нет.
                title = header[0].strip()
                original_title = ''
                year = header[1].strip()

            elif len(header[2]) > 4 and header[2][:4].isdigit():
                # год в заголовке как диапазон: "Голый пистолет (Коллекция) / Naked Gun: Collection / 1982-1994 / ПМ, ПД..."
                # или как перечень:
                # Клетка для чудаков (Клетка для безумцев) (Трилогия) / La Cage aux folles I, II, III / 1978, 1980, 1985 / ПМ, ПД / BDRip (1080p), HDTVRip (1080p)
                title = header[0].strip()
                original_title = header[1].strip()
                year = header[2].strip()[:4]
            else:
                # Если какой-то уебок написал каличный хедер, например, пропустил слеш, или еще что, не обрываем скан, и делаем по следующему алгоритму:
                # - Если есть хоть один слеш - cчитаем все, что до него - это title
                # - Если нет ни одного слеша, - берем первые 5 слов как title
                # - original_title делаем пустым
                # - год ставим как первые 4 цифры, найденные в строке, или текущий год, если цифры не найдены.

                # remove double spaces
                head = re.sub(r'\s+', ' ', s.text)
                if '/' in s.text:
                    title = head.split('/')[0]
                else:
                    b = [element.strip() for element in head.split(' ')]
                    title = ' '.join(b[:5])
                original_title = ''

                match = re.search(r'\d{4}', head)
                if match:
                    year = str(match.group())
                    year = year if year != '1080' else str(datetime.now().year)
                else:
                    year = str(datetime.now().year)

            # print(f'FOUND [{date_added:%d.%m.%y}]: {title} - {year}')
            logger.debug(f'FOUND [{date_added:%d.%m.%y}]: {title} - {year}')

            m = KinozalMovie(kinozal_id, title, original_title, year, date_added, dubbed)

            movies.append(m)

        print(f'FOUND {len(movies)} movies.')
        return movies, END_DATE_NOT_REACHED

    else:
        # log the error response
        # in case of 4xx or 5xx
        print(response)
        # todo А так вообще можно?
        raise Exception(response)


def get_details(m: KinozalMovie) -> tuple[KinozalMovie, float]:
    site = LinkConstructor(id=m.kinozal_id)

    response = requests.get(site.detail_url())

    if response.ok:
        soup = BeautifulSoup(response.content, "html.parser")

        imdb_part = soup.select_one('a:-soup-contains("IMDb")')
        if imdb_part:
            # todo weak assumption for [4]; may be need add some checks
            m.imdb_id = imdb_part['href'].split('/')[4]
            rating = imdb_part.find('span').text
            m.imdb_rating = float(rating) if is_float(rating) else None
        else:
            m.imdb_id = None
            m.imdb_rating = None

        kinopoisk_part = soup.select_one('a:-soup-contains("Кинопоиск")')
        if kinopoisk_part:
            # todo weak assumption for [4]; may be need add some checks
            m.kinopoisk_id = kinopoisk_part['href'].split('/')[4]
            rating = kinopoisk_part.find('span').text
            m.kinopoisk_rating = float(rating) if is_float(rating) else None
        else:
            m.kinopoisk_id = None
            m.kinopoisk_rating = None

        try:
            m.genres = soup.select_one('b:-soup-contains("Жанр:")').find_next_sibling().text
        except AttributeError:
            print("WARNING! CAN'T GET [genres]")
            m.genres = ''

        countries = soup.select_one('b:-soup-contains("Выпущено:")').find_next_sibling().text
        countries_list = Country.objects.values_list('name', flat=True)
        if countries:
            m.countries = ', '.join(list(c for c in countries.split(', ') if c in countries_list))
        else:
            m.countries = ''

        try:
            m.director = soup.select_one('b:-soup-contains("Режиссер:")').find_next_sibling().text
        except AttributeError:
            print("WARNING! CAN'T GET [director]")
            m.director = ''

        try:
            m.actors = soup.select_one('b:-soup-contains("В ролях:")').find_next_sibling().text
        except AttributeError:
            print("WARNING! CAN'T GET [actors]")
            m.actors = ''

        try:
            m.plot = soup.select_one('b:-soup-contains("О фильме:")').next_sibling.text.strip()
        except:
            print("WARNING! CAN'T GET [plot]")
            m.plot = ''

        translate_search = (soup.select_one('b:-soup-contains("Перевод:")'))
        if translate_search:
            m.translate = translate_search.next_sibling.strip()

        poster = soup.find('img', 'p200').attrs['src']
        if poster[:4] != 'http':
            poster = 'https://kinozal.tv' + poster
        m.poster = poster

        return m, response.elapsed.total_seconds()


def movie_audit(movies: list[KinozalMovie], user) -> list[KinozalMovie]:
    """
    Принимает на входе список объектов KinozalMovie.
    Объекты заполнены только самой просто инфой со страницы списка фильмов (но не со страницы фильма!)
    Каждый Объект сначала проходит простые проверки.
    Если прошел, тогда парсер сканирует страницу фильма, заполняет объект.

    Возвращает список объектов KinozalMovie, которые осталось только записать в базу.
    """
    result = []
    for m in movies:
        """
        LOGIC:
        - если уже есть в базе RSS - пропускаем
            ◦ так же этот фильм может быть уже в базе как Игнорируемый - в коде никаких дополнительных действий не требуется, просто не добавляем.
        - если есть в базе kinorium - пропускаем (любой статус в кинориуме, - просмотрено, буду смотреть, не буду смотреть)
            ◦ проверяем также частичное совпадение, и тогда записываем в базу, а пользователю предлагаем установить связь через поля кинориума
        - если фильм прошел проверки по базам kinozal и kinorium, тогда вытягиваем для него данные со страницы
        - проверяем через пользовательские фильтры
        - и вот теперь только заносим в базу 
        """
        print(f'PROCESS: {m.title} - {m.original_title} - {m.year}')

        """
        В этом месте нужно проверить наличие у релиза нормальной озвучки.
        Если у фильма есть норм. озвучка И у такого же фильма в базе MovieRSS статус "жду озвучку", то присвоить статус "есть озвучка" и continue
        """
        if m.dubbed and need_dubbed(m):
            print(' ┣━ FOUND DUBBING [x]')
            movie_in_db = MovieRSS.objects.filter(title=m.title, original_title=m.original_title, year=m.year).first()
            movie_in_db.priority = TRANS_FOUND
            movie_in_db.save(update_fields=['priority'])
            continue

        if exist_in_kinozal(m):
            print(' ┣━ SKIP [exist in kinozal]')
            continue
        """
        Возможна такая ситуация, что фильм попал в RSS, а потом я его посмотрел.
        Тогда уже существующий в RSS фильм нужно обновить (установить priority=SKIP)
        """


        exist, match_full, status = exist_in_kinorium(m)
        if exist and match_full:
            print(f' ┣━ SKIP [{status}]')
            continue
        elif exist and not match_full:
            print(f' ┣━ MARK AS PARTIAL [{status}]')
            m.kinorium_partial_match = True

        m, sec = get_details(m)
        print(f' ┣━ GET DETAILS: {sec:.1f}s')

        # Эта проверка выкидывает все, что через него не прошло
        if check_users_filters(user, m, priority=HIGH):
            m.priority = HIGH

            # Из оставшихся, некоторым назначаем низкий приоритет
            # тут логика такая - если фильм НЕ прошел проверку - то он подпадет как Low priority
            # А если прошел - остается в HIGH priority
            if not check_users_filters(user, m, priority=LOW):
                m.priority = LOW

        if m.priority in [LOW, HIGH]:  # Если фильм прошел проверки, то приорити будет или LOW или HIGH. Тогда записываем в базу, иначе - просто пропускаем.
            print(
                f' ┣━ ADD TO DB [prio={"low" if m.priority==LOW else "high"}] [partial={"YES" if m.kinorium_partial_match else "NO"}]')

            result.append(m)

    return result


def get_kinorium_first_search_results(data: str):
    """
    https://ru.kinorium.com/search/?q=%D1%82%D0%B5%D1%80%D0%BC%D0%B8%D0%BD%D0%B0%D1%82%D0%BE%D1%80%203
    :param data:
    :return:
    """
    payload = {'q': data}
    params = urlencode(payload, quote_via=quote_plus)
    # quote_plus - заменяет пробелы знаками +
    link = f"https://ru.kinorium.com/search/?{params}"

    response = requests.get(link)
    print(f'GRAB URL: {link}')
    soup = BeautifulSoup(response.content, "html.parser")
    elements = soup.select_one('.list.movieList')  # <div class="list movieList">

    id = soup.select_one('.list.movieList .item h3 a').attrs['href']  # like /2706046/
    link = 'https://ru.kinorium.com' + id

    first_result = None
    return link


def kinozal_search(kinozal_id: int):
    m = MovieRSS.objects.get(id=kinozal_id)
    results = []

    combined_titles = ' / '.join([m.title, m.original_title])
    if len(combined_titles) < 64:
        search_string = combined_titles
    else:
        search_string = m.title

    try:
        year = str(int(m.year))
    except ValueError:
        year = None

    V_HD = 3  # Рипы HD(1080 и 720)
    V_4K = 7  # 4K

    for quality in [V_HD, V_4K]:

        if year is not None:
            l = LinkConstructor(s=search_string, d=year, v=quality)
        else:
            l = LinkConstructor(s=search_string, v=quality)
        # for TERMINATOR, l = "https://kinozal.tv/browse.php?s=%F2%E5%F0%EC%E8%ED%E0%F2%EE%F0&g=0&c=1002&v=7&d=2019&w=0&t=0&f=0"

        response = requests.get(l.search_url())
        print(f'GRAB URL: {l.search_url()}')
        logger.info(f'GRAB URL: {l.search_url()}')

        if response.ok:
            soup = BeautifulSoup(response.content, "html.parser")
            movies_elements = soup.find_all('tr', 'bg')

            for element in movies_elements:
                m = KinozalSearch()

                m.id = element.a['href'].split('=')[1]
                m.header = element.a.text
                m.size = element.find_all('td', 's')[1].text
                m.seed = element.find('td', {'class': 'sl_s'}).text
                m.peer = element.find('td', {'class': 'sl_p'}).text
                m.created = element.find_all('td', 's')[2].text
                m.link = 'https://kinozal.tv' + element.a['href']
                if quality == V_4K:
                    m.is_4k = True
                if 'SDR' in m.header:
                    m.is_sdr = True

                results.append(m)

        else:
            raise Exception(f'ERROR: {response.content}')

    return results
