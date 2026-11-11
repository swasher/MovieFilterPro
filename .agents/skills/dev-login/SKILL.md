---
name: dev-login
description: Логин агента в локальное dev-приложение MovieFilterPro через in-app браузер под несекретным dev-аккаунтом из .env.agent — открыть страницу входа, авторизоваться, проверить сессию, убрать за собой временные серверы. Использовать, когда просят «залогиниться», показать страницу под авторизацией или продиагностировать UI за логином.
user-invocable: true
---

# Dev-login (MovieFilterPro)

Рецепт входа в локальное приложение под dev-аккаунтом агента. Порты, запуск серверов
и правила уборки — в корневом `AGENTS.md` (раздел «Dev Servers and Ports»); здесь только
то, чего там нет: контракт логина и последовательность действий в браузере.

## Креды

- Файл: `.env.agent` в корне репозитория, ключи `AGENT_USERNAME` и `AGENT_PASSWORD`.
- По `AGENTS.md` эти креды **не секретные**: их можно читать, подставлять в запросы и
  выводить при отладке. Нельзя коммитить файл и копировать значения в `.env`/`.env.production`.
- Секретных обходов (временных серверов ради сокрытия пароля) не нужно — читай файл напрямую.
- После `copydb_qnap_to_dev.sh` пароль уже восстановлен из `.env.agent`. Если базу заливали
  другим способом, вернуть пароль: `uv run python manage.py set_user_password <user> <pass>`.

## Серверы агента

Свои порты, не занимать пользовательские `8000`/`5173`:

```powershell
uv run daphne -b 127.0.0.1 -p 8001 movie_filter_pro.asgi:application
```

```powershell
$env:VITE_BACKEND_URL='http://127.0.0.1:8001'; npm run dev -- --port 5174 --strictPort
```

`--strictPort` обязателен. Если нужен только API-вход без UI — браузер не поднимать,
хватит `curl`/Django test client.

### Ожидание готовности портов

Две ловушки, обе стоили времени на практике:

1. **Не ждать HTTP-ответ на `/`.** Django на `/` отдаёт `404` (SPA обслуживает Vite), а в
   PowerShell 5.1 `Invoke-WebRequest` на не-2xx бросает исключение: цикл «жду 200» никогда не
   завершится успехом и выжжет весь таймаут, хотя сервер жив с первой секунды.
2. **Не проверять `127.0.0.1:<frontend>`.** Vite 7 с хостом `localhost` занимает только `::1`
   (см. `Get-NetTCPConnection -LocalPort 5174 -State Listen` → `LocalAddress ::1`), а daphne
   с `-b 127.0.0.1` — только IPv4. Поэтому коннект к `127.0.0.1:5174` получает `refused`,
   хотя сервер работает. Куки и проверки — по имени `localhost`, оно покрывает оба семейства.

Проверенный вариант (одним вызовом после старта обоих серверов) — смотреть состояние
прослушивания на уровне ОС, это мгновенно и не зависит от адреса/семейства:

```powershell
function Wait-Port([int]$p, [int]$timeoutSec = 30) {
  $sw = [Diagnostics.Stopwatch]::StartNew()
  while ($sw.Elapsed.TotalSeconds -lt $timeoutSec) {
    if (Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue) { return "port $p up" }
    Start-Sleep -Milliseconds 250
  }
  throw "port $p not up in $timeoutSec s"
}
Wait-Port 8001
Wait-Port 5174
```

Замеры на этой машине (серверы уже подняты): `Wait-Port` для `8001` — ~0.5 с, для `5174` — ~0.2 с,
закрытый порт честно падает по таймауту; `tabs.open` + проверка сессии — ~0.3 с. То есть
«поднять серверы и войти» — единицы секунд. Сам старт: daphne ~1 с, Vite ~2.5 с; если порт не
поднялся за 10–15 с — это ошибка запуска, смотри `.out`-файл фонового процесса, а не жди дольше.
Вариант через `TcpClient` тоже рабочий, но только с `localhost`: `Connect('127.0.0.1', 5174)`
к Vite даст `refused` и повесит проверку на секунды.

## Контракт логина

- `POST /api/auth/login/`, `multipart/form-data` или `application/x-www-form-urlencoded`
  с полями `username`, `password`.
- Endpoint `csrf_exempt`; сессия — обычная Django-кука (HttpOnly), поэтому JS-ом её не поставить,
  а вот `login` через страницу/`curl` работает.
- Успех: HTTP 200 и JSON `{ "is_authenticated": true, "user": {...}, "site_version": "..." }`.
- Ошибка: HTTP 400 и `{ "message": "Неверный логин или пароль.", "is_authenticated": false }`.
- Текущая сессия: `GET /api/auth/session/`.
- UI: страница `/login` (Svelte), после успеха `invalidateAll()` и редирект на `/`.

## Карта маршрутов (front, `front/src/routes`)

- `/` — Vault (группа `(vault)`). **Маршрута `/vault` нет** — не ходить туда, будет 404.
- `/login` — форма входа.
- При отсутствии сессии корень `/` сам показывает форму «Вход» (отдельный переход на `/login`
  не обязателен).
- Дальше: `/connections`, `/persons`, `/persons/[id]`, `/movies/[slug]`, `/kinozal`, `/scan`,
  `/scan-history`, `/plex`, `/qbittorrent`, `/preferences`, `/tmdb-auth`, `/tmdb-sync`,
  `/tmdb-writeback`, `/match-log`.

## Последовательность в браузере

Цель — 2–3 вызова code mode, а не 10. Сначала проверить, жива ли сессия, затем один блок на вход.
Замер на этой машине (11.11.2026, порты 8000/5173/5174 закрыты): полный цикл «старт серверов →
вход → уборка» ≈ 1 мин 45 с, из них старт daphne+Vite и `Wait-Port` ≈ 15 с, браузерная часть
≈ 45 с. Почти весь расход — не серверы, а восстановление после сбоя `click` (см. «Грабли»).

1. Прочитать `AGENT_USERNAME`/`AGENT_PASSWORD` из `.env.agent`.
2. Открыть `http://localhost:5174/` (куки общие для `localhost`, поэтому сессия может быть жива
   с прошлого раза). Сразу после `tabs.open` snapshot может быть пустым — Svelte гидрируется:
   ждать текст, а не делать snapshot по кругу.
3. Узнать, жива ли сессия, через `fetch('/api/auth/session/')` в `evaluate` — это ~60 мс.
   Угадывать по тексту через `wait`/`catch` нельзя: таймаут `wait` по умолчанию ~10 с, и «а вдруг
   уже залогинен» стоит ровно эти 10 секунд.
4. Если `is_authenticated: true` — логин не нужен.
5. Иначе дождаться формы «Вход», заполнить по ref-ам из свежего snapshot и отправить **Enter**
   (поле пароля после `fill` уже в фокусе — проверено). `click` по кнопке тоже работает, но иногда
   падает с `UnknownVizError` — см. «Грабли».
6. Успех — имя пользователя в шапке. Больше ничего проверять не нужно (см. «Проверка»).
7. Скриншот — только после `tabs.focus`, иначе инструмент вернёт ошибку.

### Готовый блок входа

```js
const tab = await tools.browser.tabs.open({ url: "http://localhost:5174/" });
const tabID = tab.id;

// 60 мс вместо ~10 с таймаута wait
const session = await tools.browser.evaluate({
  tabID, script: "fetch('/api/auth/session/').then(r => r.json()).then(j => j.is_authenticated)"
});

if (!session.value) {
  await tools.browser.wait({ tabID, condition: "text", text: "Войти" });
  const form = await tools.browser.snapshot({ tabID }); // refs полей и кнопки
  const ref = (label) => form.content.match(new RegExp(`(@e\\d+) \\[textbox\\] "${label}"`))?.[1];
  await tools.browser.fill({ tabID, ref: ref("Username"), text: "AGENT_USERNAME" });
  await tools.browser.fill({ tabID, ref: ref("Password"), text: "AGENT_PASSWORD" });
  // Enter по полю пароля (после fill оно в фокусе) — обходит флаки click/UnknownVizError
  await tools.browser.press({ tabID, key: "Enter" });
  await tools.browser.wait({ tabID, condition: "text", text: "AGENT_USERNAME", timeoutMs: 15000 }); // имя в шапке = успех
}
```

Подставить реальные значения из `.env.agent` вместо `AGENT_USERNAME`/`AGENT_PASSWORD`.
Если регулярки по snapshot кажутся хрупкими — взять ref-ы глазами из `snapshot` и передать явно;
это дешевле, чем отлаживать парсинг.

### Проверка после входа

Минимум: имя пользователя в шапке + `console` без ошибок. **Не** делать ради проверки отдельные
`/api/auth/session/`, походы по чужим страницам и скриншоты: `POST` вернул 200 и шапка обновилась —
этого достаточно. Дополнительное — только если оно и есть предмет задачи (например, диагностика
конкретной страницы).
Оговорка: `GET /api/auth/session/` **до** входа — это дешёвое ветвление (см. блок выше);
**после** входа тот же запрос уже ничего не проверяет, потому что результат известен из `POST`.
И ещё: сразу после отправки формы `session` может ещё отдавать `is_authenticated: false` (запрос
успевает раньше ответа `POST`) — проверять по шапке, а не опросом API.

## Грабли

- В `browser.fill` поле называется **`text`** (не `value`): `{ tabID, ref, text }`.
- В `browser.evaluate` параметр называется `script` (не `expression`); в code mode нет таймеров —
  никаких `await new Promise(r => setTimeout(...))`.
- Таймаут `browser.wait` по умолчанию ~10 с, задаётся полем **`timeoutMs`** (не `timeout`).
  Любая «проверка на всякий случай» через `wait` +
  `catch` стоит этих 10 секунд — состояние лучше спрашивать у API (`evaluate`), а `wait` держать
  только для гарантированно наступающего события.
- После отправки формы (Enter или клик) кнопка становится «Входим...»: ждать появления
  **имени пользователя**, а не исчезновения текста «Войти».
- Не переиспользовать ref-ы после навигации/нового snapshot.
- `click` по кнопке формы иногда падает с `[browser.operation_failed] UnknownVizError` (в замерах —
  2 раза из 5). Причина не установлена (не фокус вкладки и не обязательное протухание ref), поэтому
  не отлаживать: взять свежий `snapshot` и повторить клик, а лучше вообще не кликать — отправить
  форму через `Enter`.
- `press` требует **фокуса в поле**: после `fill` фокус стоит в заполненном input (проверено), и
  `Enter` сабмитит форму. А вот `press` без фокуса в поле не даёт ни ошибки, ни сабмита — форма
  молча остаётся с заполненными значениями. Поэтому не полагаться на «Enter куда-нибудь».
- `tabs.focus` для `click`/`press` не обязателен: клик по кнопке в нефокусированной вкладке
  отрабатывает (проверено), но `screenshot` без фокуса падает.
- Куки общие для `localhost` на всех портах: вход на `5174` действует и на `8000`/`8001`.
- Корень `/` под авторизацией может отрисовать пустой `<main>` на момент первого snapshot
  (данные Vault ещё грузятся) — это не ошибка входа; повторный snapshot после появления шапки.
- Не логиниться в прод и не использовать dev-креды против боевого инстанса.

## Уборка

Остановить только свои процессы (daphne `8001`, vite `5174`, любые временные), проверить,
что порты освободились; вкладку браузера закрывать не обязательно — она пригодится при
следующем заходе (сессия в куках сохраняется).

```powershell
foreach ($p in 8001, 5174) {
  Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique |
    ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }
}
```

Процессы пользователя (`8000`/`5173`, PostgreSQL, HUEY) не трогать.
