from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render, redirect
from django.urls import reverse

from .forms import PreferencesForm
from moviefilter.models import UserPreferences


@login_required()
def user_preferences_update(request):
    # deprecated  user = User.objects.get(pk=request.user.pk)
    pref = UserPreferences.get()
    form = PreferencesForm(request.POST or None, instance=pref)

    if request.method == 'POST':
        if form.is_valid():
            # pref = UserPreferences.objects.get_or_create(user=request.user)
            pref.last_scan = form.cleaned_data['last_scan']
            pref.scan_from_page = form.cleaned_data['scan_from_page']
            pref.countries = form.cleaned_data['countries']
            pref.genres = form.cleaned_data['genres']
            pref.max_year = int(form.cleaned_data['max_year'])
            pref.min_rating = float(form.cleaned_data['min_rating'])

            pref.low_countries = form.cleaned_data['low_countries']
            pref.low_genres = form.cleaned_data['low_genres']
            pref.low_max_year = int(form.cleaned_data['low_max_year'])
            pref.low_min_rating = float(form.cleaned_data['low_min_rating'])

            pref.kinozal_domain = form.cleaned_data['kinozal_domain']

            pref.plex_address = form.cleaned_data['plex_address']
            pref.plex_token = form.cleaned_data['plex_token']

            pref.save()
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
