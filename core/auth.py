from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.urls import reverse
from django.contrib import messages
from django.contrib.auth.models import User
from django.shortcuts import render
from django.contrib.auth import login

from vault.models import UserList

def user_logout(request):
    """
    Пользовательская функция нужная, в частности, потому, что иначе возникает ошибка:

    | По соображениям безопасности, начиная с Django 3, LogoutView по умолчанию принимает только POST запросы.
    | Нажатие на ссылку всегда создает GET запрос. (<a href="{% url 'core:logout' %}?next={% url 'core:login' %}" ...>Logout</a>).
    | Ошибка HTTP ERROR 405 (Method Not Allowed) возникает из-за несоответствия между тем, как настроен URL
    | для выхода из системы, и тем, как кнопка "Logout" в шаблоне пытается на этот URL перейти.
    | Получается, что браузер отправляет GET-запрос, а сервер ожидает POST-запрос, из-за чего и возвращает ошибку 405.
    """
    logout(request)
    return redirect('core:login')


def register_user(request):
    if request.method == 'POST':
        # Получаем данные из формы
        username = request.POST.get('username')
        email = request.POST.get('email')
        password1 = request.POST.get('password1')
        password2 = request.POST.get('password2')

        # Валидация
        if password1 != password2:
            messages.error(request, 'Пароли не совпадают')
            return redirect('core:register')

        if User.objects.filter(username=username).exists():
            messages.error(request, 'Пользователь с таким именем уже существует')
            return redirect('core:register')

        # Создание пользователя
        try:
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password1
            )

            # Ваша кастомная логика
            UserList.create_system_lists(user)

            # Автоматический вход после регистрации (опционально)
            login(request, user)

            messages.success(request, 'Регистрация успешна!')
            return redirect('rss')  # или другой нужный URL

        except Exception as e:
            messages.error(request, f'Ошибка при регистрации: {str(e)}')
            return redirect('core:register')

    return render(request, 'register.html')


@login_required
def delete_account(request):
    if request.method == 'POST':
        username = request.POST.get('username')

        # Если форма требует подтверждения вводом никнейма
        if username and username != request.user.username:
            messages.error(request, 'Имя пользователя не совпадает.')
            return redirect('core:user_preferences')

        try:
            # Полное удаление пользователя и всех связанных данных (включая системные списки)
            UserList.delete_user_completely(request.user)
            logout(request)
            messages.success(request, 'Ваш аккаунт был успешно удален.')
            return redirect('core:login')
        except Exception as e:
            messages.error(request, f'Ошибка при удалении аккаунта: {e}')
            return redirect('core:user_preferences')

    # Если GET запрос, просто возвращаем в настройки
    return redirect('core:user_preferences')
