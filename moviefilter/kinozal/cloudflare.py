"""
Обход Cloudflare у Kinozal (managed-челлендж) через Scrapling StealthyFetcher.

Принцип HTTP-first (см. scrapling-demo/KINOZAL-CLOUDFLARE-RESEARCH.md):
обычные запросы идут через requests; браузер запускается ТОЛЬКО при обнаружении
челленджа. После успешного решения полученный `cf_clearance` переносится обратно
в requests-сессию — это оптимизация, а не критический путь: если clearance не
подхватится (Cloudflare иногда привязывает его к TLS-отпечатку клиента), эскалация
в любом случае возвращает готовый HTML.

ВАЖНО: браузеру НЕ передаётся фиксированный User-Agent. Scrapling сам генерирует
консистентную пару UA+fingerprint под реальный headless Chromium (на сервере это
Linux). Передача Windows-UA в Linux-браузер ломает отпечаток, и Cloudflare уходит
в интерактивную капчу, которую headless не решает (подтверждено на проде).

Модуль не должен тянуть браузерный движок при импорте: `scrapling` импортируется
лениво, внутри эскалации.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from datetime import timedelta
from urllib.parse import urlparse

import requests

from web_logger import log, LogType

# User-Agent для обычного requests-клиента (до первой эскалации). После успешной
# эскалации requests-сессия переключается на реальный UA браузера, чтобы
# cf_clearance (привязанный к UA) подхватывался.
CLOUDFLARE_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/156.0.0.0 Safari/537.36"
)

# Таймаут браузерной эскалации в мс. Managed-Turnstile у kinozal иногда решается
# только со 2-й попытки солвера (140–200 с), поэтому 180 с.
CLOUDFLARE_TIMEOUT_MS = 180_000

# Куки Cloudflare, которые переносятся из браузера в requests-сессию.
_CLOUDFLARE_COOKIE_NAMES = ("cf_clearance", "cf_bm", "__cf_bm")

_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)


class CloudflareBlockedError(RuntimeError):
    """Cloudflare не пропустил запрос даже после браузерной эскалации."""


# ------------------------------------ #
#            DOMAIN LAYER              #
# ------------------------------------ #

# Сильные маркеры страницы-челленджа/блокировки.
# ОСТОРОЖНО: маркер `cdn-cgi/challenge-platform` намеренно НЕ используется — он
# остаётся в HTML и после успешного прохождения проверки на страницах за
# Cloudflare (false positive, подтверждено исследованием).
_CHALLENGE_TITLE_MARKERS = (
    "just a moment...",
    "attention required! | cloudflare",
    "please wait...",
    "checking your browser",
)
_CHALLENGE_BODY_MARKERS = (
    "verifying you are human",
    "verify you are human",
    "enable javascript and cookies to continue",
    "cf-turnstile-response",
)


def detect_challenge(html: bytes | str, status: int) -> list[str]:
    """Признаки того, что ответ — страница Cloudflare-челленджа, а не контент.

    Возвращает список причин (пустой список — признаков нет).
    """
    reasons: list[str] = []

    if isinstance(html, bytes):
        text = html.decode("utf-8", "replace")
    else:
        text = html or ""
    text_l = text.lower()

    title_match = _TITLE_RE.search(text)
    title_l = title_match.group(1).strip().lower() if title_match else ""

    for marker in _CHALLENGE_TITLE_MARKERS:
        if marker in title_l:
            reasons.append(f"заголовок страницы содержит маркер челленджа: '{marker}'")

    head = text_l[:20000]
    tail = text_l[-20000:] if len(text_l) > 20000 else ""
    for marker in _CHALLENGE_BODY_MARKERS:
        if marker in head or marker in tail:
            reasons.append(f"HTML содержит маркер челленджа: '{marker}'")

    # Малая страница с CF-заголовком статуса — почти наверняка Interstitial.
    if status in (403, 503) and len(text_l) < 20000:
        reasons.append(f"статус {status} при маленьком теле ответа ({len(text_l)} байт)")

    if "just a moment" in title_l:
        reasons.append("Interstitial Cloudflare ('Just a moment...')")

    return reasons


def cookie_domain(url: str) -> str | None:
    """Выводит домен кук из URL: '.' + хост без 'www' (например '.kinozal.guru')."""
    host = urlparse(url if "://" in url else f"https://{url}").hostname
    if not host:
        return None
    host = host[4:] if host.startswith("www.") else host
    return f".{host}"


# ------------------------------------ #
#          APPLICATION LAYER           #
# ------------------------------------ #


def _scrapling_response_cookies(response) -> tuple[dict, ...]:
    """Бережно достаёт cookies из Scrapling Response (кортеж dict Playwright-формата)."""
    try:
        cookies = getattr(response, "cookies", None) or ()
    except Exception:
        return ()
    if isinstance(cookies, dict):
        return (cookies,)
    if isinstance(cookies, (list, tuple)):
        return tuple(c for c in cookies if isinstance(c, dict))
    return ()


def _response_user_agent(response) -> str | None:
    """Реальный User-Agent, с которым браузер выполнил запрос."""
    try:
        headers = getattr(response, "request_headers", None) or {}
        return headers.get("user-agent") or headers.get("User-Agent")
    except Exception:
        return None


def _to_requests_response(scrapling_response, elapsed: float) -> requests.Response:
    """Собирает настоящий requests.Response из Scrapling Response.

    Вызывающий код (kinozal_scan/parse.py, moviefilter/api.py) работает только с
    интерфейсом requests.Response (.status_code, .ok, .content, .elapsed,
    .raise_for_status), поэтому эскалация обязана вернуть совместимый объект.
    """
    body = getattr(scrapling_response, "body", b"") or b""
    headers = getattr(scrapling_response, "headers", None) or {}

    resp = requests.Response()
    resp.status_code = getattr(scrapling_response, "status", 0) or 0
    resp.url = getattr(scrapling_response, "url", "") or ""
    resp.reason = getattr(scrapling_response, "reason", "") or ""
    resp._content = body if isinstance(body, bytes) else body.encode("utf-8")
    try:
        resp.headers = requests.structures.CaseInsensitiveDict(headers)
    except Exception:
        resp.headers = requests.structures.CaseInsensitiveDict()
    resp.encoding = "utf-8"
    resp.elapsed = timedelta(seconds=elapsed)
    return resp


def _page_title(scrapling_response) -> str:
    try:
        return str(scrapling_response.css("title::text").get() or "").strip()
    except Exception:
        try:
            m = _TITLE_RE.search(_to_requests_response(scrapling_response, 0).content.decode("utf-8", "replace"))
            return m.group(1).strip() if m else ""
        except Exception:
            return ""


class _ScraplingLogBridge(logging.Handler):
    """Перенаправляет INFO-логи Scrapling (turnstile version, попытки солвера)
    в web_logger, чтобы диагностировать эскалацию на сервере по обычным логам."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            log(f"[scrapling] {self.format(record)}", logger_name=LogType.DEBUG)
        except Exception:
            pass


def _bridge_scrapling_logs() -> None:
    scrapling_logger = logging.getLogger("scrapling")
    scrapling_logger.setLevel(logging.INFO)
    if not any(isinstance(h, _ScraplingLogBridge) for h in scrapling_logger.handlers):
        bridge = _ScraplingLogBridge()
        bridge.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
        scrapling_logger.addHandler(bridge)


class CloudflareBypass:
    """
    Одиночка, отвечающий за браузерную эскалацию и кэш cf_clearance.

    Кэш держится в памяти процесса (web и worker — отдельные процессы supervisord,
    у каждого свой экземпляр). Рестарт контейнера просто вызывает одну новую
    эскалацию — это редкое событие, поэтому персистентный кэш не нужен (фаза 2).
    """

    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized"):
            return
        self._initialized = True
        # Сериализует запуск браузера: один Chromium за раз (пик 500–700 МБ RAM,
        # параллельные инстансы в thread-executor'е недопустимы).
        self._lock = threading.Lock()
        # domain -> {"cookies": {name: value}, "useragent": str|None}
        self._cache: dict[str, dict] = {}

    # -- кэш clearance ------------------------------------------------------

    def has_clearance(self, url: str) -> bool:
        domain = cookie_domain(url)
        return bool(domain and self._cache.get(domain))

    def apply_clearance(self, session: requests.Session, url: str) -> bool:
        """Подкладывает закэшированные CF-куки и UA браузера в requests-сессию."""
        domain = cookie_domain(url)
        entry = self._cache.get(domain) if domain else None
        if not entry:
            return False
        cookies = entry.get("cookies") or {}
        for name, value in cookies.items():
            session.cookies.set(name, value, domain=domain, path="/")
        useragent = entry.get("useragent")
        if useragent:
            session.headers["User-Agent"] = useragent
        return bool(cookies)

    def _store(self, domain: str, cookies: dict[str, str], useragent: str | None) -> None:
        if cookies:
            self._cache[domain] = {"cookies": cookies, "useragent": useragent}
            log(
                f"[CF] получен clearance для {domain} "
                f"({', '.join(cookies.keys())})"
            )

    def _invalidate(self, domain: str) -> None:
        if self._cache.pop(domain, None):
            log(f"[CF] clearance для {domain} невалиден — сброшен")

    # -- эскалация ----------------------------------------------------------

    def escape(
        self,
        url: str,
        session: requests.Session,
        auth_cookies: list[dict] | None = None,
    ) -> requests.Response:
        """
        Запускает браузер, решает Cloudflare-челлендж и возвращает HTML.

        Возвращает requests.Response-совместимый объект. При ошибке браузера
        (таймаут, сеть, не запустился) бросает requests.RequestException. Если
        Cloudflare не пропустил даже после решения — CloudflareBlockedError.
        """
        domain = cookie_domain(url) or ""

        with self._lock:
            # Ленивый импорт: не тянем браузерный движок, пока эскалация не нужна.
            try:
                from scrapling.fetchers import StealthyFetcher
            except Exception as exc:
                log(
                    f"[CF] scrapling.fetchers недоступен: {exc}",
                    logger_name=LogType.ERROR,
                )
                raise requests.RequestException(
                    f"Cloudflare escalation unavailable (scrapling not importable): {exc}"
                ) from exc

            _bridge_scrapling_logs()

            # БЕЗ `useragent`: Scrapling сам генерирует консистентный UA+fingerprint.
            fetch_kwargs: dict = {
                "headless": True,
                "timeout": CLOUDFLARE_TIMEOUT_MS,
                "solve_cloudflare": True,
                "retries": 1,
                # В Docker /dev/shm по умолчанию 64 МБ — мало для Chromium.
                "extra_flags": ["--disable-dev-shm-usage"],
            }
            if auth_cookies:
                fetch_kwargs["cookies"] = auth_cookies

            log(f"[CF] эскалация в браузер: {url} (таймаут {CLOUDFLARE_TIMEOUT_MS // 1000} c)")
            t0 = time.monotonic()
            try:
                scrapling_response = StealthyFetcher.fetch(url, **fetch_kwargs)
            except Exception as exc:
                elapsed = time.monotonic() - t0
                log(
                    f"[CF] эскалация провалилась через {elapsed:.1f} c: "
                    f"{type(exc).__name__}: {exc}",
                    logger_name=LogType.ERROR,
                )
                raise requests.RequestException(
                    f"Cloudflare escalation failed: {type(exc).__name__}: {exc}"
                ) from exc

            elapsed = time.monotonic() - t0
            status = getattr(scrapling_response, "status", None)
            log(
                f"[CF] эскалация завершена за {elapsed:.1f} c, статус {status}, "
                f"title {_page_title(scrapling_response)!r}"
            )

            # Извлекаем cookies и реальный UA ДО решения, сохранять ли их.
            cf_cookies: dict[str, str] = {}
            for cookie in _scrapling_response_cookies(scrapling_response):
                name = cookie.get("name")
                value = cookie.get("value")
                if name in _CLOUDFLARE_COOKIE_NAMES and value:
                    cf_cookies[name] = value
            useragent = _response_user_agent(scrapling_response)

            response = _to_requests_response(scrapling_response, elapsed)

            # Честная проверка: эскалация не гарантирует решение любого челленджа.
            still_challenge = detect_challenge(response.content, response.status_code)
            if still_challenge:
                # cf_clearance от неудачной попытки бесполезен — не кэшируем.
                self._invalidate(domain)
                for reason in still_challenge:
                    log(f"[CF] после эскалации челлендж остался: {reason}", logger_name=LogType.ERROR)
                raise CloudflareBlockedError(
                    f"Cloudflare blocked after escalation (status {status})"
                )

            # Перенос clearance + реального UA браузера в кэш и активную сессию.
            self._store(domain, cf_cookies, useragent)
            if self._cache.get(domain):
                self.apply_clearance(session, url)

            return response


# Одиночка уровня модуля (аналог паттерна в KinozalClient).
cloudflare_bypass = CloudflareBypass()
