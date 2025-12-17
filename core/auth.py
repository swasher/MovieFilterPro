from django.contrib.auth import logout
from django.shortcuts import redirect
from django.urls import reverse


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
