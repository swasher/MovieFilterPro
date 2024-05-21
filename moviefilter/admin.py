from django.contrib import admin
from .models import Kinorium
from .models import Country
from .models import MovieRSS


class KinoriumMovieAdmin(admin.ModelAdmin):
    pass


class CountryAdmin(admin.ModelAdmin):
    pass


class MovieRssAdmin(admin.ModelAdmin):
    list_display = ["title", "original_title", "year", "priority", "date_added"]
    list_display_links = ["title"]
    list_filter = ["priority"]
    search_fields = ['title', 'original_title']


admin.site.register(Kinorium, KinoriumMovieAdmin)
admin.site.register(Country, CountryAdmin)
admin.site.register(MovieRSS, MovieRssAdmin)