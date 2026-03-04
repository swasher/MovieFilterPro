from django.shortcuts import get_object_or_404
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.urls import reverse_lazy, reverse
from django.http import HttpResponse
from django.db.models import Q, Avg, Count
from django.http import Http404
from django.contrib import messages
from django.utils.html import escape

from .models import (
    Movie, Person, Genre, UserList, UserListMovie,
    UserMovie, MoviePerson
)
from .services.movie_status_service import MovieStatusService
from .services.tmdb_movie_matching_service import TMDBCandidate
from .services.tmdb_movie_sync_service import TMDBMovieSyncService


SYSTEM_LIST_CONFIG = {
    'watched': {'name': 'Просмотрено'},
    'will_watch': {'name': 'Буду смотреть'},
    'wont_watch': {'name': 'Не буду смотреть'},
    'favorites': {'name': 'Избранное'},
}


def _render_rating_controls(movie_id: int, rating_value: int | None = None) -> str:
    html = '<div class="btn-group" role="group">'
    for i in range(1, 11):
        btn_class = 'btn-warning' if i == rating_value else 'btn-outline-warning'
        html += f'''
        <button type="button" class="btn btn-sm {btn_class}" 
                hx-post="{reverse('vault:htmx_rate_movie')}"
                hx-vals='{{"movie_id": "{movie_id}", "rating": "{i}"}}'
                hx-target="#movie-rating-controls"
                hx-swap="innerHTML">
            {i}
        </button>
        '''
    html += '</div>'

    if rating_value is not None:
        html += f'''
        <button type="button" class="btn btn-sm btn-outline-danger ms-2" 
                hx-post="{reverse('vault:htmx_remove_rating')}"
                hx-vals='{{"movie_id": "{movie_id}"}}'
                hx-target="#movie-rating-controls"
                hx-swap="innerHTML">
            <i class="bi bi-x"></i> Удалить оценку
        </button>
        '''

    return html


def _to_bool(value: str | None) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _to_int(value: str | None) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _render_tmdb_sync_result_html(result, movie_id: int) -> str:
    if result.status == "ok":
        updated_fields = ", ".join(result.updated_fields) if result.updated_fields else "нет изменений"
        orphan_deleted = result.orphan_persons_deleted
        orphan_info = (
            f'<div class="small text-muted mt-1">Удалено orphan-персон: {orphan_deleted}</div>'
            if orphan_deleted
            else ''
        )
        return f'''
        <div class="alert alert-success mb-2">
            <strong>TMDB sync completed.</strong>
            <div class="small mt-1">Обновлено: {escape(updated_fields)}</div>
            {orphan_info}
        </div>
        '''

    if result.status == "needs_user_choice":
        return _render_tmdb_candidates_modal(candidates=result.candidates, movie_id=movie_id, message=result.message)

    return f'''
    <div class="alert alert-danger mb-2">
        <strong>TMDB sync failed.</strong>
        <div class="small mt-1">{escape(result.message or "Неизвестная ошибка")}</div>
    </div>
    '''


def _render_tmdb_candidates_modal(candidates, movie_id: int, message: str = "") -> str:
    modal_id = f"tmdbCandidateModal{movie_id}"
    intro = escape(message or "Найдено несколько похожих фильмов. Выберите нужный вариант.")

    rows = []
    for candidate in candidates:
        reasons = ", ".join(candidate.score_reasons) if candidate.score_reasons else "-"
        title = escape(candidate.title or "Без названия")
        original_title = escape(candidate.original_title or "")
        year = candidate.year if candidate.year else "?"
        media = "movie" if candidate.media_type == "movie" else "tv"

        rows.append(
            f'''
            <div class="border rounded p-2 mb-2">
                <div class="d-flex justify-content-between align-items-start gap-3">
                    <div>
                        <div><strong>{title}</strong> <span class="badge bg-secondary ms-1">{media}</span></div>
                        <div class="small text-muted">{original_title}</div>
                        <div class="small">Год: {year} | Score: {candidate.score}</div>
                        <div class="small text-muted">Причины: {escape(reasons)}</div>
                    </div>
                    <button type="button"
                            class="btn btn-sm btn-primary"
                            hx-post="{reverse('vault:htmx_fetch_tmdb_confirm')}"
                            hx-vals='{{"movie_id": "{movie_id}", "tmdb_id": "{candidate.tmdb_id}", "media_type": "{candidate.media_type}"}}'
                            hx-target="#tmdb-sync-result"
                            hx-swap="innerHTML"
                            data-bs-dismiss="modal">
                        Выбрать
                    </button>
                </div>
            </div>
            '''
        )

    rows_html = "".join(rows) if rows else '<div class="text-muted">Кандидаты не найдены.</div>'

    return f'''
    <div class="alert alert-warning mb-2">{intro}</div>
    <div class="modal fade" id="{modal_id}" tabindex="-1" aria-hidden="true">
        <div class="modal-dialog modal-lg modal-dialog-scrollable">
            <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title">Выбор фильма на TMDB</h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                </div>
                <div class="modal-body">
                    {rows_html}
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Закрыть</button>
                </div>
            </div>
        </div>
    </div>
    <script>
      (function() {{
        var modalEl = document.getElementById('{modal_id}');
        if (!modalEl || typeof bootstrap === 'undefined') return;
        var modal = bootstrap.Modal.getOrCreateInstance(modalEl);
        modal.show();
      }})();
    </script>
    '''


class MovieListView(ListView):
    """Список всех фильмов"""
    model = Movie
    template_name = 'vault/movie_list.html'
    context_object_name = 'movies'
    paginate_by = 20
    STATUS_TO_WATCH_STATUS = {
        'watched': UserMovie.WatchStatus.WATCHED,
        'will_watch': UserMovie.WatchStatus.PLAN,
        'wont_watch': UserMovie.WatchStatus.SKIP,
    }

    def get_queryset(self):
        queryset = Movie.objects.filter(status='released').prefetch_related('genres', 'countries')
        queryset = self._apply_status_filter(queryset)

        # Сортировка
        order = self.request.GET.get('order', '-year')
        queryset = queryset.order_by(order)

        return queryset

    def _apply_status_filter(self, queryset):
        if not self.request.user.is_authenticated:
            return queryset

        selected_status = self.request.GET.get('status')
        if selected_status == 'favorites':
            return queryset.filter(
                user_movies__user=self.request.user,
                user_movies__is_favorite=True,
            ).distinct()
        if selected_status in self.STATUS_TO_WATCH_STATUS:
            return queryset.filter(
                user_movies__user=self.request.user,
                user_movies__watch_status=self.STATUS_TO_WATCH_STATUS[selected_status],
            ).distinct()
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['genres'] = Genre.objects.all()
        context['selected_genre'] = None
        context['selected_status'] = self.request.GET.get('status', '')
        context['custom_lists'] = UserList.objects.filter(user=self.request.user) if self.request.user.is_authenticated else []
        context['active_list_pk'] = None
        context['sidebar_status_mode'] = 'filter'
        return context


class MovieByGenreView(ListView):
    """Фильмы по жанру"""
    model = Movie
    template_name = 'vault/movie_list.html'
    context_object_name = 'movies'
    paginate_by = 20
    STATUS_TO_WATCH_STATUS = MovieListView.STATUS_TO_WATCH_STATUS

    def get_queryset(self):
        self.genre = get_object_or_404(Genre, slug=self.kwargs['slug'])
        queryset = Movie.objects.filter(
            genres=self.genre,
            status='released'
        ).prefetch_related('genres', 'countries')
        queryset = self._apply_status_filter(queryset)

        order = self.request.GET.get('order', '-year')
        queryset = queryset.order_by(order)

        return queryset

    def _apply_status_filter(self, queryset):
        if not self.request.user.is_authenticated:
            return queryset

        selected_status = self.request.GET.get('status')
        if selected_status == 'favorites':
            return queryset.filter(
                user_movies__user=self.request.user,
                user_movies__is_favorite=True,
            ).distinct()
        if selected_status in self.STATUS_TO_WATCH_STATUS:
            return queryset.filter(
                user_movies__user=self.request.user,
                user_movies__watch_status=self.STATUS_TO_WATCH_STATUS[selected_status],
            ).distinct()
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['genres'] = Genre.objects.all()
        context['selected_genre'] = self.genre
        context['selected_status'] = self.request.GET.get('status', '')
        context['custom_lists'] = UserList.objects.filter(user=self.request.user) if self.request.user.is_authenticated else []
        context['active_list_pk'] = None
        context['sidebar_status_mode'] = 'filter'
        return context


class MovieDetailView(DetailView):
    """Детальная страница фильма"""
    model = Movie
    template_name = 'vault/movie_detail.html'
    context_object_name = 'movie'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        movie = self.object

        # Статус фильма у пользователя
        if self.request.user.is_authenticated:
            context['movie_status'] = MovieStatusService.get_movie_status(
                self.request.user, movie
            )
            context['user_rating'] = context['movie_status']['rating']
            context['user_note'] = context['movie_status']['note']
        else:
            context['movie_status'] = {
                'in_watched': False,
                'in_will_watch': False,
                'in_wont_watch': False,
                'in_favorites': False,
                'rating': None,
                'note': '',
            }
            context['user_rating'] = None
            context['user_note'] = ''

        context['rating_values'] = range(1, 11)

        return context


class SearchView(ListView):
    """Поиск фильмов"""
    model = Movie
    template_name = 'vault/movie_list.html'
    context_object_name = 'movies'
    paginate_by = 20
    STATUS_TO_WATCH_STATUS = MovieListView.STATUS_TO_WATCH_STATUS

    def get_queryset(self):
        query = self.request.GET.get('q', '')

        if query:
            queryset = Movie.objects.filter(
                Q(title__icontains=query) |
                Q(original_title__icontains=query) |
                Q(description__icontains=query)
            ).prefetch_related('genres', 'countries')
        else:
            queryset = Movie.objects.none()

        queryset = self._apply_status_filter(queryset)
        return queryset

    def _apply_status_filter(self, queryset):
        if not self.request.user.is_authenticated:
            return queryset

        selected_status = self.request.GET.get('status')
        if selected_status == 'favorites':
            return queryset.filter(
                user_movies__user=self.request.user,
                user_movies__is_favorite=True,
            ).distinct()
        if selected_status in self.STATUS_TO_WATCH_STATUS:
            return queryset.filter(
                user_movies__user=self.request.user,
                user_movies__watch_status=self.STATUS_TO_WATCH_STATUS[selected_status],
            ).distinct()
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['genres'] = Genre.objects.all()
        context['selected_genre'] = None
        context['search_query'] = self.request.GET.get('q', '')
        context['selected_status'] = self.request.GET.get('status', '')
        context['custom_lists'] = UserList.objects.filter(user=self.request.user) if self.request.user.is_authenticated else []
        context['active_list_pk'] = None
        context['sidebar_status_mode'] = 'filter'
        return context


class PersonDetailView(DetailView):
    """Страница персоны (актер, режиссер и т.д.)"""
    model = Person
    template_name = 'vault/person_detail.html'
    context_object_name = 'person'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        person = self.object

        # Все фильмы персоны
        all_movies = MoviePerson.objects.filter(
            person=person
        ).select_related('movie').order_by('-movie__year')

        context['all_movies'] = all_movies
        context['movies_count'] = all_movies.count()

        # По ролям
        context['actor_movies'] = all_movies.filter(role='actor')
        context['director_movies'] = all_movies.filter(role='director')
        context['producer_movies'] = all_movies.filter(role='producer')

        # Статистика
        context['roles_count'] = all_movies.values('role').distinct().count()

        # Годы карьеры
        years = all_movies.values_list('movie__year', flat=True)
        if years:
            context['career_years'] = max(years) - min(years)
        else:
            context['career_years'] = 0

        return context


class MyListsView(LoginRequiredMixin, ListView):
    """Все списки пользователя"""
    model = UserList
    template_name = 'vault/my_lists.html'
    context_object_name = 'user_lists'

    def get_queryset(self):
        return UserList.objects.filter(user=self.request.user).prefetch_related('list_movies')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        counts = MovieStatusService.get_system_lists_counts(self.request.user)
        context['system_lists'] = [
            {
                'slug': 'watched',
                'name': SYSTEM_LIST_CONFIG['watched']['name'],
                'count': counts['watched'],
            },
            {
                'slug': 'will_watch',
                'name': SYSTEM_LIST_CONFIG['will_watch']['name'],
                'count': counts['will_watch'],
            },
            {
                'slug': 'wont_watch',
                'name': SYSTEM_LIST_CONFIG['wont_watch']['name'],
                'count': counts['wont_watch'],
            },
            {
                'slug': 'favorites',
                'name': SYSTEM_LIST_CONFIG['favorites']['name'],
                'count': counts['favorites'],
            },
        ]
        context['custom_lists'] = self.get_queryset()
        context['selected_status'] = ''
        context['active_list_pk'] = None
        context['sidebar_status_mode'] = 'system'

        return context


class ListDetailView(LoginRequiredMixin, DetailView):
    """Детальная страница списка"""
    model = UserList
    template_name = 'vault/list_detail.html'
    context_object_name = 'user_list'

    def get_queryset(self):
        return UserList.objects.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user_list = self.object

        # Фильмы из списка
        list_movies = UserListMovie.objects.filter(
            user_list=user_list
        ).select_related('movie').prefetch_related('movie__genres')

        # Сортировка
        order = self.request.GET.get('order', '-added_at')
        if order == '-added_at':
            list_movies = list_movies.order_by('-added_at')
        elif order == '-year':
            list_movies = list_movies.order_by('-movie__year')
        elif order == '-imdb_rating':
            list_movies = list_movies.order_by('-movie__imdb_rating')
        elif order == 'title':
            list_movies = list_movies.order_by('movie__title')

        context['list_movies'] = list_movies
        context['movies'] = Movie.objects.filter(
            id__in=list_movies.values_list('movie_id', flat=True)
        )

        # Статистика
        movies = context['movies']
        context['avg_duration'] = movies.aggregate(Avg('duration'))['duration__avg']
        context['avg_rating'] = movies.aggregate(Avg('imdb_rating'))['imdb_rating__avg']

        # Популярные жанры
        context['top_genres'] = Genre.objects.filter(
            movies__in=movies
        ).annotate(count=Count('movies')).order_by('-count')[:5]
        context['is_system_list'] = False
        context['custom_lists'] = UserList.objects.filter(user=self.request.user)
        context['selected_status'] = ''
        context['active_list_pk'] = user_list.pk
        context['sidebar_status_mode'] = 'system'

        return context


class SystemListDetailView(LoginRequiredMixin, ListView):
    """Детальная страница системного списка (статус/избранное)"""
    model = UserMovie
    template_name = 'vault/list_detail.html'
    context_object_name = 'list_movies'

    def dispatch(self, request, *args, **kwargs):
        self.system_list = kwargs['system_list']
        if self.system_list not in SYSTEM_LIST_CONFIG:
            raise Http404("Системный список не найден")
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        queryset = UserMovie.objects.filter(user=self.request.user).select_related('movie').prefetch_related('movie__genres')

        if self.system_list == 'favorites':
            queryset = queryset.filter(is_favorite=True)
        else:
            watch_status = MovieStatusService.STATUS_KEY_TO_WATCH_STATUS[self.system_list]
            queryset = queryset.filter(watch_status=watch_status)

        order = self.request.GET.get('order', '-added_at')
        if order == '-added_at':
            queryset = queryset.order_by('-created_at')
        elif order == '-year':
            queryset = queryset.order_by('-movie__year')
        elif order == '-imdb_rating':
            queryset = queryset.order_by('-movie__imdb_rating')
        elif order == 'title':
            queryset = queryset.order_by('movie__title')

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        list_movies = context['list_movies']
        movies = Movie.objects.filter(id__in=list_movies.values_list('movie_id', flat=True))
        context['movies'] = movies
        context['avg_duration'] = movies.aggregate(Avg('duration'))['duration__avg']
        context['avg_rating'] = movies.aggregate(Avg('imdb_rating'))['imdb_rating__avg']
        context['top_genres'] = Genre.objects.filter(
            movies__in=movies
        ).annotate(count=Count('movies')).order_by('-count')[:5]
        context['user_list'] = {
            'name': SYSTEM_LIST_CONFIG[self.system_list]['name'],
            'description': '',
            'is_public': False,
            'is_system': True,
            'status_key': self.system_list,
        }
        context['is_system_list'] = True
        context['custom_lists'] = UserList.objects.filter(user=self.request.user)
        context['selected_status'] = self.system_list
        context['active_list_pk'] = None
        context['sidebar_status_mode'] = 'system'
        return context


class ListCreateView(LoginRequiredMixin, CreateView):
    """Создание нового списка"""
    model = UserList
    template_name = 'vault/list_create.html'
    fields = ['name', 'description', 'is_public']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['custom_lists'] = UserList.objects.filter(user=self.request.user)
        context['selected_status'] = ''
        context['active_list_pk'] = None
        context['sidebar_status_mode'] = 'system'
        return context

    def form_valid(self, form):
        form.instance.user = self.request.user
        messages.success(self.request, 'Список успешно создан!')
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('vault:list_detail', kwargs={'pk': self.object.pk})


class ListUpdateView(LoginRequiredMixin, UpdateView):
    """Редактирование списка"""
    model = UserList
    template_name = 'vault/list_create.html'
    fields = ['name', 'description', 'is_public']

    def get_queryset(self):
        return UserList.objects.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['custom_lists'] = UserList.objects.filter(user=self.request.user)
        context['selected_status'] = ''
        context['active_list_pk'] = self.object.pk
        context['sidebar_status_mode'] = 'system'
        return context

    def form_valid(self, form):
        messages.success(self.request, 'Список успешно обновлен!')
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('vault:list_detail', kwargs={'pk': self.object.pk})


class ListDeleteView(LoginRequiredMixin, DeleteView):
    """Удаление списка"""
    model = UserList
    success_url = reverse_lazy('vault:my_lists')

    def get_queryset(self):
        return UserList.objects.filter(user=self.request.user)

    def delete(self, request, *args, **kwargs):
        messages.success(request, 'Список успешно удален!')
        return super().delete(request, *args, **kwargs)


# ============== HTMX Views ==============

@login_required
def fetch_tmdb_data(request):
    """Синхронизация данных фильма из TMDB (HTMX)."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    movie_id = _to_int(request.POST.get('movie_id'))
    if not movie_id:
        return HttpResponse('<div class="alert alert-danger">Не передан movie_id</div>', status=400)

    force_rematch = _to_bool(request.POST.get('force_rematch'))
    movie = get_object_or_404(Movie, id=movie_id)

    try:
        result = TMDBMovieSyncService.sync_movie(movie=movie, force_rematch=force_rematch)
        return HttpResponse(_render_tmdb_sync_result_html(result=result, movie_id=movie.id))
    except Exception as e:
        return HttpResponse(
            f'<div class="alert alert-danger">Ошибка TMDB sync: {escape(str(e))}</div>',
            status=400,
        )


@login_required
def fetch_tmdb_data_confirm(request):
    """Подтверждение выбора кандидата TMDB из модального окна (HTMX)."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    movie_id = _to_int(request.POST.get('movie_id'))
    tmdb_id = _to_int(request.POST.get('tmdb_id'))
    media_type = (request.POST.get('media_type') or '').strip().lower()

    if not movie_id or not tmdb_id or media_type not in {'movie', 'tv'}:
        return HttpResponse('<div class="alert alert-danger">Некорректные данные выбора TMDB</div>', status=400)

    movie = get_object_or_404(Movie, id=movie_id)
    candidate = TMDBCandidate(
        tmdb_id=tmdb_id,
        media_type=media_type,
        title='',
        original_title='',
        year=None,
        score=0,
        score_reasons=('manual_choice',),
        poster_path=None,
        popularity=None,
        vote_average=None,
    )

    try:
        result = TMDBMovieSyncService.sync_movie(
            movie=movie,
            force_rematch=True,
            selected_candidate=candidate,
        )
        return HttpResponse(_render_tmdb_sync_result_html(result=result, movie_id=movie.id))
    except Exception as e:
        return HttpResponse(
            f'<div class="alert alert-danger">Ошибка подтверждения TMDB: {escape(str(e))}</div>',
            status=400,
        )


@login_required
def toggle_movie_status(request):
    """Переключить статус фильма (HTMX)"""
    if request.method == 'POST':
        movie_id = request.POST.get('movie_id')
        status_key = request.POST.get('status_key') or request.POST.get('list_type')

        movie = get_object_or_404(Movie, id=movie_id)

        try:
            is_added = MovieStatusService.toggle_status(
                request.user, movie, status_key
            )

            # Возвращаем обновленную кнопку
            button_class = 'btn-primary' if status_key == 'will_watch' else \
                'btn-danger' if status_key == 'favorites' else \
                    'btn-success' if status_key == 'watched' else 'btn-secondary'

            icon_name = 'bookmark' if status_key == 'will_watch' else \
                'heart' if status_key == 'favorites' else \
                    'check-circle' if status_key == 'watched' else 'x-circle'

            if is_added:
                icon_name += '-fill'
                btn_class = button_class
            else:
                btn_class = button_class.replace('btn-', 'btn-outline-')

            label = 'Буду смотреть' if status_key == 'will_watch' else \
                'Избранное' if status_key == 'favorites' else \
                    'Просмотрено' if status_key == 'watched' else 'Не буду смотреть'

            html = f'''
            <button type="button" class="btn {btn_class}" 
                    hx-post="{reverse('vault:htmx_toggle_status')}"
                    hx-vals='{{"movie_id": "{movie_id}", "status_key": "{status_key}"}}'
                    data-action="toggle-status"
                    data-status-key="{status_key}"
                    hx-swap="outerHTML">
                <i class="bi bi-{icon_name}"></i>
                {label}
            </button>
            '''

            return HttpResponse(html)
        except Exception as e:
            return HttpResponse(f'<div class="alert alert-danger">Ошибка: {str(e)}</div>', status=400)

    return HttpResponse(status=405)


@login_required
def rate_movie(request):
    """Поставить оценку фильму (HTMX)"""
    if request.method == 'POST':
        movie_id = request.POST.get('movie_id')
        rating_raw = request.POST.get('rating')
        if not rating_raw:
            return HttpResponse('<div class="alert alert-danger">Не передана оценка</div>', status=400)

        try:
            rating_value = int(rating_raw)
            movie = get_object_or_404(Movie, id=movie_id)
            MovieStatusService.rate_movie(request.user, movie, rating_value)
            return HttpResponse(_render_rating_controls(movie.id, rating_value))
        except Exception as e:
            return HttpResponse(f'<div class="alert alert-danger">Ошибка: {str(e)}</div>', status=400)

    return HttpResponse(status=405)


@login_required
def remove_rating(request):
    """Удалить оценку (HTMX)"""
    if request.method == 'POST':
        movie_id = request.POST.get('movie_id')
        movie = get_object_or_404(Movie, id=movie_id)

        try:
            MovieStatusService.remove_rating(request.user, movie)
            return HttpResponse(_render_rating_controls(movie.id))
        except Exception as e:
            return HttpResponse(f'<div class="alert alert-danger">Ошибка: {str(e)}</div>', status=400)

    return HttpResponse(status=405)


@login_required
def add_to_list(request):
    """Добавить фильм в список (HTMX)"""
    if request.method == 'POST':
        movie_id = request.POST.get('movie_id')
        list_id = request.POST.get('list_id')
        movie = get_object_or_404(Movie, id=movie_id)
        user_list = get_object_or_404(UserList, id=list_id, user=request.user)

        try:
            UserListMovie.objects.get_or_create(
                user_list=user_list,
                movie=movie
            )
            return HttpResponse('<div class="alert alert-success">Фильм добавлен в список!</div>')
        except Exception as e:
            return HttpResponse(f'<div class="alert alert-danger">Ошибка: {str(e)}</div>', status=400)

    return HttpResponse(status=405)


@login_required
def remove_from_list(request):
    """Удалить фильм из списка (HTMX)"""
    if request.method == 'POST':
        movie_id = request.POST.get('movie_id')
        list_id = request.POST.get('list_id')

        movie = get_object_or_404(Movie, id=movie_id)
        user_list = get_object_or_404(UserList, id=list_id, user=request.user)

        try:
            UserListMovie.objects.filter(
                user_list=user_list,
                movie=movie
            ).delete()

            # Возвращаем пустой ответ - элемент будет удален из DOM
            return HttpResponse('')
        except Exception as e:
            return HttpResponse(f'<div class="alert alert-danger">Ошибка: {str(e)}</div>', status=400)

    return HttpResponse(status=405)


@login_required
def toggle_list_privacy(request):
    """Переключить приватность списка (HTMX)"""
    if request.method == 'POST':
        list_id = request.POST.get('list_id')
        user_list = get_object_or_404(UserList, id=list_id, user=request.user)

        try:
            user_list.is_public = not user_list.is_public
            user_list.save()

            badge_class = 'bg-success' if user_list.is_public else 'bg-secondary'
            badge_text = 'Публичный' if user_list.is_public else 'Приватный'

            return HttpResponse(f'<span class="badge {badge_class}">{badge_text}</span>')
        except Exception as e:
            return HttpResponse(f'<div class="alert alert-danger">Ошибка: {str(e)}</div>', status=400)

    return HttpResponse(status=405)

