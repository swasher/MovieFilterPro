from django.contrib.auth import get_user_model


def users_exist() -> bool:
    """Есть ли в базе хотя бы один пользователь."""
    return get_user_model().objects.exists()
