from django.contrib import admin

from .models import Torrent, TorrentEvent


@admin.register(Torrent)
class TorrentAdmin(admin.ModelAdmin):
    list_display = ['name', 'info_hash', 'movie', 'created_at']
    search_fields = ['name', 'info_hash']
    autocomplete_fields = ['movie']
    date_hierarchy = 'created_at'


@admin.register(TorrentEvent)
class TorrentEventAdmin(admin.ModelAdmin):
    list_display = ['event_type', 'level', 'torrent', 'movie', 'created_at']
    list_filter = ['level', 'event_type']
    search_fields = ['message']
    date_hierarchy = 'created_at'
