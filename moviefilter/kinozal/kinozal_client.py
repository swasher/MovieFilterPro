import requests
from urllib.parse import urlencode, quote_plus

from requests import Response

from moviefilter.models import UserPreferences
from web_logger import log, LogType

from .cloudflare import CLOUDFLARE_UA, cloudflare_bypass, detect_challenge


class KinozalDomainNotConfigured(RuntimeError):
    """Не выбрано ни одного зеркала Kinozal в настройках."""

    def __init__(
        self,
        message: str = "Не настроено зеркало Kinozal. Выбери его в Preferences → Зеркала kinozal.",
    ):
        super().__init__(message)


def normalize_kinozal_domain(raw: str | None) -> str:
    """
    Приводит домен зеркала к каноническому виду: без схемы, пути и порта.
    """
    domain = (raw or "").strip().lower()
    if "://" in domain:
        domain = domain.split("://", 1)[1]
    domain = domain.split("/", 1)[0].split(":", 1)[0].strip()
    return domain


def get_active_kinozal_domain() -> str:
    """
    Активное зеркало Kinozal.

    Читается из UserPreferences при каждом обращении, чтобы переключение
    зеркала в настройках применялось без перезапуска процесса.
    """
    return normalize_kinozal_domain(UserPreferences.get().kinozal_domain)


class LinkConstructor:
    """
    Конструктор ссылок для сайта Kinozal. Создает ссылки по типу
    https: // kinozal.tv / browse.php?c = 1002 & v = 3 & page = 74


    Параметры фильтрации:
    c = 1001 - Все сериалы
    c = 1002 - Все фильмы
    c = 1003 - Все мультфильмы
    v = 3 - Рипы HD (1080 и 720)
    v = 7 - 4K
    page - номер страницы (первая - не нужно указывать page, вторая - номер 1)
    s - поиск по названию
    d - год
    id - идентификатор для детальной страницы
    """

    def __init__(self, c: int = 1002, v: int = 3, page: int = 0, d: str = '', s: str = '',
                 id: int = None):
        """
        Инициализация конструктора ссылок.

        Args:
            base_domain: Базовый домен сайта (например, 'kinozal.tv')
            c: Категория контента (по умолчанию фильмы)
            v: Качество видео (по умолчанию HD)
            page: Номер страницы (начинается с 0)
            d: Год для фильтрации
            s: Строка поиска
            id: ID для детальной страницы
        """
        self.c = c
        self.v = v
        self.page = page if page else 0
        self.id = id
        self.d = d
        self.s = s

    @property
    def domain(self) -> str:
        """Активное зеркало Kinozal (всегда актуальное, из UserPreferences)."""
        return get_active_kinozal_domain()

    def _require_domain(self) -> str:
        domain = self.domain
        if not domain:
            raise KinozalDomainNotConfigured()
        return domain

    @property
    def _browse(self) -> str:
        """Базовая ссылка для страница-списка фильмов."""
        # 'https://kinozal.tv/browse.php?'
        return f'https://{self._require_domain()}/browse.php?'

    @property
    def _details(self) -> str:
        """Базовая ссылка для страницы с деталями фильм."""
        # 'https://kinozal.tv/details.php?'
        return f'https://{self._require_domain()}/details.php?'

    @staticmethod
    def link(root, payload) -> str:
        """
        # todo НЕ ПОНЯТНО, ЧТО ИМЕННО ЭТО ДЕЛАЕТ
        Создает полную ссылку из корня и параметров.

        Args:
            root: Корневая часть ссылки
            payload: Словарь параметров для URL

        Returns:
            Полная ссылка с параметрами
        """
        # параметр quote_plus - заменяет пробелы знаками +
        params = urlencode(payload, quote_via=quote_plus)
        return f"{root}{params}"

    def url(self) -> str:
        """
        # todo НЕ ПОНЯТНО, ЧТО ИМЕННО ЭТО ДЕЛАЕТ
        Создает ссылку на страницу фильмов/сериалов с заданными параметрами.

        Returns:
            URL для просмотра каталога
        """
        payload = {'c': self.c, 'v': self.v, 'page': self.page}
        return self.link(self._browse, payload)

    def poster(self, relative_link: str) -> str:
        """
        Создает полную ссылку на постер фильма.
        Я решил эту маленькую логику оставить в get_details(), так что это deprecated.

        Args:
            relative_link: Относительная ссылка на постер

        Returns:
            Полная ссылка на постер
        """
        return f'https://{self._require_domain()}/{relative_link}'

    def search_url(self) -> str:
        """
        Создает ссылку на страницу поиска фильмов с заданными параметрами.
        Используется для поиска "подобных фильмов" при нажатии на кнопку Download.
        Типа (только в urlencode)
        https://kinozal.guru/browse.php?s=Кресент-Сити+%2F+Crescent+City&d=2024&v=3

        Returns:
            URL для поиска
        """
        payload = {'s': self.s, 'd': self.d, 'v': self.v}
        # Удаляем None значения из payload
        payload = {k: v for k, v in payload.items() if v is not None}
        return self.link(self._browse, payload)

    def detail_url(self):
        """
        Создает ссылку на детальную страницу фильма.

        Returns:
            URL детальной страницы
        """
        if not self.id:
            raise ValueError("ID должен быть установлен для создания детальной ссылки")
        payload = {'id': self.id}
        return self.link(self._details, payload)

    def prev_page(self) -> str:
        """
        Возвращает URL предыдущей страницы.

        Returns:
            URL предыдущей страницы

        Raises:
            Exception: Если уже на первой странице
        """
        # первая страница на moviefilter'е имеет номер 0
        if self.page > 0:
            self.page -= 1
            return self.url()
        else:
            raise Exception("Невозможно перейти на предыдущую страницу - уже на первой")

    def next_page(self):
        """
        Переходит на следующую страницу и возвращает URL.

        Returns:
            URL следующей страницы
        """
        self.page += 1
        return self.url()


class KinozalClient:
    """
    Синглтон клиент для работы с сайтом Kinozal.
    Обеспечивает авторизацию через куки и интеграцию с LinkConstructor.
    """

    _instance = None

    def __new__(cls, *args, **kwargs):
        """Реализация паттерна Синглтон."""
        if not cls._instance:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """
        Инициализация клиента (выполняется только один раз для синглтона).
        """
        # Проверяем, что инициализация еще не была выполнена
        if hasattr(self, 'initialized'):
            return

        # Настройка HTTP сессии
        self.session = requests.Session()
        self.session.headers.update({
            # UA обязан совпадать с браузером эскалации (cf_clearance привязан к UA).
            "User-Agent": CLOUDFLARE_UA
        })

        # Домен и куки читаются динамически из UserPreferences (см. property domain
        # и _refresh_cookies), чтобы переключение зеркала и обновление cookies
        # применялись без перезапуска процесса.
        self.initialized = True

    @property
    def domain(self) -> str:
        """Текущее активное зеркало Kinozal (читается из UserPreferences каждый раз)."""
        return get_active_kinozal_domain()

    def _require_domain(self) -> str:
        domain = self.domain
        if not domain:
            raise KinozalDomainNotConfigured()
        return domain

    def _refresh_cookies(self) -> None:
        """Синхронизирует cookies сессии с текущими настройками."""
        preferences = UserPreferences.get()
        self.session.cookies.update({
            "uid": preferences.cookie_uid or "",    # Значение куки uid для авторизации
            "pass": preferences.cookie_pass or "",  # Значение куки pass для авторизации
        })

    def _auth_cookie_params(self) -> list[dict]:
        """Куки uid/pass в Playwright-формате для браузерной эскалации.

        Домен выводится из активного зеркала ('.' + хост). Значения не логируются.
        """
        preferences = UserPreferences.get()
        domain = self._require_domain()
        cookies: list[dict] = []
        if preferences.cookie_uid:
            cookies.append({"name": "uid", "value": preferences.cookie_uid, "domain": f".{domain}", "path": "/"})
        if preferences.cookie_pass:
            cookies.append({"name": "pass", "value": preferences.cookie_pass, "domain": f".{domain}", "path": "/"})
        return cookies

    def get_html_response(self, path_or_constructor, **kwargs) -> Response:
        """
        Выполняет GET запрос.

        Args:
            path_or_constructor: Строка пути, URL или экземпляр LinkConstructor
            **kwargs: Дополнительные параметры для requests.get

        Транспортный слой обходит Cloudflare-челлендж: обычный requests-запрос,
        при детекции челленджа — браузерная эскалация через Scrapling. Вызывающий
        код о Cloudflare ничего не знает и получает обычный requests.Response.
        """
        self._refresh_cookies()

        # Если передали LinkConstructor
        if isinstance(path_or_constructor, LinkConstructor):
            url = path_or_constructor.url()
        # Если строка с полным URL
        elif isinstance(path_or_constructor, str) and path_or_constructor.startswith('http'):
            url = path_or_constructor
        # Если относительный путь
        else:
            url = f"https://{self._require_domain()}{path_or_constructor}"

        s = self.session

        # Подкладываем закэшированный cf_clearance, если он есть для этого домена.
        cloudflare_bypass.apply_clearance(s, url)

        response = s.get(url, **kwargs)

        # Cloudflare-челлендж? Тогда обычный requests не получил контент — эскалируем.
        challenge_reasons = detect_challenge(response.content, response.status_code)
        if challenge_reasons:
            for reason in challenge_reasons:
                log(f"[CF] челлендж на {url}: {reason}", logger_name=LogType.ERROR)
            response = cloudflare_bypass.escape(url, s, self._auth_cookie_params())

        return response

    def download_torrent(self, kinozal_id: int):
        """
        Скачивает торрент-файл по ID.

        Args:
            kinozal_id: ID торрента на сайте

        Returns:
            Response объект с содержимым торрент-файла
        """
        url = f"https://dl.{self._require_domain()}/download.php?id={kinozal_id}"
        self._refresh_cookies()
        return self.session.get(url)

    # === Методы интеграции с LinkConstructor ===

    def create_link_constructor(self, **kwargs):
        """
        Фабричный метод для создания LinkConstructor с автоматической подстановкой домена.

        Args:
            **kwargs: Параметры для LinkConstructor (c, v, page, d, s, id)

        Returns:
            Новый экземпляр LinkConstructor
        """
        return LinkConstructor(**kwargs)

    def get_with_constructor(self, constructor_params):
        """
        Универсальный метод для выполнения запроса через LinkConstructor.

        Args:
            constructor_params: Словарь параметров для LinkConstructor

        Returns:
            Response объект
        """
        constructor = self.create_link_constructor(**constructor_params)
        return self.get_html_response(constructor.url())

    # === Удобные методы-обертки для частых операций ===

    def browse_movies(self, page=0, quality=3, **kwargs):
        """
        Просмотр каталога фильмов.

        Args:
            page: Номер страницы (по умолчанию 0)
            quality: Качество видео (3=HD, 7=4K)
            **kwargs: Дополнительные параметры

        Returns:
            Response с HTML страницей каталога фильмов
        """
        constructor = self.create_link_constructor(c=1002, page=page, v=quality, **kwargs)
        #log(f'GRAB URL: {constructor.url()}')
        return self.get_html_response(constructor.url())

    def browse_series(self, page=0, quality=3, **kwargs):
        """
        Просмотр каталога сериалов.

        Args:
            page: Номер страницы (по умолчанию 0)
            quality: Качество видео (3=HD, 7=4K)
            **kwargs: Дополнительные параметры

        Returns:
            Response с HTML страницей каталога сериалов
        """
        constructor = self.create_link_constructor(c=1001, page=page, v=quality, **kwargs)
        return self.get_html_response(constructor.url())

    def search_movies(self, query, year=None, quality=3):
        """
        Поиск фильмов по названию.

        Args:
            query: Поисковый запрос
            year: Год для фильтрации (опционально)
            quality: Качество видео (3=HD, 7=4K)

        Returns:
            Response с результатами поиска
        """
        constructor = self.create_link_constructor(c=1002, s=query, d=year, v=quality)
        return self.get_html_response(constructor.search_url())

    def get_movie_details(self, movie_id):
        """
        Получение детальной информации о фильме.

        Args:
            movie_id: ID фильма на сайте

        Returns:
            Response с HTML детальной страницы
        """
        constructor = self.create_link_constructor(id=movie_id)
        return self.get_html_response(constructor.detail_url())

    def paginate(self, constructor_params, max_pages=10):
        """
        Генератор для автоматической пагинации.

        Args:
            constructor_params: Базовые параметры для LinkConstructor
            max_pages: Максимальное количество страниц для обхода

        Yields:
            Response объекты для каждой страницы
        """
        for page in range(max_pages):
            params = constructor_params.copy()
            params['page'] = page
            yield self.get_with_constructor(params)


# === Пример использования ===

if __name__ == "__main__":
    # Создание клиента-синглтона
    client = KinozalClient()

    # Использование через удобные методы
    movies_page = client.browse_movies(page=1, quality=7)  # первая страница, 4K фильмы
    search_results = client.search_movies("Дюна", year=2021)
    movie_details = client.get_movie_details(12345)

    # Использование через фабричный метод
    link_builder = client.create_link_constructor(c=1001, page=5)
    series_page = client.get_html_response(link_builder.url())

    # Независимое использование LinkConstructor
    independent_link = LinkConstructor("kinozal.tv", c=1003, page=2)
    cartoon_url = independent_link.url()

    # Автоматическая пагинация
    for page_response in client.paginate({'c': 1002, 'v': 3}, max_pages=5):
        print(f"Обработка страницы: {page_response.url}")
