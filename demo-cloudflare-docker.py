"""
Фаза 0.5: проверка обхода Cloudflare через rtfox-browser. Версия 3.

Что проверяем:
  1. rtfox-browser поднимает браузер (Chrome for Testing / Chromium / Google Chrome).
  2. Cloudflare-челлендж на Kinozal проходится.
  3. Куки из браузера (cf_clearance и пр.) работают в обычном `requests`
     с тем же User-Agent (основа гибридного подхода для боевого кода).

Что появилось в v3:
  - правильное автоопределение браузера и на Windows (для запуска на dev-машине);
  - `--console` — сбор console-лог браузера (видно JS-ошибки челленджа);
  - в цикле ожидания печатается состояние челленджа:
      token_len=N    — turnstile-токен уже получен (виджет отработал);
      success=…      — появился ли блок "Verification successful";
      cf_iframe=YES  — рендерится ли turnstile-iframe;
      error="…"      — текст ошибки CF, если она показана.

Запуск в контейнере (prod):
  docker exec -it -e KINOZAL_SPIKE_COOKIE_UID=... -e KINOZAL_SPIKE_COOKIE_PASS=... \
      <имя контейнера> python /app/demo-cloudflare-docker.py [--console]

Запуск на dev-машине (Windows, свой Chrome):
  uv run python demo-cloudflare-docker.py [--console] [--headed]

Другие CF-зоны из контейнера (контрольный тест):
  docker exec -it -e KINOZAL_SPIKE_URL=https://nopecha.com/demo/cloudflare \
      <имя контейнера> python /app/demo-cloudflare-docker.py [--console]

Переменные окружения:
  KINOZAL_SPIKE_URL           — полный URL для проверки (по умолчанию browse.php на kinozal.guru)
  KINOZAL_SPIKE_COOKIE_UID    — (рекомендуется) кука uid для авторизации на Kinozal
  KINOZAL_SPIKE_COOKIE_PASS   — (рекомендуется) кука pass для авторизации на Kinozal
  KINOZAL_SPIKE_WAIT          — сколько секунд ждать прохождения челленджа (по умолчанию 120)
  KINOZAL_SPIKE_CHECK_DETAILS — если "1", проверяем details-страницу через requests (по умолчанию "1")
  KINOZAL_SPIKE_CHECK_DL      — если "1", проверяем, стоит ли dl-поддомен за Cloudflare (по умолчанию "1")
  KINOZAL_SPIKE_DETACHED      — если "1", запуск chrome detached-процессом (use_subprocess=False)
  KINOZAL_SPIKE_BROWSER       — бинарь браузера (иначе автоопределение)

Коды выхода:
  0 — все проверки прошли
  1 — браузерная часть не удалась (челлендж не пройден / не запустился Chromium)
  2 — браузер прошёл, но повтор кук в requests не сработал
"""

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time

DEFAULT_URL = "https://kinozal.guru/browse.php?s=&g=0&c=1002&v=7&d=0&w=0&t=0&f=0"


def env_bool(name, default=False):
    return os.environ.get(name, str(int(default))).strip().lower() in ("1", "true", "yes", "on")


def looks_like_challenge(title: str, url: str, html: str) -> bool:
    tl = title.lower()
    ul = url.lower()
    if any(word in tl for word in ("moment", "один момент", "attention")):
        return True
    if "challenge" in ul:
        return True
    if any(marker in html for marker in ("challenge-platform", "cf-chl-", "cdn-cgi/challenge")):
        return True
    return False


def pick_browser():
    env = os.environ.get("KINOZAL_SPIKE_BROWSER")
    if env:
        if os.path.exists(env):
            return env
        print(f"[WARN] KINOZAL_SPIKE_BROWSER={env} не найден, пробую автоопределение")

    candidates = []

    if os.name == "nt":
        for base_var in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
            base = os.environ.get(base_var)
            if base:
                candidates.append(os.path.join(base, "Google", "Chrome", "Application", "chrome.exe"))

    candidates += [
        "/opt/chrome/chrome",
        "/opt/chrome-linux64/chrome",
        shutil.which("chromium"),
        shutil.which("google-chrome"),
        shutil.which("chromium-browser"),
    ]

    for c in candidates:
        if c and os.path.exists(c):
            return c
    return None


CHALLENGE_STATE_JS = """
(function () {
    var parts = [];
    var inp = document.querySelector('input[name="cf-turnstile-response"]');
    if (inp) parts.push('token_len=' + inp.value.length);
    var ok = document.getElementById('tSBMk0');
    if (ok) parts.push('success=' + (ok.style.display !== 'none' ? 'VISIBLE' : 'hidden'));
    var err = document.getElementById('challenge-error-text');
    if (err && !err.closest('noscript') && err.textContent.trim()) {
        parts.push('error="' + err.textContent.trim().slice(0, 80) + '"');
    }
    var f = document.querySelector('iframe[src*="challenges.cloudflare.com"]');
    parts.push('cf_iframe=' + (f ? 'YES' : 'no'));
    return parts.join(' ');
})()
"""


def main():
    parser = argparse.ArgumentParser(description="Cloudflare spike v3 for Kinozal scraper")
    parser.add_argument("--headed", action="store_true", help="запуск с GUI (в контейнере требует xvfb-run)")
    parser.add_argument("--profile", default=None, help="путь к постоянному chrome-профилю")
    parser.add_argument("--console", action="store_true", help="собирать console-лог браузера")
    args = parser.parse_args()

    url = os.environ.get("KINOZAL_SPIKE_URL", DEFAULT_URL)
    wait_seconds = float(os.environ.get("KINOZAL_SPIKE_WAIT", "120"))
    cookie_uid = os.environ.get("KINOZAL_SPIKE_COOKIE_UID")
    cookie_pass = os.environ.get("KINOZAL_SPIKE_COOKIE_PASS")
    check_details = env_bool("KINOZAL_SPIKE_CHECK_DETAILS", True)
    check_dl = env_bool("KINOZAL_SPIKE_CHECK_DL", True)
    detached = env_bool("KINOZAL_SPIKE_DETACHED", False)
    headless = not args.headed

    host = url.split("/")[2]

    print("=" * 74)
    print("ФАЗА 0.5: Cloudflare-обход, расширенная диагностика v3")
    print("=" * 74)
    root = os.geteuid() == 0 if hasattr(os, "geteuid") else None
    print(f"python: {sys.version.split()[0]} | platform: {platform.platform()}")
    print(f"root: {root} | URL: {url} | headless: {headless} | console-лог: {args.console}")
    print(f"ожидание челленджа: {wait_seconds}s | куки uid/pass заданы: {bool(cookie_uid and cookie_pass)}")
    print(f"профиль: {args.profile or 'временный'} | detached: {detached}")
    print()

    try:
        import requests
        ip = requests.get("https://api.ipify.org", timeout=15).text.strip()
        print(f"egress IP: {ip}")
    except Exception as e:
        print(f"[WARN] egress IP не определён: {e}")
    print()

    browser = pick_browser()
    if not browser:
        print("[FAIL] браузер не найден. Установи chromium или Chrome for Testing.")
        return 1

    print(f"browser binary: {browser}")
    try:
        out = subprocess.check_output([browser, "--version"], stderr=subprocess.STDOUT, timeout=20).decode().strip()
        print(f"browser version: {out}")
    except Exception as e:
        print(f"[WARN] версия не определена: {e}")
    print()

    try:
        import rtfox_browser as uc
    except ImportError as e:
        print(f"[FAIL] rtfox_browser не установлен: {e}")
        return 1

    driver = None

    try:
        # ---------------------------------------------------------------
        # ЧАСТЬ 1. Браузер: запуск и прохождение челленджа
        # ---------------------------------------------------------------
        print("[1/3] Запуск браузера...")
        t0 = time.time()

        options = uc.ChromeOptions()
        options.add_argument("--disable-dev-shm-usage")

        driver = uc.Chrome(
            options=options,
            headless=headless,
            browser_executable_path=browser,
            user_data_dir=args.profile,
            use_subprocess=not detached,
            enable_cdp_events=args.console,
        )
        print(f"  браузер запущен за {time.time() - t0:.1f}s")

        try:
            wd_before = driver.execute_script("return navigator.webdriver")
            print(f"  navigator.webdriver (до get): {wd_before}")
        except Exception:
            print("  navigator.webdriver (до get): неизвестно")

        seen_console = set()

        def report_console():
            if not args.console:
                return
            try:
                entries = driver.get_log("browser")
            except Exception:
                return
            for e in entries:
                key = (e.get("level") or "") + (e.get("message") or "")[:200]
                if key in seen_console:
                    continue
                seen_console.add(key)
                if e.get("level") in ("SEVERE", "WARNING", "ERROR"):
                    print(f"    [console:{e.get('level')}] {e.get('message')}")

        def get_challenge_frames(drv):
            try:
                return drv.execute_script(
                    "return Array.from(document.querySelectorAll('iframe')).map(f => ({src: f.src || '', title: f.title || ''}));"
                ) or []
            except Exception:
                return []

        def get_challenge_state(drv):
            try:
                return (drv.execute_script(CHALLENGE_STATE_JS) or "").strip()
            except Exception:
                return ""

        def try_click_turnstile(drv):
            from selenium.webdriver.common.action_chains import ActionChains
            from selenium.webdriver.common.by import By

            frames = drv.find_elements(By.TAG_NAME, "iframe")
            for f in frames:
                title = (f.get_attribute("title") or "").lower()
                src = (f.get_attribute("src") or "").lower()
                if "cloudflare" in title or "turnstile" in src or "challenge" in src:
                    ActionChains(drv).move_to_element_with_offset(f, 5, 5).click().perform()
                    return True
            boxes = drv.find_elements(By.CSS_SELECTOR, "input[type=checkbox], .ctp-checkbox-label")
            if boxes:
                ActionChains(drv).move_to_element(boxes[0]).click().perform()
                return True
            return False

        print(f"[2/3] Навигация на {url}, ожидание прохождения челленджа...")
        t0 = time.time()

        driver.get(url)

        if cookie_uid and cookie_pass:
            for name, value in (("uid", cookie_uid), ("pass", cookie_pass)):
                driver.add_cookie({"name": name, "value": value, "domain": host, "path": "/"})
            print("  куки uid/pass добавлены в браузер")

        try:
            wd_after = driver.execute_script("return navigator.webdriver")
            print(f"  navigator.webdriver (после get): {wd_after}")
        except Exception:
            print("  navigator.webdriver (после get): неизвестно")

        start = time.time()
        last_snap_t = 0.0
        last_snap_hash = None
        snap_seq = 0
        clicks = 0
        last_click = 0.0
        last_state = None
        schedule_reload = bool(cookie_uid and cookie_pass)

        while time.time() - start < wait_seconds:
            title = driver.title or ""
            current = driver.current_url or ""
            html = driver.page_source or ""
            frames = get_challenge_frames(driver)
            interactive = any(
                "challenges.cloudflare.com" in f["src"] or "turnstile" in f["src"]
                for f in frames
            )
            challenged = looks_like_challenge(title, current, html)

            state = get_challenge_state(driver)
            if state and state != last_state:
                print(f"    [state {int(time.time() - start)}s] {state}")
                last_state = state

            report_console()

            if html and not challenged and not schedule_reload:
                print(f"  челлендж пройден за {time.time() - t0:.1f}s")
                break

            now = time.time()

            if schedule_reload and html and not challenged:
                # челлендж прошёл на первой загрузке, но куки uid/pass надо применить повторной загрузкой
                print("  челлендж пройден, перезагружаю с авторизационными куками...")
                driver.get(url)
                schedule_reload = False
                continue

            if challenged and interactive and clicks < 5 and (last_click == 0.0 or now - last_click > 8):
                clicks += 1
                print(f"  обнаружен turnstile-iframe, автоклик #{clicks}...")
                try:
                    if try_click_turnstile(driver):
                        last_click = now
                except Exception as e:
                    print(f"    [WARN] автоклик: {e}")

            if now - last_snap_t >= 10:
                last_snap_t = now
                h = hashlib.md5(html.encode("utf-8", errors="ignore")).hexdigest()
                if h != last_snap_hash:
                    last_snap_hash = h
                    with open(f"snap_{snap_seq:02d}.html", "w", encoding="utf-8") as f:
                        f.write(html)
                    print(f"    [snapshot {snap_seq:02d}] url={current!r} title={title!r} len={len(html)} interactive={interactive}")
                    snap_seq += 1

            time.sleep(1)
        else:
            report_console()
            with open("challenge-page.html", "w", encoding="utf-8") as f:
                f.write(driver.page_source)
            print(f"[FAIL] челлендж не пройден за {wait_seconds}s")
            print(f"  url={driver.current_url!r} title={driver.title!r}")
            print(f"  автокликов: {clicks} | финальное состояние: {get_challenge_state(driver)!r}")
            print("  snapshots: snap_NN.html, финальный дамп: challenge-page.html")
            return 1

        html_browser = driver.page_source
        print(f"  title: {driver.title!r} | url: {driver.current_url!r} | длина html: {len(html_browser)}")
        if "browse.php" in html_browser or 'class="bg"' in html_browser:
            print("  содержимое каталога присутствует")
        else:
            print("  [WARN] не видно строк каталога — проверь challenge-page.html / page.html")

        with open("page.html", "w", encoding="utf-8") as f:
            f.write(html_browser)

        selenium_cookies = driver.get_cookies()
        with open("cookies.json", "w", encoding="utf-8") as f:
            json.dump(selenium_cookies, f, ensure_ascii=False, indent=2)

        print(f"  cookie names: {sorted({c['name'] for c in selenium_cookies})}")

        ua = driver.execute_script("return navigator.userAgent")
        print(f"  UA браузера: {ua}")

        # ---------------------------------------------------------------
        # ЧАСТЬ 2. Повтор кук в обычном requests (основа гибрида)
        # ---------------------------------------------------------------
        print()
        print("[3/3] Проверка: куки браузера + requests...")
        import requests as rq

        s = rq.Session()
        for c in selenium_cookies:
            if c.get("name") and c.get("domain"):
                s.cookies.set(c["name"], c["value"], domain=c["domain"], path=c.get("path", "/"))
        s.headers.update({
            "User-Agent": ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        })

        r = s.get(url, timeout=60)
        rhtml = r.content.decode("utf-8", errors="ignore")
        print(f"  browse: status={r.status_code} длина={len(r.content)}")
        if r.status_code != 200:
            print("[FAIL] requests вернул не 200")
            return 2
        if looks_like_challenge("", r.url or "", rhtml):
            print("[FAIL] requests снова получил challenge-страницу")
            return 2
        if "browse.php" not in rhtml and 'class="bg"' not in rhtml:
            print("[FAIL] в ответе requests нет содержимого каталога")
            return 2
        print("  OK: каталог через requests получен")

        if check_details:
            m = re.search(r"details\.php\?id=(\d+)", rhtml)
            if m:
                details_url = f"https://{host}/details.php?id={m.group(1)}"
                rd = s.get(details_url, timeout=60)
                dhtml = rd.content.decode("utf-8", errors="ignore")
                print(f"  details: status={rd.status_code} длина={len(rd.content)}")
                if rd.status_code != 200 or looks_like_challenge("", rd.url or "", dhtml):
                    print("[FAIL] details-страница через requests не прошла")
                    return 2
                if "download.php?id=" not in dhtml:
                    print("[FAIL] в details нет ссылки на скачивание")
                    return 2
                print("  OK: details-страница через requests получена")
            else:
                print("  [WARN] ссылка на details не найдена в каталоге — проверку details пропускаем")

        if check_dl:
            dl_url = f"https://dl.{host}/"
            try:
                rdl = s.get(dl_url, timeout=60)
                dlhtml = rdl.content.decode("utf-8", errors="ignore")
                print(f"  dl-поддомен: status={rdl.status_code} длина={len(rdl.content)}")
                if looks_like_challenge("", rdl.url or "", dlhtml):
                    print("  [WARN] dl.* тоже отдаёт challenge — кука cf_clearance с основного домена не покрывает поддомен")
                else:
                    print("  OK: dl-поддомен не отдал challenge")
            except rq.RequestException as e:
                print(f"  [WARN] dl-поддомен недоступен: {e}")

        print()
        print("РЕЗУЛЬТАТ: PASS")
        return 0

    except Exception as e:
        import traceback
        print(f"[FAIL] непредвиденная ошибка: {e!r}")
        traceback.print_exc()
        return 1

    finally:
        if driver is not None:
            try:
                print("Закрываю браузер...")
                driver.quit()
            except Exception:
                pass


if __name__ == "__main__":
    sys.exit(main())