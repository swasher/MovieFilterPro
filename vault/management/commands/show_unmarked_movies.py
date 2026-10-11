import csv
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError

from vault.models import Movie, UserMovie


class Command(BaseCommand):
    help = (
        'Показывает фильмы из БД, у которых нет ничего: '
        'либо нет UserMovie вовсе, либо watch_status и rating пустые.\n'
        'Нужна для оценки масштаба проблемы (все похожие «дыры», '
        'а не только подтверждённые жертвы бага импорта).'
    )

    def add_arguments(self, parser):
        parser.add_argument('--user-id', type=int, default=None,
                            help='ID пользователя, чьи статусы проверяем '
                                 '(по умолчанию — первый/единственный пользователь из БД)')
        parser.add_argument('--summary', action='store_true',
                            help='Только итоговые счётчики, без списка фильмов')
        parser.add_argument('--repair-csv', type=str, default=None,
                            help='Путь к ремонтному CSV. По умолчанию ищется vault/current_csv/watched_fix.csv '
                                 '(если есть — фильмы из него помечаются как «покрытые ремонтом»)')

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
    def _read_repair_keys(path: Path) -> set[tuple] | None:
        if path is None or not path.exists():
            return None
        with path.open(encoding='utf-8-sig') as fh:
            rows = list(csv.DictReader(fh))
        keys = set()
        for r in rows:
            title = (r.get('csv_title') or '').strip()
            year_raw = (r.get('csv_year') or '').strip()
            year = int(year_raw) if year_raw else None
            keys.add((title, year))
        return keys

    def handle(self, *args, **options):
        user = self._resolve_user(options['user_id'])

        repair_csv_path = options['repair_csv']
        if repair_csv_path:
            repair_csv_path = Path(repair_csv_path)
        else:
            repair_csv_path = Path(settings.BASE_DIR) / 'vault' / 'current_csv' / 'watched_fix.csv'
        repair_keys = self._read_repair_keys(repair_csv_path)

        without_um = (
            Movie.objects.exclude(user_movies__user=user)
            .order_by('-year', 'title')
        )
        empty_um_movies = (
            Movie.objects.filter(
                user_movies__user=user,
                user_movies__watch_status__isnull=True,
                user_movies__rating__isnull=True,
            )
            .order_by('-year', 'title')
        )

        rows = []
        for m in without_um:
            rows.append((m, None))
        for m in empty_um_movies:
            rows.append((m, UserMovie.objects.get(user=user, movie=m)))

        covered = 0
        fav_only = 0
        note_only = 0

        self.stdout.write(f'Пользователь: id={user.pk} ({user.username})')
        self.stdout.write(
            f'Фильмов без «ничего»: {len(rows)}  '
            f'(совсем без UserMovie: {without_um.count()}, '
            f'с пустым UserMovie: {empty_um_movies.count()})'
        )
        if repair_keys is None:
            self.stdout.write('Ремонтный CSV не найден — отметки «покрыто ремонтом» не будет.')
        else:
            self.stdout.write(f'Ремонтный CSV: {repair_csv_path}')
        self.stdout.write('')

        if not options['summary']:
            for m, um in rows:
                in_repair = bool(repair_keys is not None and (m.title, m.year) in repair_keys)
                marker = '| в ремонте' if in_repair else ''
                if um is None:
                    self.stdout.write(f'[нет UserMovie] {m.title} ({m.year or "?"}) | {m.original_title or ""} {marker}')
                else:
                    extra = []
                    if um.is_favorite:
                        extra.append('избранный')
                    if (um.note or '').strip():
                        extra.append('заметка')
                    suffix = f' | {", ".join(extra)}' if extra else ''
                    self.stdout.write(
                        f'[пустой UserMovie: статуса и оценки нет] {m.title} ({m.year or "?"}) | '
                        f'{m.original_title or ""}{suffix} {marker}'
                    )
                if in_repair:
                    covered += 1
                if um is not None and um.is_favorite:
                    fav_only += 1
                if um is not None and (um.note or '').strip():
                    note_only += 1
        elif repair_keys is not None:
            covered = sum(1 for m, _ in rows if (m.title, m.year) in repair_keys)
            fav_only = sum(1 for _, um in rows if um is not None and um.is_favorite)
            note_only = sum(1 for _, um in rows if um is not None and (um.note or '').strip())

        self.stdout.write('')
        self.stdout.write(f"Итого: фильмов без «ничего» — {len(rows)}")
        if repair_keys is not None:
            self.stdout.write(f"  из них покрыты ремонтным CSV: {covered}")
        self.stdout.write(f"  в том числе с избранным: {fav_only}, с заметкой: {note_only}")