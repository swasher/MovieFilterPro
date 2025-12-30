from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.urls import reverse_lazy, reverse
from django.http import HttpResponse, JsonResponse
from django.db.models import Q, Avg, Count
from django.contrib import messages
from django.core.paginator import Paginator

from .models import (
    Movie, Person, Genre, UserList, UserListMovie,
    Rating, Review, MoviePerson
)
from .services.movie_status_service import MovieStatusService


class MovieListView(ListView):
    """Список всех фильмов"""
    model = Movie
    template_name = 'vault/movie_list.html'
    context_object_name = 'movies'
    paginate_by = 20

    def get_queryset(self):
        queryset = Movie.objects.filter(status='released').prefetch_related('genres', 'countries')

        # Сортировка
        order = self.request.GET.get('order', '-year')
        queryset = queryset.order_by(order)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['genres'] = Genre.objects.all()
        context['selected_genre'] = None
        return context


class MovieByGenreView(ListView):
    """Фильмы по жанру"""
    model = Movie
    template_name = 'vault/movie_list.html'
    context_object_name = 'movies'
    paginate_by = 20

    def get_queryset(self):
        self.genre = get_object_or_404(Genre, slug=self.kwargs['slug'])
        queryset = Movie.objects.filter(
            genres=self.genre,
            status='released'
        ).prefetch_related('genres', 'countries')

        order = self.request.GET.get('order', '-year')
        queryset = queryset.order_by(order)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['genres'] = Genre.objects.all()
        context['selected_genre'] = self.genre
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
        else:
            context['movie_status'] = {
                'in_watched': False,
                'in_will_watch': False,
                'in_wont_watch': False,
                'in_favorites': False,
                'rating': None,
            }
            context['user_rating'] = None

        # Отзывы
        context['reviews'] = movie.reviews.select_related('user').prefetch_related('likes')[:5]

        return context


class SearchView(ListView):
    """Поиск фильмов"""
    model = Movie
    template_name = 'vault/movie_list.html'
    context_object_name = 'movies'
    paginate_by = 20

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

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['genres'] = Genre.objects.all()
        context['search_query'] = self.request.GET.get('q', '')
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
        return UserList.objects.filter(
            user=self.request.user
        ).prefetch_related('list_movies').order_by('order', '-updated_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Разделяем системные и пользовательские списки
        all_lists = self.get_queryset()
        context['system_lists'] = all_lists.filter(is_system=True)
        context['custom_lists'] = all_lists.filter(is_system=False)

        return context


class ListDetailView(LoginRequiredMixin, DetailView):
    """Детальная страница списка"""
    model = UserList
    template_name = 'vault/list_detail.html'
    context_object_name = 'user_list'

    def get_queryset(self):
        # Пользователь может видеть только свои списки (или публичные - добавить позже)
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

        return context


class ListCreateView(LoginRequiredMixin, CreateView):
    """Создание нового списка"""
    model = UserList
    template_name = 'vault/list_create.html'
    fields = ['name', 'description', 'is_public']

    def form_valid(self, form):
        form.instance.user = self.request.user
        form.instance.list_type = 'custom'
        form.instance.is_system = False
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
        # Только свои списки и не системные
        return UserList.objects.filter(user=self.request.user, is_system=False)

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
        # Только свои списки и не системные
        return UserList.objects.filter(user=self.request.user, is_system=False)

    def delete(self, request, *args, **kwargs):
        messages.success(request, 'Список успешно удален!')
        return super().delete(request, *args, **kwargs)


class CreateReviewView(LoginRequiredMixin, CreateView):
    """Создание отзыва"""
    model = Review
    fields = ['title', 'text', 'review_type']

    def form_valid(self, form):
        movie = get_object_or_404(Movie, slug=self.kwargs['slug'])
        form.instance.user = self.request.user
        form.instance.movie = movie
        messages.success(self.request, 'Отзыв успешно опубликован!')
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('vault:movie_detail', kwargs={'slug': self.kwargs['slug']})


# ============== HTMX Views ==============

@login_required
def toggle_movie_status(request):
    """Переключить статус фильма (HTMX)"""
    if request.method == 'POST':
        movie_id = request.POST.get('movie_id')
        list_type = request.POST.get('list_type')

        movie = get_object_or_404(Movie, id=movie_id)

        try:
            is_added = MovieStatusService.toggle_list(
                request.user, movie, list_type
            )

            # Возвращаем обновленную кнопку
            button_class = 'btn-primary' if list_type == 'will_watch' else \
                'btn-danger' if list_type == 'favorites' else \
                    'btn-success' if list_type == 'watched' else 'btn-secondary'

            icon_name = 'bookmark' if list_type == 'will_watch' else \
                'heart' if list_type == 'favorites' else \
                    'check-circle' if list_type == 'watched' else 'x-circle'

            if is_added:
                icon_name += '-fill'
                btn_class = button_class
            else:
                btn_class = button_class.replace('btn-', 'btn-outline-')

            label = 'Буду смотреть' if list_type == 'will_watch' else \
                'Избранное' if list_type == 'favorites' else \
                    'Просмотрено' if list_type == 'watched' else 'Не буду смотреть'

            html = f'''
            <button type="button" class="btn {btn_class}" 
                    hx-post="{reverse('vault:htmx_toggle_status')}"
                    hx-vals='{{"movie_id": "{movie_id}", "list_type": "{list_type}"}}'
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
        rating_value = int(request.POST.get('rating'))

        movie = get_object_or_404(Movie, id=movie_id)

        try:
            MovieStatusService.rate_movie(request.user, movie, rating_value)

            # Возвращаем обновленные кнопки оценок
            html = '<div class="btn-group" role="group">'
            for i in range(1, 11):
                btn_class = 'btn-warning' if i == rating_value else 'btn-outline-warning'
                html += f'''
                <button type="button" class="btn btn-sm {btn_class}" 
                        hx-post="{reverse('vault:htmx_rate_movie')}"
                        hx-vals='{{"movie_id": "{movie_id}", "rating": "{i}"}}'
                        hx-swap="outerHTML"
                        hx-target="closest .btn-group">
                    {i}
                </button>
                '''
            html += '</div>'
            html += f'''
            <button type="button" class="btn btn-sm btn-outline-danger ms-2" 
                    hx-post="{reverse('vault:htmx_remove_rating')}"
                    hx-vals='{{"movie_id": "{movie_id}"}}'
                    hx-target="closest div">
                <i class="bi bi-x"></i> Удалить оценку
            </button>
            '''

            return HttpResponse(html)
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

            # Возвращаем кнопки без выбранной оценки
            html = '<div>'
            html += '<label class="form-label">Ваша оценка:</label>'
            html += '<div class="btn-group" role="group">'
            for i in range(1, 11):
                html += f'''
                <button type="button" class="btn btn-sm btn-outline-warning" 
                        hx-post="{reverse('vault:htmx_rate_movie')}"
                        hx-vals='{{"movie_id": "{movie_id}", "rating": "{i}"}}'
                        hx-swap="outerHTML"
                        hx-target="closest div">
                    {i}
                </button>
                '''
            html += '</div></div>'

            return HttpResponse(html)
        except Exception as e:
            return HttpResponse(f'<div class="alert alert-danger">Ошибка: {str(e)}</div>', status=400)

    return HttpResponse(status=405)


@login_required
def add_to_list(request):
    """Добавить фильм в список (HTMX)"""
    if request.method == 'POST':
        movie_id = request.POST.get('movie_id')
        list_id = request.POST.get('list_id')
        note = request.POST.get('note', '')

        movie = get_object_or_404(Movie, id=movie_id)
        user_list = get_object_or_404(UserList, id=list_id, user=request.user)

        try:
            UserListMovie.objects.get_or_create(
                user_list=user_list,
                movie=movie,
                defaults={'note': note}
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
        user_list = get_object_or_404(UserList, id=list_id, user=request.user, is_system=False)

        try:
            user_list.is_public = not user_list.is_public
            user_list.save()

            badge_class = 'bg-success' if user_list.is_public else 'bg-secondary'
            badge_text = 'Публичный' if user_list.is_public else 'Приватный'

            return HttpResponse(f'<span class="badge {badge_class}">{badge_text}</span>')
        except Exception as e:
            return HttpResponse(f'<div class="alert alert-danger">Ошибка: {str(e)}</div>', status=400)

    return HttpResponse(status=405)


@login_required
def like_review(request, pk):
    """Лайкнуть отзыв (HTMX)"""
    if request.method == 'POST':
        review = get_object_or_404(Review, pk=pk)

        if request.user in review.likes.all():
            review.likes.remove(request.user)
            liked = False
        else:
            review.likes.add(request.user)
            liked = True

        btn_class = 'btn-primary' if liked else 'btn-outline-secondary'

        html = f'''
        <button class="btn btn-sm {btn_class}" 
                hx-post="{reverse('vault:htmx_like_review', kwargs={'pk': pk})}"
                hx-swap="outerHTML">
            <i class="bi bi-hand-thumbs-up"></i> {review.likes_count()}
        </button>
        '''

        return HttpResponse(html)

    return HttpResponse(status=405)
