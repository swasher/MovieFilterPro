from django.contrib import admin
from .models import KinoriumMovie


class KinoriumMovieAdmin(admin.ModelAdmin):
    pass


admin.site.register(KinoriumMovie, KinoriumMovieAdmin)