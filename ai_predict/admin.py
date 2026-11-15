from django.contrib import admin

from ai_predict.models import MoviePrediction, PromptTemplate, TasteProfile


@admin.register(TasteProfile)
class TasteProfileAdmin(admin.ModelAdmin):
    list_display = ("name", "updated_at", "created_at")
    search_fields = ("name", "content")
    readonly_fields = ("created_at", "updated_at")


@admin.register(PromptTemplate)
class PromptTemplateAdmin(admin.ModelAdmin):
    list_display = ("updated_at",)
    readonly_fields = ("updated_at",)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return True


@admin.register(MoviePrediction)
class MoviePredictionAdmin(admin.ModelAdmin):
    list_display = ("movie", "taste_profile", "status", "score", "verdict", "model_name", "created_at")
    list_filter = ("status", "verdict", "taste_profile")
    search_fields = ("movie__title",)
    raw_id_fields = ("movie",)
    readonly_fields = (
        "movie",
        "taste_profile",
        "status",
        "score",
        "verdict",
        "confidence",
        "result_text",
        "input_snapshot",
        "raw_response",
        "error",
        "model_name",
        "duration_ms",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request):
        return False
