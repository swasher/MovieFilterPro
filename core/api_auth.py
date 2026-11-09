from django.conf import settings
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from core.users import users_exist


def _build_session_payload(request):
    user = request.user
    if not user.is_authenticated:
        return {
            "is_authenticated": False,
            "user": None,
            "users_exist": users_exist(),
            "site_version": settings.VERSION,
        }

    return {
        "is_authenticated": True,
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
        },
        "users_exist": True,
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


@csrf_exempt
@require_POST
def password_change_view(request):
    """Смена пароля текущего пользователя.

    Нужен, потому что на проде не всегда есть доступ к Django Admin.
    Текущий пароль обязателен: endpoint меняет пароль только у уже
    авторизованной сессии, которая его знает.
    """
    user = request.user
    if not user.is_authenticated:
        return JsonResponse({"message": "Требуется авторизация."}, status=401)

    current_password = request.POST.get("current_password") or ""
    new_password = request.POST.get("new_password") or ""

    if not current_password or not new_password:
        return JsonResponse(
            {"message": "Укажи текущий и новый пароль."}, status=400
        )

    if not user.check_password(current_password):
        return JsonResponse({"message": "Текущий пароль неверен."}, status=400)

    if new_password == current_password:
        return JsonResponse(
            {"message": "Новый пароль должен отличаться от текущего."}, status=400
        )

    if settings.DEBUG:
        # В dev разрешаем простой пароль (например, «1234»), чтобы не мешать
        # локальной отладке. На проде работают штатные AUTH_PASSWORD_VALIDATORS.
        if len(new_password) < 4:
            return JsonResponse(
                {"message": "Пароль должен быть не короче 4 символов."}, status=400
            )
    else:
        try:
            validate_password(new_password, user=user)
        except ValidationError as exc:
            return JsonResponse(
                {
                    "message": " ".join(exc.messages),
                    "errors": exc.messages,
                },
                status=400,
            )

    user.set_password(new_password)
    user.save(update_fields=["password"])

    # Не разлогиниваем текущую вкладку: обновляем auth-hash её сессии.
    # Остальные сессии пользователя станут невалидными из-за смены хеша.
    update_session_auth_hash(request, user)

    return JsonResponse({"message": "Пароль изменён."})
