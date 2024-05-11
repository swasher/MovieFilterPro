from django.contrib import admin
from .models import Kinorium
from .models import Country
from .models import MovieRSS


class KinoriumMovieAdmin(admin.ModelAdmin):
    pass


class CountryAdmin(admin.ModelAdmin):
    pass

class MovieRssAdmin(admin.ModelAdmin):
    pass
    search_fields = ['title', 'original_title']


admin.site.register(Kinorium, KinoriumMovieAdmin)
admin.site.register(Country, CountryAdmin)
admin.site.register(MovieRSS, MovieRssAdmin)