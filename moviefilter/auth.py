from django.contrib.auth import logout
from django.shortcuts import redirect
from django.urls import reverse


def user_logout(request):
    logout(request)
    return redirect(reverse('moviefilter:movies'))
