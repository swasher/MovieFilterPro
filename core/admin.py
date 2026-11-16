from django.contrib import admin

from core.models import AiEndpoint


@admin.register(AiEndpoint)
class AiEndpointAdmin(admin.ModelAdmin):
    list_display = ("name", "base_url", "model", "updated_at")
    search_fields = ("name", "base_url", "model")
    readonly_fields = ("created_at", "updated_at")
