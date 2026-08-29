"""
Очистка аккаунта TMDB: списки (V4), оценки, watchlist, favorites (V3).

Улучшенная версия:
- Токен берется из Django: moviefilter.models.UserPreferences (singleton pk=1)
  приоритет: tmdb_v4_authenticated_access_token (write token) -> fallback tmdb_v4_read_access_token
- ACCOUNT_ID резолвится автоматически через API, хардкодить не нужно.
- Подтверждение и --dry-run / --yes / фильтры по типам.

Запуск:
    uv run python clear_tmdb_account.py
    uv run python clear_tmdb_account.py --dry-run
    uv run python clear_tmdb_account.py --yes --only lists,ratings
    uv run python clear_tmdb_account.py --v4-token eyJ...   # переопределить токен

Что такое ACCOUNT_ID:
    TMDB после approve выдает write access token + account_id.
    - V4 (object ID, строка вида "5f6d..."): используется для /4/account/{id}/lists
      получить можно GET https://api.themoviedb.org/4/account с Bearer write-token -> {"id": "<v4_id>"}
      В tmdbapis это API4.account_id (ставится автоматически при validate).
    - V3 (numeric ID, int): используется для /3/account/{id}/rated, /watchlist, /favorite
      получить можно GET https://api.themoviedb.org/3/account с Bearer -> {"id": 12345}
      В tmdbapis это API3.account_id.
    Скрипт резолвит оба автоматически. Для новых токенов они эквивалентны через Bearer auth,
    но эндпоинты требуют разный формат — поэтому резолвим отдельно.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import django

# --- Django bootstrap ---
# Позволяет запускать как `uv run python clear_tmdb_account.py` из корня проекта
BASE_DIR = Path(__file__).resolve().parent
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "movie_filter_pro.settings")
# django.setup() требует, чтобы settings были импортируемы (BASE_DIR в sys.path уже есть при запуске из корня)
try:
    django.setup()
except Exception as exc:
    print(f"[FATAL] django.setup() failed: {exc}")
    print("  Убедись что запускаешь из корня проекта и .env настроен.")
    sys.exit(1)

import requests
from moviefilter.models import UserPreferences  # noqa: E402

BASE_URL_V4 = "https://api.themoviedb.org/4"
BASE_URL_V3 = "https://api.themoviedb.org/3"


def get_token(cli_token: str | None = None) -> tuple[str, str]:
    """Возвращает (token, source). Приоритет: CLI > DB write_token > DB read_token."""
    if cli_token:
        return cli_token.strip(), "cli --v4-token"

    prefs = UserPreferences.get()
    write_token = (prefs.tmdb_v4_authenticated_access_token or "").strip()
    if write_token:
        return write_token, "DB: UserPreferences.tmdb_v4_authenticated_access_token (write)"

    read_token = (prefs.tmdb_v4_read_access_token or "").strip()
    if read_token:
        print("[WARN] Write token пуст, использую tmdb_v4_read_access_token (read-only).")
        print("       Удаление списков/оценок/watchlist требует WRITE токена (после Approve).")
        print("       Получи его: /tmdb-auth/ -> Start -> Approve -> Finish")
        return read_token, "DB: UserPreferences.tmdb_v4_read_access_token (read, fallback)"

    print("[FATAL] Нет токена ни в CLI ни в БД.")
    print("  Заполни в админке / настройках: tmdb_v4_read_access_token + пройди approve для write token,")
    print("  или передай --v4-token eyJ...")
    sys.exit(1)


def resolve_account_ids(token: str) -> tuple[str | None, int | None]:
    """
    Резолвит V4 и V3 account_id через API.
    Возвращает (v4_id: str|None, v3_id: int|None).
    Если не удалось — None, и будет fallback на raw token auth без ID (некоторые эндпоинты принимают /account/{id} с любым id при Bearer).
    """
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json;charset=utf-8"}
    v4_id = None
    v3_id = None

    # V4: GET /4/account -> {"id": "5f..."}  (object id)
    try:
        r = requests.get(f"{BASE_URL_V4}/account", headers=headers, timeout=15)
        if r.status_code == 200:
            data = r.json()
            # TMDB v4 возвращает {"id": "abc...", "accountId": 123} или наоборот
            v4_id = data.get("id") or data.get("accountId") or data.get("account_id")
            # иногда id это уже hex, accountId numeric
            if v4_id is not None:
                v4_id = str(v4_id)
                print(f"[INFO] V4 account_id resolved: {v4_id}  (GET /4/account)")
            # также пробуем вытащить numeric для V3
            if isinstance(data.get("accountId"), int):
                v3_id = int(data["accountId"])
        else:
            print(f"[WARN] GET /4/account -> {r.status_code}: {r.text[:300]}")
    except Exception as exc:
        print(f"[WARN] GET /4/account failed: {exc}")

    # V3: GET /3/account -> {"id": 12345}
    try:
        r = requests.get(f"{BASE_URL_V3}/account", headers=headers, timeout=15)
        if r.status_code == 200:
            data = r.json()
            if isinstance(data.get("id"), int):
                v3_id = int(data["id"])
                print(f"[INFO] V3 account_id resolved: {v3_id}  (GET /3/account)")
        else:
            # V3 с Bearer v4 token может отдать 401 если токен read-only — это нормально
            print(f"[WARN] GET /3/account -> {r.status_code}: {r.text[:300]}")
    except Exception as exc:
        print(f"[WARN] GET /3/account failed: {exc}")

    # Fallback через tmdbapis если requests не дал результата
    if not v4_id or not v3_id:
        try:
            from tmdb_adapter.client_singleton import get_tmdb_client

            tmdb = get_tmdb_client()
            if not v4_id and getattr(tmdb, "_api4", None) is not None:
                try:
                    v4_id = str(tmdb._api4.account_id)
                    print(f"[INFO] V4 account_id via tmdbapis: {v4_id}")
                except Exception:
                    pass
            if not v3_id and getattr(tmdb, "_api3", None) is not None:
                try:
                    v3_id = int(tmdb._api3.account_id)
                    print(f"[INFO] V3 account_id via tmdbapis: {v3_id}")
                except Exception:
                    pass
        except Exception:
            pass

    if not v4_id:
        print("[WARN] V4 account_id не резолвнулся — /4/account/{id}/lists может не работать.")
    if not v3_id:
        print("[WARN] V3 account_id не резолвнулся — /3/account/{id}/... может не работать.")

    return v4_id, v3_id


def _handle_rate_limit(resp: requests.Response) -> None:
    if resp.status_code == 429:
        retry = resp.headers.get("Retry-After")
        delay = int(retry) if retry and retry.isdigit() else 2
        print(f"[RATE LIMIT 429] sleep {delay}s ...")
        time.sleep(delay)


def delete_user_lists(headers: dict, v4_id: str | None, dry_run: bool = False) -> int:
    """Удаление всех пользовательских списков (API v4). Возвращает кол-во удаленных."""
    print("\n--- Очистка пользовательских списков (V4) ---")
    if not v4_id:
        print("[SKIP] Нет V4 account_id — пропускаю списки.")
        return 0

    deleted = 0
    page = 1
    while True:
        url = f"{BASE_URL_V4}/account/{v4_id}/lists?page={page}"
        try:
            res = requests.get(url, headers=headers, timeout=15).json()
        except Exception as exc:
            print(f"[ERROR] GET lists page {page}: {exc}")
            break

        results = res.get("results", [])
        if not results:
            if page == 1:
                print("  (списков нет)")
            break

        for item in results:
            list_id = item["id"]
            name = item.get("name", "?")
            if dry_run:
                print(f"[DRY-RUN] Будет удален список ID: {list_id} ({name})")
                deleted += 1
                continue

            del_url = f"{BASE_URL_V4}/list/{list_id}"
            try:
                del_res = requests.delete(del_url, headers=headers, timeout=15)
            except Exception as exc:
                print(f"[ERROR] DELETE list {list_id} exception: {exc}")
                continue

            if del_res.status_code == 429:
                _handle_rate_limit(del_res)
                # retry once
                del_res = requests.delete(del_url, headers=headers, timeout=15)

            if del_res.status_code in (200, 201, 204):
                print(f"[OK] Удален список ID: {list_id} ({name})")
                deleted += 1
            else:
                print(f"[ERROR] Не удалось удалить список ID: {list_id} ({name}) -> {del_res.status_code} {del_res.text[:200]}")
            time.sleep(0.25)  # мягкий throttling для TMDB

        if page >= res.get("total_pages", 1):
            break
        page += 1

    print(f"  Итого списков удалено (или dry-run): {deleted}")
    return deleted


def clear_ratings(headers: dict, v3_id: int | str | None, media_type: str = "movie", dry_run: bool = False) -> int:
    """Удаление всех оценок для фильмов или сериалов. Возвращает кол-во."""
    print(f"\n--- Очистка оценок ({media_type}) ---")
    if not v3_id:
        print("[SKIP] Нет V3 account_id — пропускаю ratings.")
        return 0

    deleted = 0
    while True:
        url = f"{BASE_URL_V3}/account/{v3_id}/rated/{media_type}s?page=1"
        try:
            res = requests.get(url, headers=headers, timeout=15).json()
        except Exception as exc:
            print(f"[ERROR] GET rated {media_type}: {exc}")
            break

        results = res.get("results", [])
        if not results:
            if deleted == 0:
                print("  (оценок нет)")
            break

        for item in results:
            media_id = item["id"]
            if dry_run:
                print(f"[DRY-RUN] Будет удалена оценка {media_type} ID: {media_id}")
                deleted += 1
                continue

            del_url = f"{BASE_URL_V3}/{media_type}/{media_id}/rating"
            try:
                del_res = requests.delete(del_url, headers=headers, timeout=15)
            except Exception as exc:
                print(f"[ERROR] DELETE rating {media_type} {media_id}: {exc}")
                continue

            if del_res.status_code == 429:
                _handle_rate_limit(del_res)
                del_res = requests.delete(del_url, headers=headers, timeout=15)

            if del_res.status_code in (200, 201, 204):
                print(f"[OK] Удалена оценка {media_type} ID: {media_id}")
                deleted += 1
            else:
                print(f"[ERROR] Не удалось удалить оценку {media_type} ID: {media_id} -> {del_res.status_code} {del_res.text[:200]}")
            time.sleep(0.25)

        # после удаления структура смещается — снова page=1, цикл сам завершится когда results пустой

    print(f"  Итого оценок удалено (или dry-run): {deleted}")
    return deleted


def clear_account_states(headers: dict, v3_id: int | str | None, list_type: str = "watchlist", media_type: str = "movie", dry_run: bool = False) -> int:
    """Удаление элементов из Watchlist или Favorites."""
    print(f"\n--- Очистка {list_type} ({media_type}) ---")
    if not v3_id:
        print(f"[SKIP] Нет V3 account_id — пропускаю {list_type}.")
        return 0

    deleted = 0
    while True:
        url = f"{BASE_URL_V3}/account/{v3_id}/{list_type}/{media_type}s?page=1"
        try:
            res = requests.get(url, headers=headers, timeout=15).json()
        except Exception as exc:
            print(f"[ERROR] GET {list_type} {media_type}: {exc}")
            break

        results = res.get("results", [])
        if not results:
            if deleted == 0:
                print(f"  ({list_type} {media_type}: пусто)")
            break

        for item in results:
            media_id = item["id"]
            if dry_run:
                print(f"[DRY-RUN] Будет удален {media_type} ID: {media_id} из {list_type}")
                deleted += 1
                continue

            post_url = f"{BASE_URL_V3}/account/{v3_id}/{list_type}"
            payload = {
                "media_type": media_type,
                "media_id": media_id,
                list_type: False,
            }
            try:
                post_res = requests.post(post_url, headers=headers, json=payload, timeout=15)
            except Exception as exc:
                print(f"[ERROR] POST {list_type} remove {media_type} {media_id}: {exc}")
                continue

            if post_res.status_code == 429:
                _handle_rate_limit(post_res)
                post_res = requests.post(post_url, headers=headers, json=payload, timeout=15)

            if post_res.status_code in (200, 201, 204, 12, 13):
                print(f"[OK] Удален {media_type} ID: {media_id} из {list_type}")
                deleted += 1
            else:
                print(f"[ERROR] Не удалось удалить {media_type} ID: {media_id} из {list_type} -> {post_res.status_code} {post_res.text[:300]}")
            time.sleep(0.25)

    print(f"  Итого {list_type} {media_type} удалено (или dry-run): {deleted}")
    return deleted


def main():
    parser = argparse.ArgumentParser(description="Очистка аккаунта TMDB (списки, оценки, watchlist, favorites)")
    parser.add_argument("--dry-run", action="store_true", help="Только показать что будет удалено, без реальных DELETE")
    parser.add_argument("--yes", action="store_true", help="Не спрашивать подтверждение")
    parser.add_argument("--v4-token", type=str, default=None, help="Переопределить токен (иначе из Django UserPreferences)")
    parser.add_argument("--only", type=str, default="all",
                        help="Что чистить: all | lists,ratings,watchlist,favorite (через запятую). Пример: --only lists,ratings")
    parser.add_argument("--v4-id", type=str, default=None, help="Переопределить V4 account_id (иначе авто)")
    parser.add_argument("--v3-id", type=str, default=None, help="Переопределить V3 account_id (иначе авто)")
    args = parser.parse_args()

    token, source = get_token(args.v4_token)
    print(f"[INFO] Token source: {source}")
    print(f"[INFO] Token preview: {token[:12]}...{token[-6:] if len(token) > 18 else ''} (len={len(token)})")

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json;charset=utf-8",
    }

    # резолв ACCOUNT_ID
    if args.v4_id or args.v3_id:
        v4_id = args.v4_id
        # v3 может быть int
        v3_id: int | str | None = int(args.v3_id) if args.v3_id and args.v3_id.isdigit() else args.v3_id
        print(f"[INFO] Using override: V4={v4_id} V3={v3_id}")
    else:
        v4_id, v3_id = resolve_account_ids(token)

    print(f"[INFO] Resolved IDs -> V4: {v4_id!r}  V3: {v3_id!r}")

    # что чистим
    only_raw = args.only.strip().lower()
    if only_raw == "all":
        do_lists = do_ratings = do_watchlist = do_favorite = True
    else:
        parts = {p.strip() for p in only_raw.split(",") if p.strip()}
        do_lists = "lists" in parts
        do_ratings = "ratings" in parts or "rated" in parts
        do_watchlist = "watchlist" in parts
        do_favorite = "favorite" in parts or "favorites" in parts
        if not any([do_lists, do_ratings, do_watchlist, do_favorite]):
            print(f"[FATAL] --only={args.only!r} не распознан. Допустимо: all | lists,ratings,watchlist,favorite")
            sys.exit(1)

    print(f"\n[PLAN] dry_run={args.dry_run}  lists={do_lists} ratings={do_ratings} watchlist={do_watchlist} favorite={do_favorite}")

    if not args.dry_run and not args.yes:
        ans = input("\nВНИМАНИЕ: будут удалены данные TMDB аккаунта! Продолжить? [y/N]: ").strip().lower()
        if ans not in ("y", "yes", "д", "да"):
            print("Отменено.")
            sys.exit(0)

    total = 0
    if do_lists:
        total += delete_user_lists(headers, v4_id, dry_run=args.dry_run)
    if do_ratings:
        total += clear_ratings(headers, v3_id, media_type="movie", dry_run=args.dry_run)
        total += clear_ratings(headers, v3_id, media_type="tv", dry_run=args.dry_run)
    if do_watchlist:
        total += clear_account_states(headers, v3_id, list_type="watchlist", media_type="movie", dry_run=args.dry_run)
        total += clear_account_states(headers, v3_id, list_type="watchlist", media_type="tv", dry_run=args.dry_run)
    if do_favorite:
        total += clear_account_states(headers, v3_id, list_type="favorite", media_type="movie", dry_run=args.dry_run)
        total += clear_account_states(headers, v3_id, list_type="favorite", media_type="tv", dry_run=args.dry_run)

    if args.dry_run:
        print(f"\n[DRY-RUN] Всего кандидатов на удаление: {total}")
    else:
        print(f"\nПолная очистка завершена. Всего удалено: {total}")


if __name__ == "__main__":
    main()
