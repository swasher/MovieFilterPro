"""
Так как я не осилил создание TMDB write access token через библиотеку TMDbAPIs, я сделал это через нативный ворквлоу
TMDB.
tmdb_auth -> обычный django view для перехода на страницу
tmdb_start -> генерирует аутефикационную ссылку из read access token, по которой должен перейти пользователь
--- после того как пользователь перешел по ссылке и нажал Approve, мы можем получить  write access token
tmdb_approve -> Что мы и делаем в этой функции
"""

import requests
from django.http import HttpResponse
from django.shortcuts import render, redirect
from django.urls import reverse
from django.utils.html import format_html
from threading import Lock
from typing import Optional
from tmdbapis import TMDbAPIs


from moviefilter.models import UserPreferences
from .tmdb_singleton import get_tmdb_client


TMDB_CREATE_REQUEST_TOKEN = "https://api.themoviedb.org/4/auth/request_token"
TMDB_CREATE_ACCESS_TOKEN  = "https://api.themoviedb.org/4/auth/access_token"
TMDB_APPROVE_URL          = "https://www.themoviedb.org/auth/access?request_token="


_tmdb_instance: Optional[TMDbAPIs] = None
_last_key = None
_last_token = None
_lock = Lock()

def tmdb_auth(request):
    prefs = UserPreferences.get()
    return render(request, "tmdb_auth.html", {
        "write_token": prefs.tmdb_v4_authenticated_access_token
    })


def tmdb_start(request):
    prefs = UserPreferences.get()

    headers = {
        "Authorization": f"Bearer {prefs.tmdb_v4_read_access_token}",
        "Content-Type": "application/json"
    }

    r = requests.post(TMDB_CREATE_REQUEST_TOKEN, headers=headers)
    data = r.json()

    if "request_token" not in data:
        return HttpResponse("ERROR: " + str(data))

    request_token = data["request_token"]

    request.session["tmdb_request_token"] = request_token

    approve_url = TMDB_APPROVE_URL + request_token
    finish_url = reverse('tmdb-approve')

    # return HttpResponse(
    #     f'<a href="{approve_url}" target="_blank">{approve_url}</a>'
    #     f'<br><button type="button" class="btn btn-primary" hx-get="{% url '' %}" hx-target="#result">Finish auth</button>'
    # )

    # Кнопка Finish Auth с htmx
    html = format_html(
        '<a href="{}" target="_blank">{}</a>'
        '<br><button type="button" class="btn btn-primary" '
        'hx-get="{}" hx-target="#result">Finish auth</button>',
        approve_url, approve_url, finish_url
    )
    # Кнопка без htmx
    html = format_html(
        '<a href="{}" target="_blank">{}</a>'
        '<br>'
        '<a class="btn btn-primary" href="{}">Finish auth</a>',
        approve_url, approve_url, finish_url
    )

    return HttpResponse(html)


def tmdb_approve(request):
    prefs = UserPreferences.get()
    request_token = request.session.get("tmdb_request_token")

    if not request_token:
        return HttpResponse("ERROR: no request_token in session")

    headers = {
        "Authorization": f"Bearer {prefs.tmdb_v4_read_access_token}",
        "Content-Type": "application/json"
    }

    payload = {"request_token": request_token}

    r = requests.post(TMDB_CREATE_ACCESS_TOKEN, json=payload, headers=headers)
    data = r.json()

    if "access_token" not in data:
        return HttpResponse("ERROR: " + str(data))

    access_token = data["access_token"]

    prefs.tmdb_v4_authenticated_access_token = access_token
    prefs.save()

    # return HttpResponse(access_token)
    return redirect("tmdb_auth")


def tmdb_logout(request):
    prefs = UserPreferences.get()

    # 1. Получаем клиент (если токен есть)
    if prefs.tmdb_v4_authenticated_access_token:
        try:
            tmdb = get_tmdb_client(prefs.tmdb_api_key, prefs.tmdb_v4_authenticated_access_token)
            tmdb.logout()
        except Exception as e:
            print(f"Logout API call failed (maybe token already expired): {e}")

    # 2. КРИТИЧЕСКИ ВАЖНО: Инвалидируем синглтон
    reset_tmdb_client()

    # 3. Очищаем токен в базе
    prefs.tmdb_v4_authenticated_access_token = None
    prefs.save()

    return redirect('tmdb_auth')


def reset_tmdb_client():
    """Сбрасывает синглтон TMDB клиента"""
    global _tmdb_instance, _last_key, _last_token

    with _lock:
        _tmdb_instance = None
        _last_key = None
        _last_token = None
