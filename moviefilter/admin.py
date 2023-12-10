from django.contrib import admin
from .models import Kinorium
from .models import Country


class KinoriumMovieAdmin(admin.ModelAdmin):
    pass


class CountryAdmin(admin.ModelAdmin):
    pass


admin.site.register(Kinorium, KinoriumMovieAdmin)
admin.site.register(Country, CountryAdmin)