from django.contrib import admin

from bestfilmsof.models import (
    BestfilmsCache,
    BestfilmsEntry,
    BestfilmsGenreYear,
    BestfilmsSync,
)


@admin.register(BestfilmsEntry)
class BestfilmsEntryAdmin(admin.ModelAdmin):
    list_display = ("year", "genre", "position", "score", "title", "imdb_id", "tmdb_id")
    list_filter = ("year", "genre")
    search_fields = ("title", "imdb_id")
    ordering = ("year", "genre", "position")


@admin.register(BestfilmsCache)
class BestfilmsCacheAdmin(admin.ModelAdmin):
    list_display = ("tmdb_id", "title", "title_ru", "release_date", "fetched_at")
    search_fields = ("title", "title_ru", "tmdb_id")


@admin.register(BestfilmsSync)
class BestfilmsSyncAdmin(admin.ModelAdmin):
    list_display = ("key", "status", "synced_at", "started_at", "finished_at")
    list_filter = ("status",)
    search_fields = ("key",)


@admin.register(BestfilmsGenreYear)
class BestfilmsGenreYearAdmin(admin.ModelAdmin):
    list_display = ("genre", "year", "count", "top_title", "top_score")
    list_filter = ("genre",)
    search_fields = ("top_title",)
