from django.contrib import admin
from django.utils.html import format_html
from .models import (
    Movie, Person, Genre, MoviePerson,
    UserList, UserListMovie, UserMovie
)
from core.models import Country


@admin.register(Genre)
class GenreAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'movies_count']
    prepopulated_fields = {'slug': ('name',)}
    search_fields = ['name']

    def movies_count(self, obj):
        return obj.movies.count()

    movies_count.short_description = 'Фильмов'


@admin.register(Country)
class CountryAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'movies_count']
    search_fields = ['name', 'code']

    def movies_count(self, obj):
        return obj.movies.count()

    movies_count.short_description = 'Фильмов'


@admin.register(Person)
class PersonAdmin(admin.ModelAdmin):
    list_display = ['full_name', 'birth_date', 'country', 'gender', 'photo_preview']
    list_filter = ['country', 'gender', 'birth_date']
    search_fields = ['first_name', 'last_name']
    date_hierarchy = 'birth_date'

    fieldsets = (
        ('Основная информация', {
            'fields': ('first_name', 'last_name', 'photo', 'gender')
        }),
        ('Даты', {
            'fields': ('birth_date', 'death_date')
        }),
        ('Дополнительно', {
            'fields': ('country', 'biography'),
            'classes': ('collapse',)
        }),
    )

    def full_name(self, obj):
        return f"{obj.first_name} {obj.last_name}"

    full_name.short_description = 'ФИО'

    def photo_preview(self, obj):
        if obj.photo:
            return format_html('<img src="{}" width="50" height="50" style="object-fit: cover; border-radius: 50%;" />',
                               obj.photo.url)
        return '-'

    photo_preview.short_description = 'Фото'


class MoviePersonInline(admin.TabularInline):
    model = MoviePerson
    extra = 1
    autocomplete_fields = ['person']
    fields = ['person', 'role', 'character_name', 'order']


@admin.register(Movie)
class MovieAdmin(admin.ModelAdmin):
    list_display = ['title', 'year', 'movie_type', 'status', 'imdb_rating', 'poster_preview', 'created_at']
    list_filter = ['status', 'movie_type', 'year', 'genres', 'countries']
    search_fields = ['title', 'original_title', 'description']
    prepopulated_fields = {'slug': ('title',)}
    filter_horizontal = ['genres', 'countries']
    date_hierarchy = 'created_at'
    inlines = [MoviePersonInline]

    fieldsets = (
        ('Основная информация', {
            'fields': ('title', 'original_title', 'slug', 'description', 'poster')
        }),
        ('Классификация', {
            'fields': ('movie_type', 'status', 'genres', 'countries', 'age_rating')
        }),
        ('Даты и время', {
            'fields': ('year', 'release_date', 'duration')
        }),
        ('Рейтинги', {
            'fields': ('imdb_rating', 'imdb_votes'),
            'classes': ('collapse',)
        }),
        ('Финансы', {
            'fields': ('budget', 'box_office'),
            'classes': ('collapse',)
        }),
        ('Медиа', {
            'fields': ('trailer_url',),
            'classes': ('collapse',)
        }),
    )

    def poster_preview(self, obj):
        if obj.poster:
            return format_html('<img src="{}" width="40" height="60" style="object-fit: cover;" />', obj.poster.url)
        return '-'

    poster_preview.short_description = 'Постер'

    def save_model(self, request, obj, form, change):
        # Автоматическое заполнение slug если не указан
        if not obj.slug:
            from slugify import slugify
            obj.slug = slugify(obj.title)
        super().save_model(request, obj, form, change)


@admin.register(MoviePerson)
class MoviePersonAdmin(admin.ModelAdmin):
    list_display = ['movie', 'person', 'role', 'character_name', 'order']
    list_filter = ['role']
    search_fields = ['movie__title', 'person__first_name', 'person__last_name', 'character_name']
    autocomplete_fields = ['movie', 'person']


@admin.register(UserList)
class UserListAdmin(admin.ModelAdmin):
    list_display = ['name', 'user', 'is_public', 'movies_count', 'updated_at']
    list_filter = ['is_public', 'created_at']
    search_fields = ['name', 'user__username', 'description']
    readonly_fields = ['created_at', 'updated_at']
    date_hierarchy = 'created_at'

    fieldsets = (
        ('Основная информация', {
            'fields': ('user', 'name', 'description')
        }),
        ('Настройки', {
            'fields': ('is_public',)
        }),
        ('Даты', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def movies_count(self, obj):
        return obj.list_movies.count()

    movies_count.short_description = 'Фильмов'


@admin.register(UserListMovie)
class UserListMovieAdmin(admin.ModelAdmin):
    list_display = ['user_list', 'movie', 'added_at']
    list_filter = ['added_at']
    search_fields = ['movie__title', 'user_list__name']
    autocomplete_fields = ['movie', 'user_list']
    date_hierarchy = 'added_at'


@admin.register(UserMovie)
class UserMovieAdmin(admin.ModelAdmin):
    list_display = [
        'user', 'movie', 'watch_status', 'is_favorite', 'rating', 'watched_at',
        'rated_at', 'status_at', 'note_at', 'favorited_at', 'updated_at',
    ]
    list_filter = [
        'watch_status', 'is_favorite', 'rating', 'watched_at',
        'rated_at', 'status_at', 'note_at', 'favorited_at', 'updated_at',
    ]
    search_fields = ['user__username', 'movie__title']
    date_hierarchy = 'updated_at'


# Настройка заголовков админки
admin.site.site_header = 'Vault - Администрирование'
admin.site.site_title = 'Vault Admin'
admin.site.index_title = 'Управление фильмотекой'
