import csv
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from vault.models import Movie, UserMovie


def parse_date(value: str | None):
    value = (value or '').strip()
    if not value:
        return None
    for fmt in ('%Y-%m-%d', '%d.%m.%Y', '%Y/%m/%d'):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


class Command(BaseCommand):
    help = (
        'Применяет ремонтный CSV (из build_watched_fix_csv) к БД: '
        'фильмам со статусом «Просмотрено» в Kinorium без оценки '
        'проставляет watch_status=WATCHED и даты просмотра.\n'
        'По умолчанию работает в режиме dry-run; реальные изменения — только с --apply.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--input', type=str, default=None,
                            help='Путь к ремонтному CSV (по умолчанию vault/current_csv/watched_fix.csv)')
        parser.add_argument('--user-id', type=int, default=None,
                            help='ID пользователя, которому проставляются статусы '
                                 '(по умолчанию — первый/единственный пользователь из БД)')
        parser.add_argument('--apply', action='store_true',
                            help='Реально сохранять изменения (без флага — только отчёт)')

    def _resolve_user(self, user_id):
        if user_id is not None:
            user = User.objects.filter(pk=user_id).first()
            if user is None:
                raise CommandError(f'Пользователь с id={user_id} не найден.')
            return user
        users = list(User.objects.all()[:2])
        if not users:
            raise CommandError('В БД нет ни одного пользователя. Укажите --user-id.')
        if len(users) > 1:
            self.stdout.write(self.style.WARNING(
                f'В БД несколько пользователей, беру первого: id={users[0].pk} ({users[0].username}). '
                'Уточните через --user-id, если нужно.'
            ))
        return users[0]

    @staticmethod
    def _read_rows(path: Path):
        with path.open(encoding='utf-8-sig') as fh:
            return list(csv.DictReader(fh))

    @staticmethod
    def _candidate_steps(title, original_title, year, title_slug, original_title_slug):
        """Каскад шагов поиска фильма в БД. Каждый шаг — (метка, QuerySet)."""
        if title and year is not None:
            yield 'title+year', Movie.objects.filter(title=title, year=year)
        if original_title and year is not None:
            yield 'original_title+year', Movie.objects.filter(original_title=original_title, year=year)
        if title and year is not None:
            yield 'title+year±1', Movie.objects.filter(title=title, year__in=[year - 1, year + 1])
        if original_title and year is not None:
            yield 'original_title+year±1', Movie.objects.filter(original_title=original_title, year__in=[year - 1, year + 1])
        slugs = [s for s in (title_slug, original_title_slug) if s]
        if slugs:
            yield 'slug', Movie.objects.filter(slug__in=slugs)
        if title:
            yield 'title (без года)', Movie.objects.filter(title=title)

    @staticmethod
    def _find_movie(row: dict):
        title = (row.get('csv_title') or '').strip() or None
        original_title = (row.get('csv_original_title') or '').strip() or None
        year_raw = (row.get('csv_year') or '').strip()
        year = int(year_raw) if year_raw else None
        title_slug = (row.get('title_slug') or '').strip() or None
        original_title_slug = (row.get('original_title_slug') or '').strip() or None

        for label, qs in Command._candidate_steps(title, original_title, year, title_slug, original_title_slug):
            matches = list(qs[:2])
            if len(matches) == 1:
                return matches[0], label
        return None, None

    @transaction.atomic
    def handle(self, *args, **options):
        csv_dir = Path(settings.BASE_DIR) / 'vault' / 'current_csv'
        input_path = Path(options['input']) if options['input'] else csv_dir / 'watched_fix.csv'
        if not input_path.exists():
            raise CommandError(f'Файл не найден: {input_path}')

        user = self._resolve_user(options['user_id'])

        do_apply = options['apply']
        mode = 'APPLY' if do_apply else 'DRY-RUN (ничего не записывается)'

        rows = self._read_rows(input_path)
        stats = {
            'total': len(rows),
            'applied': 0,
            'already_watched': 0,
            'conflict': 0,
            'not_found': 0,
            'with_tmdb': 0,
        }
        unresolved = []

        self.stdout.write(f'Режим: {mode}. Строк в CSV: {len(rows)}. Пользователь: id={user.pk}.')
        self.stdout.write('')

        for row in rows:
            watched_at = parse_date(row.get('watched_at'))
            title = (row.get('csv_title') or '').strip()
            year = (row.get('csv_year') or '').strip()

            movie, label = self._find_movie(row)
            if movie is None:
                stats['not_found'] += 1
                unresolved.append((title, year, 'не найден в БД'))
                self.stdout.write(self.style.WARNING(f'[не найден] {title} ({year})'))
                continue

            user_movie = UserMovie.objects.filter(user=user, movie=movie).first()

            if user_movie and user_movie.watch_status == UserMovie.WatchStatus.WATCHED:
                stats['already_watched'] += 1
                self.stdout.write(f'[уже просмотрен] {title} ({year}) -> {movie.title} ({movie.year})')
                continue

            if user_movie and user_movie.watch_status in (
                UserMovie.WatchStatus.PLAN,
                UserMovie.WatchStatus.SKIP,
            ):
                stats['conflict'] += 1
                unresolved.append((title, year, f'в БД стоит другой статус: {user_movie.watch_status}'))
                self.stdout.write(
                    self.style.ERROR(
                        f'[конфликт] {title} ({year}) -> {movie.title} ({movie.year}): '
                        f'в БД уже стоит статус {user_movie.get_watch_status_display()}'
                    )
                )
                continue

            details = ['создать UserMovie' if user_movie is None else 'обновить watch_status']
            if watched_at:
                details.append(f'watched_at={watched_at}')

            if do_apply:
                if user_movie is None:
                    UserMovie.objects.create(
                        user=user,
                        movie=movie,
                        watch_status=UserMovie.WatchStatus.WATCHED,
                        watched_at=watched_at,
                        status_at=watched_at,
                    )
                else:
                    update_fields = ['watch_status', 'updated_at']
                    user_movie.watch_status = UserMovie.WatchStatus.WATCHED
                    if watched_at is not None:
                        if user_movie.watched_at is None:
                            user_movie.watched_at = watched_at
                            update_fields.append('watched_at')
                        if user_movie.status_at is None:
                            user_movie.status_at = watched_at
                            update_fields.append('status_at')
                    user_movie.save(update_fields=update_fields)

            stats['applied'] += 1
            if movie.tmdb_id:
                stats['with_tmdb'] += 1
            self.stdout.write(
                f'[{label}] {title} ({year}) -> {movie.title} ({movie.year}): ' + ', '.join(details)
            )

        self.stdout.write('')
        self.stdout.write(
            f"Итого: строк={stats['total']}, к исправлению={stats['applied']}, "
            f"уже просмотрено={stats['already_watched']}, конфликтов={stats['conflict']}, "
            f"не найдено={stats['not_found']}"
        )
        self.stdout.write(
            f'  Из исправляемых: с tmdb_id={stats["with_tmdb"]} '
            f'(автоматически уйдут в TMDB writeback), '
            f'без tmdb_id={stats["applied"] - stats["with_tmdb"]} (только локальный статус)'
        )

        if unresolved:
            self.stdout.write('')
            self.stdout.write(self.style.WARNING('Требуют ручного разбора:'))
            for title, year, reason in unresolved:
                self.stdout.write(f'  - {title} ({year}): {reason}')