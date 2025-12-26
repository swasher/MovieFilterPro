import re
import dataclasses
import logging
import asyncio
from bs4 import BeautifulSoup
from datetime import date, datetime, timedelta

from django.db.models import Q
from requests.exceptions import HTTPError, Timeout, RequestException

from movie_filter_pro.settings import HIGH, LOW, DEFER, SKIP, WAIT_TRANS, TRANS_FOUND
from moviefilter.classes import KinozalMovie
from moviefilter.kinozal import KinozalClient
from moviefilter.models import Country, MovieRSS, Kinorium
from moviefilter.models import UserPreferences

from .util import is_float
from .exceptions import DetailsFetchError, ScanCancelled

from .checks import exist_in_kinorium, exist_in_kinozal, check_users_filters, need_dubbed
from web_logger import log, LogType

kinozal_logger = logging.getLogger('kinozal')


def kinozal_scan(start_page: int, scan_to_date: date, user, cancel_event: asyncio.Event):
    """
    Запускает сканирование кинозала. Проходит сканированием по всем страницам, начиная с start_page (обычно 0, но
    пользователь может указать конкретную страницу, если оборвался длинный скан, и до даты последнего сканирования.)
    :param start_page: стартовая страница, начинается от нуля.
    :param scan_to_date:
    :param user:
    :cancel_event: объект, который меняется, если пользователь нажал Cancel во время сканирования.
    :return:
    """

    last_day_reached = False
    last_page_reached = False
    counter = 0  # сколько нашлось фильмов для записи в базу
    prefs = UserPreferences.get()

    if start_page is None:
        current_page = 0
    else:
        current_page = start_page

    while not last_day_reached and current_page <= 100:

        try:
            # Получаем список всех фильмов со страницы. Если достигли нужной даты, то last_day_reached возврашается как True
            movies, last_day_reached = parse_page(current_page, scan_to_date, cancel_event)

            # Проверяем список по фильтрам, и получаем отфильтрованный и заполненный список, который можно уже заносить в базу.
            # movie_audit удаляет из списка movies фильмы, не прошедшие проверку, а так-же заполняет каждый movie дополнительными данными.
            movies = movie_audit(movies, user, prefs, cancel_event)
        except DetailsFetchError as e:
            if cancel_event.is_set():
                raise ScanCancelled()
            log(
                "Scan terminated due to a critical error while fetching movie details.",
                logger_name=LogType.ERROR,
            )
            raise e
        except ScanCancelled:
            log("kinozal_scan: Scan cancelled by user")
            return counter

        # записываем фильмы в базу
        if movies:
            # logger.debug(f"SAVE TO DB")
            # logger.info(f"SAVE TO DB infoinfoinfoinfoinfo")
            # logger.error(f"SAVE TO DB ERROR ERROR ERROR ERROR ERROR ")
            log(f'SAVE TO DB: [{len(movies)} movies]')

            counter += len(movies)
            for m in movies:
                # todo использовать bulk_create
                MovieRSS.objects.get_or_create(title=m.title, original_title=m.original_title, year=m.year,
                                               defaults=dataclasses.asdict(m))
        log('')

        # переходим к сканированию следующей странице
        current_page += 1

    return counter


def parse_page(page_number: int, scan_to_date: date, cancel_event) -> tuple[list[KinozalMovie], bool]:
    """
    Принимает:
     - номер страницы, которую будем сканировать.
     - дату, до которой нужно будет сканировать.
    """
    END_DATE_REACHED = True
    END_DATE_NOT_REACHED = False

    client = KinozalClient()
    movies: list[KinozalMovie] = []

    log('---')
    log(f'\nStart scanning Kinozal page #{page_number}')

    # download the HTML document
    # with an HTTP GET request
    # response = requests.get(site.url())
    response = client.browse_movies(page=page_number)

    if response.ok:
        soup = BeautifulSoup(response.content, "html.parser")

        movies_elements = soup.find_all('tr', 'bg')

        for m in movies_elements:
            """
            movie head format:
            
            'Красная жара / Red Heat / 1988 / ПМ / UHD / BDRip (1080p)' - обычно такая форма
            'Наследие / 2023 / РУ, СТ / WEB-DL (1080p)'                 - если русский, то нет original_title
            'Телекинез / 2022-2023 / РУ / WEB-DL (1080p)'               - встречается и такое (тогда берем первые 4 цифры)
            
            """

            if cancel_event.is_set():
                log("parse_page: Scan cancelled by user")
                raise ScanCancelled()

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
            log(f'FOUND [{date_added:%d.%m.%y}]: {title} - {year}')

            m = KinozalMovie(kinozal_id, title, original_title, year, date_added, dubbed)

            movies.append(m)

        log(f'FOUND {len(movies)} movies.')
        return movies, END_DATE_NOT_REACHED

    else:
        # log the error response
        # in case of 4xx or 5xx
        print(response)
        # todo А так вообще можно?
        raise Exception(response)


def get_details(m: KinozalMovie) -> tuple[KinozalMovie, float]:
    """
    Парсит данные со страницы фильма. Получает на вход частично заполненный данными объект KinozalMovie,
    добавляет найденные данные и возвращает этот же объект.

    :param m:
    :return: KinozalMovie, время сканирования
    """
    client = KinozalClient()
    pref = UserPreferences.get()

    try:
        response = client.get_movie_details(m.kinozal_id)
        response.raise_for_status()
    # except HTTPError as http_err:
    #     log(f"HTTP error occurred: {http_err}", logger_name=LogType.ERROR)
    #     return None, 0
    # except Timeout:
    #     log("The request timed out", logger_name=LogType.ERROR)
    #     return None, 0
    # except RequestException as req_err:
    #     log(f"An error occurred: {req_err}", logger_name=LogType.ERROR)
    #     return None, 0
    # except Exception as e:
    #     log(f"An unexpected error occurred: {e}", logger_name=LogType.ERROR)
    #     return None, 0
    except RequestException as e:
        log(f"Failed to get details for movie id {m.kinozal_id} due to a network error.", logger_name=LogType.ERROR,)
        raise DetailsFetchError(f"Network error for movie id {m.kinozal_id}") from e
    except Exception as e:
        log(f"An unexpected error occurred while getting details for movie id {m.kinozal_id}.", logger_name=LogType.ERROR)
        raise DetailsFetchError(f"Unexpected error for movie id {m.kinozal_id}") from e

    soup = BeautifulSoup(response.content, "html.parser")

    # validate if sout contain valid kinozal detail page
    download_link = soup.find('a', href=lambda x: x and f'download.php?id={m.kinozal_id}' in x)
    if not download_link:
        #return f"Movie details page validation failed for ID {m.kinozal_id}: download link not found"
        kinozal_logger.error(f'NO VALID SOUP FOR id {m.kinozal_id}.')
    else:
        kinozal_logger.info(f'Successfully load detaild for id {m.kinozal_id}.')

    if imdb_part := soup.select_one('a:-soup-contains("IMDb")'):
        # todo weak assumption for [4]; probably needs to add some checks
        m.imdb_id = imdb_part['href'].split('/')[4]
        try:
            # Иногда уроды неправильно оформляют раздачу, и imdb блок есть, но он криво сделан, не в том месте, не содержит рейтинга.
            # Было такое, что imdb_part.find('span') становился None
            rating = imdb_part.find('span').text
            m.imdb_rating = float(rating) if is_float(rating) else None
        except AttributeError:
            log(f"Failed to parse IMDB rating for movie id {m.kinozal_id}", logger_name=LogType.ERROR)

    if kinopoisk_part := soup.select_one('a:-soup-contains("Кинопоиск")'):
        # todo weak assumption for [4]; may be need add some checks
        m.kinopoisk_id = kinopoisk_part['href'].split('/')[4]
        try:
            rating = kinopoisk_part.find('span').text
            m.kinopoisk_rating = float(rating) if is_float(rating) else None
        except AttributeError:
            log(f"Failed to parse Kinopoisk rating for movie id {m.kinozal_id}", logger_name=LogType.ERROR)

    if genres_element := soup.select_one('b:-soup-contains("Жанр:")'):
        next_element = genres_element.find_next_sibling('span', class_='lnks_tobrs')
        if next_element:
            m.genres = next_element.text
        else:
            m.genres = ''
    else:
        m.genres = ''

    if countries_element := soup.select_one('b:-soup-contains("Выпущено:")'):
        next_element = countries_element.find_next_sibling('span', class_='lnks_tobrs')
        if next_element:
            countries = next_element.text

            known_countries_list = Country.objects.values_list('name', flat=True)

            if countries:
                m.countries = ', '.join(list(c for c in countries.split(', ') if c in known_countries_list))
            else:
                m.countries = ''

    director_element = soup.select_one('b:-soup-contains("Режиссер:")')
    if director_element:
        next_element = director_element.find_next_sibling('span', class_='lnks_toprs')
        m.director = next_element.text.strip() if next_element else ""
    else:
        m.director = ''

    actors_element = soup.select_one('b:-soup-contains("В ролях:")')
    if actors_element:
        next_element = actors_element.find_next_sibling('span', class_='lnks_toprs')
        m.actors = next_element.text.strip() if next_element else ['']
    else:
        m.actors = ['']

    try:
        m.plot = soup.select_one('b:-soup-contains("О фильме:")').next_sibling.text.strip()
    except:
        log(f"CAN'T GET [plot] for {m.original_title} with kinozal_id {m.kinozal_id}", logger_name=LogType.DEBUG)

    translate_search = (soup.select_one('b:-soup-contains("Перевод:")'))
    if translate_search:
        m.translate = translate_search.next_sibling.getText().strip()

    poster = soup.find('img', 'p200').attrs['src']
    # используют и внешние линки (тогда в нем есть http), и внутренние относительные линки (тогда надо добавить домен)
    if poster[:4] != 'http':
        poster = f'https://{pref.kinozal_domain}/{poster}'
    m.poster = poster

    # DEBUG
    kinozal_logger.info(f'\n == FETCHED DATA FOR {m.title} ==')
    kinozal_logger.info(f'{m.original_title=}')
    kinozal_logger.info(f'{m.year=}')
    kinozal_logger.info(f'{m.imdb_id=}')
    kinozal_logger.info(f'{m.imdb_rating=}')
    kinozal_logger.info(f'{m.kinopoisk_id=}')
    kinozal_logger.info(f'{m.kinopoisk_rating=}')
    kinozal_logger.info(f'{m.genres=}')
    kinozal_logger.info(f'{m.countries=}')
    kinozal_logger.info(f'{m.director=}')
    kinozal_logger.info(f'{m.actors=}')
    kinozal_logger.info(f'{m.plot=}'[:200])
    kinozal_logger.info(f'{m.translate=}')
    kinozal_logger.info(f'{m.poster=}')

    return m, response.elapsed.total_seconds()


# def movie_audit(movies: list[KinozalMovie], user, cancel_event: asyncio.Event) -> list[KinozalMovie]:
#     """
#     Принимает на входе список объектов KinozalMovie.
#     Объекты заполнены только самой просто инфой со страницы списка фильмов (но не со страницы фильма!)
#     Каждый Объект сначала проходит простые проверки, нужно ли продолжать с ним работу.
#     Если прошел, тогда парсер сканирует страницу фильма, заполняет объект.
#
#     Возвращает список объектов KinozalMovie, которые осталось только записать в базу.
#     """
#
#     result = []
#     for m in movies:
#         """
#         LOGIC:
#         - если уже есть в базе RSS - пропускаем
#             ◦ так же этот фильм может быть уже в базе как Игнорируемый - в коде никаких дополнительных действий не требуется, просто не добавляем.
#         - если есть в базе kinorium - пропускаем (любой статус в кинориуме, - просмотрено, буду смотреть, не буду смотреть)
#             ◦ проверяем также частичное совпадение, и тогда записываем в базу, а пользователю предлагаем установить связь через поля кинориума
#         - если фильм прошел проверки по базам kinozal и kinorium, тогда вытягиваем для него данные со страницы
#         - проверяем через пользовательские фильтры
#         - и вот теперь только заносим в базу
#         """
#
#         if cancel_event.is_set():
#             log("movie_audit: Scan cancelled by user")
#             # break - для более "мягкого" выхода, заканчивает цикл и записывает уже пройденные фильмы в базу
#             # Если нужно прервать сразу и полностью, можно использовать `raise ScanCancelled()`
#             # break
#             raise ScanCancelled()
#
#         log(f'<b>PROCESS:</b> {m.title} - {m.original_title} - {m.year}')
#         #kinozal_logger.info(f'PROCESS: {m.title} - {m.original_title} - {m.year}')
#
#         """
#         В этом месте нужно проверить наличие у релиза нормальной озвучки.
#         Если у фильма есть норм. озвучка И у такого же фильма в базе MovieRSS статус "жду озвучку", то присвоить статус "есть озвучка" и continue
#         """
#         if m.dubbed and need_dubbed(m):
#             log(' ┣━ FOUND DUBBING [x]')
#             movie_in_db = MovieRSS.objects.filter(title=m.title, original_title=m.original_title, year=m.year).first()
#             movie_in_db.priority = TRANS_FOUND
#             movie_in_db.save(update_fields=['priority'])
#             continue
#
#         if exist_in_kinozal(m):
#             log(' ┣━ SKIP [exist in kinozal]')
#             continue
#         """
#         Возможна такая ситуация, что фильм попал в RSS, а потом я его посмотрел.
#         Тогда уже существующий в RSS фильм нужно обновить (установить priority=SKIP)
#         """
#         exist, match_full, status = exist_in_kinorium(m)
#         if exist and match_full:
#             log(f" ┣━ SKIP [{status}]")
#             continue
#         elif exist and not match_full:
#             log(f" ┣━ MARK AS PARTIAL [{status}]")
#             m.kinorium_partial_match = True
#
#         m, sec = get_details(m)  # <--------------------------- MAIN FUNCTION FOR GET DETAILS FOR THE MOVIE
#         log(f' ┣━ GET DETAILS: {sec:.1f}s')
#
#         # Эта проверка выкидывает все, что через него не прошло
#         if check_users_filters(user, m, priority=HIGH):
#             m.priority = HIGH
#
#             # Из оставшихся, некоторым назначаем низкий приоритет
#             # тут логика такая - если фильм НЕ прошел проверку - то он подпадет как Low priority
#             # А если прошел - остается в HIGH priority
#             if not check_users_filters(user, m, priority=LOW):
#                 m.priority = LOW
#
#         if m.priority in [LOW, HIGH]:  # Если фильм прошел проверки, то приорити будет или LOW или HIGH. Тогда записываем в базу, иначе - просто пропускаем.
#             log(f' ┣━ ADD TO DB [prio={"low" if m.priority == LOW else "high"}] [partial={"YES" if m.kinorium_partial_match else "NO"}]')
#
#             result.append(m)
#
#     return result


def movie_audit(movies: list[KinozalMovie], user, prefs, cancel_event: asyncio.Event) -> list[KinozalMovie]:
    """
    Оптимизированная версия.
    Выполняет предварительную загрузку данных, чтобы минимизировать количество запросов к БД внутри цикла.

    Эта "предварительная загрузка данных" написана AI и там хрен поймешь, что происходит.
    Но суть такая, что вместо того, чтобы дергать БД в каждом цикле по нескольку раз, мы достаем нужные данные из БД
    один раз перед циклом, и затем уже работаем с ними в ОЗУ.

    Принимает на входе список объектов KinozalMovie.
    Объекты заполнены только самой просто инфой со страницы списка фильмов (но не со страницы фильма!)
    Каждый Объект сначала проходит простые проверки, нужно ли продолжать с ним работу.
    Если прошел, тогда парсер сканирует страницу фильма, заполняет объект.

    Возвращает список объектов KinozalMovie, которые осталось только записать в базу.
    """

    # Начало блока предварительной загрузки данных ---

    # 1. Собираем все возможные идентификаторы из входящего списка фильмов
    if not movies:
        return []

    movie_titles = {m.title for m in movies if m.title}
    movie_original_titles = {m.original_title for m in movies if m.original_title}
    # Годы могут быть диапазонами (напр. '1982-1994'), берем только первые 4 цифры
    movie_years_str = {m.year[:4] for m in movies if m.year and m.year[:4].isdigit()}

    # 2. Предварительная загрузка из MovieRSS для проверок exist_in_kinozal и need_dubbed
    # Загружаем в словарь для быстрой проверки: {(title, original_title, year): priority}
    rss_check_query = Q(title__in=movie_titles) | Q(original_title__in=movie_original_titles)
    existing_rss_movies = {
        (movie.title, movie.original_title, str(movie.year)): movie.priority
        for movie in MovieRSS.objects.filter(rss_check_query).filter(year__in=[int(y) for y in movie_years_str])
    }

    # 3. Предварительная загрузка из Kinorium для проверки exist_in_kinorium
    kinorium_check_query = Q(title__in=movie_titles) | Q(original_title__in=movie_original_titles)
    potential_kinorium_movies = Kinorium.objects.filter(kinorium_check_query).filter(year__in=[int(y) for y in movie_years_str])

    # Словари для быстрого поиска по разным типам совпадений
    kinorium_full_match = {(m.title, m.original_title, str(m.year)): m.get_status_display() for m in
                           potential_kinorium_movies}
    kinorium_partial_title_year = {(m.title, str(m.year)): m.get_status_display() for m in potential_kinorium_movies}
    kinorium_partial_original_year = {(m.original_title, str(m.year)): m.get_status_display() for m in
                                      potential_kinorium_movies}

    # --- ИЗМЕНЕНИЕ: Конец блока предварительной загрузки данных ---



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

        if cancel_event.is_set():
            log("movie_audit: Scan cancelled by user")
            # break - для более "мягкого" выхода, заканчивает цикл и записывает уже пройденные фильмы в базу
            # Если нужно прервать сразу и полностью, можно использовать `raise ScanCancelled()`
            # break
            raise ScanCancelled()

        log(f'<b>PROCESS:</b> {m.title} - {m.original_title} - {m.year}')
        #kinozal_logger.info(f'PROCESS: {m.title} - {m.original_title} - {m.year}')

        # Используем быстрые проверки по данным в памяти ---
        year_str_for_check = m.year if m.year.isdigit() else m.year[:4]
        movie_key = (m.title, m.original_title, year_str_for_check)

        """
        В этом месте нужно проверить наличие у релиза нормальной озвучки.
        Если у фильма есть норм. озвучка И у такого же фильма в базе MovieRSS статус "жду озвучку", то присвоить статус "есть озвучка" и continue
        """
        # Проверка 1: Фильм ждет озвучку?
        if m.dubbed and existing_rss_movies.get(movie_key) == WAIT_TRANS:
            log(' ┣━ FOUND DUBBING [x]')
            # Помечаем фильм в базе как "есть озвучка". Это единственный запрос к БД, который остался в цикле.
            MovieRSS.objects.filter(title=m.title, original_title=m.original_title, year=m.year).update(
                priority=TRANS_FOUND)
            continue

        # Проверка 2: Фильм уже есть в RSS?
        if movie_key in existing_rss_movies:
            log(' ┣━ SKIP [exist in kinozal]')
            continue

        """
        Возможна такая ситуация, что фильм попал в RSS, а потом я его посмотрел.
        Тогда уже существующий в RSS фильм нужно обновить (установить priority=SKIP)
        """
        # Проверка 3: Фильм уже есть в Kinorium?
        status = kinorium_full_match.get(movie_key)
        if status:
            log(f" ┣━ SKIP [{status}]")
            continue

        status = kinorium_partial_title_year.get((m.title, year_str_for_check))
        if status:
            log(f" ┣━ MARK AS PARTIAL [{status}]")
            m.kinorium_partial_match = True
        else:
            status = kinorium_partial_original_year.get((m.original_title, year_str_for_check))
            if status:
                log(f" ┣━ MARK AS PARTIAL [{status}]")
                m.kinorium_partial_match = True

        m, sec = get_details(m)  # <--------------------------- MAIN FUNCTION FOR GET DETAILS FOR THE MOVIE
        log(f' ┣━ GET DETAILS: {sec:.1f}s')

        # Эта проверка выкидывает все, что через него не прошло
        if check_users_filters(user, m, priority=HIGH, prefs=prefs):
            m.priority = HIGH

            # Из оставшихся, некоторым назначаем низкий приоритет
            # тут логика такая - если фильм НЕ прошел проверку - то он подпадет как Low priority
            # А если прошел - остается в HIGH priority
            if not check_users_filters(user, m, priority=LOW, prefs=prefs):
                m.priority = LOW

        if m.priority in [LOW, HIGH]:  # Если фильм прошел проверки, то приорити будет или LOW или HIGH. Тогда записываем в базу, иначе - просто пропускаем.
            log(f' ┣━ ADD TO DB [prio={"low" if m.priority == LOW else "high"}] [partial={"YES" if m.kinorium_partial_match else "NO"}]')

            result.append(m)

    return result
