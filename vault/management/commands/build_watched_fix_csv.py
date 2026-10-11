import csv
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from slugify import slugify

CSV_FIELDS = [
    'csv_title',
    'csv_original_title',
    'csv_year',
    'watched_at',
    'title_slug',
    'original_title_slug',
]


def parse_int(value: str | None) -> int | None:
    if value is None:
        return None
    value = str(value).strip()
    if '-' in value:
        value = value.split('-', 1)[0]
    cleaned = ''.join(ch for ch in value if ch.isdigit())
    return int(cleaned) if cleaned else None


def parse_date(value: str | None):
    if not value or not str(value).strip():
        return None
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d', '%d.%m.%Y', '%Y/%m/%d'):
        try:
            return datetime.strptime(str(value).strip(), fmt).date()
        except ValueError:
            continue
    return None


class Command(BaseCommand):
    help = (
        'Строит CSV-файл «ремонта» для фильмов, у которых в Kinorium был статус '
        '"Просмотрено" без оценки.\n'
        'Читает старые выгрузки (backup_76444_movie_list.csv + backup_76444_votes.csv) '
        'и выписывает только данные, нужные для починки статусов.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--movie-list', type=str, default=None,
                            help='Путь к backup_76444_movie_list.csv (по умолчанию vault/current_csv/)')
        parser.add_argument('--votes', type=str, default=None,
                            help='Путь к backup_76444_votes.csv (по умолчанию vault/current_csv/)')
        parser.add_argument('--output', type=str, default=None,
                            help='Куда писать ремонтный CSV (по умолчанию vault/current_csv/watched_fix.csv)')

    @staticmethod
    def _iter_csv(path: Path):
        if not path.exists():
            raise CommandError(f"Файл не найден: {path}")
        with path.open(encoding='utf-16') as fh:
            return list(csv.DictReader(fh, delimiter='\t'))

    def handle(self, *args, **options):
        csv_dir = Path(settings.BASE_DIR) / 'vault' / 'current_csv'
        movie_list_path = Path(options['movie_list']) if options['movie_list'] else csv_dir / 'backup_76444_movie_list.csv'
        votes_path = Path(options['votes']) if options['votes'] else csv_dir / 'backup_76444_votes.csv'
        output_path = Path(options['output']) if options['output'] else csv_dir / 'watched_fix.csv'

        movie_rows = self._iter_csv(movie_list_path)
        votes_rows = self._iter_csv(votes_path)

        # Строки movie_list, где фильм просмотрен, но оценки нет.
        victim_rows = [
            r for r in movie_rows
            if (r.get('Status') or '').strip() == 'Просмотрено'
            and not (r.get('My rating') or '').strip()
        ]

        # Реальные даты просмотра лежат в votes.csv (рейтинг там пустой).
        # Берём самую раннюю дату по каждому фильму.
        vote_dates: dict[tuple, datetime.date] = {}
        for v in votes_rows:
            if not (v.get('Date') or '').strip():
                continue
            key = ((v.get('Title') or '').strip(), parse_int(v.get('Year')))
            date_val = parse_date(v.get('Date'))
            if date_val is None:
                continue
            if vote_dates.get(key) is None or date_val < vote_dates[key]:
                vote_dates[key] = date_val

        # Один фильм может лежать в нескольких списках -> несколько строк.
        # Уникализируем по (Title, Year).
        unique: dict[tuple, dict] = {}
        for r in victim_rows:
            key = ((r.get('Title') or '').strip(), parse_int(r.get('Year')))
            unique.setdefault(key, r)

        with output_path.open('w', encoding='utf-8-sig', newline='\n') as fh:
            writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS, lineterminator='\n')
            writer.writeheader()
            for r in unique.values():
                title = (r.get('Title') or '').strip()
                original_title = (r.get('Original Title') or '').strip()
                year = parse_int(r.get('Year'))
                watched_at = vote_dates.get((title, year))
                writer.writerow({
                    'csv_title': title,
                    'csv_original_title': original_title,
                    'csv_year': year if year is not None else '',
                    'watched_at': watched_at.isoformat() if watched_at else '',
                    'title_slug': slugify(title) if title else '',
                    'original_title_slug': slugify(original_title) if original_title else '',
                })

        no_date = sum(1 for r in unique.values() if vote_dates.get(((r.get('Title') or '').strip(), parse_int(r.get('Year')))) is None)

        self.stdout.write(self.style.SUCCESS('Ремонтный CSV построен.'))
        self.stdout.write(f"  Строк movie_list с «Просмотрено» без оценки: {len(victim_rows)}")
        self.stdout.write(f"  Уникальных фильмов: {len(unique)}")
        self.stdout.write(f"  Без даты просмотра (в votes.csv не нашлось): {no_date}")
        self.stdout.write(f"  Файл: {output_path}")