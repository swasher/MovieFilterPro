from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render, redirect
from django.urls import reverse

from .forms import PreferencesForm
from moviefilter.models import UserPreferences


@login_required()
def user_preferences_update(request):
    pref = UserPreferences.get()
    form = PreferencesForm(request.POST or None, instance=pref)

    if request.method == 'POST' and form.is_valid():
        form.save()
        return redirect(reverse('core:user_preferences'))

    return render(request, 'preferences_update_form.html', {'form': form})


def tst(request):
    if request.method == 'POST':
        print(request.POST)
    if request.method == 'GET':
        print(request.GET)

    if request.htmx:
        return HttpResponse('SOME HTMX DATA')
    else:
        return render(request, 'testing.html')
