from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST


def _build_session_payload(request):
    user = request.user
    if not user.is_authenticated:
        return {
            "is_authenticated": False,
            "user": None,
            "site_version": settings.VERSION,
        }

    return {
        "is_authenticated": True,
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
        },
        "site_version": settings.VERSION,
    }


@ensure_csrf_cookie
@require_GET
def session_view(request):
    response = JsonResponse(_build_session_payload(request))
    # Ensure frontend always has a fresh CSRF cookie for subsequent POST requests.
    get_token(request)
    return response


@csrf_exempt
@require_POST
def login_view(request):
    username = (request.POST.get("username") or "").strip()
    password = request.POST.get("password") or ""

    if not username or not password:
        response = JsonResponse(
            {
                "message": "Укажи логин и пароль.",
                **_build_session_payload(request),
            },
            status=400,
        )
        get_token(request)
        return response

    user = authenticate(request, username=username, password=password)
    if user is None:
        response = JsonResponse(
            {
                "message": "Неверный логин или пароль.",
                "is_authenticated": False,
                "user": None,
            },
            status=400,
        )
        get_token(request)
        return response

    login(request, user)
    response = JsonResponse(
        {
            "message": "Вход выполнен.",
            **_build_session_payload(request),
        }
    )
    get_token(request)
    return response


@csrf_exempt
@require_POST
def logout_view(request):
    logout(request)
    response = JsonResponse(
        {
            "message": "Выход выполнен.",
            "is_authenticated": False,
            "user": None,
        }
    )
    get_token(request)
    return response
