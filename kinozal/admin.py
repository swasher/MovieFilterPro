from django.contrib import admin
from .models import KinoriumMovie
from .models import Country


class KinoriumMovieAdmin(admin.ModelAdmin):
    pass


class CountryAdmin(admin.ModelAdmin):
    pass


admin.site.register(KinoriumMovie, KinoriumMovieAdmin)
admin.site.register(Country, CountryAdmin)