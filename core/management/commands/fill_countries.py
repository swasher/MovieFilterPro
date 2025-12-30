from django.core.management.base import BaseCommand
from core.models import Country
from babel import Locale


class Command(BaseCommand):
    help = 'Очищает и заново заполняет таблицу Country'

    def handle(self, *args, **options):
        # 1. Списки исправлений
        # Переименовываем длинные названия в общепринятые для кино
        RENAME_MAP = {
            'US': 'США',
            'GB': 'Великобритания',
            'KP': 'Северная Корея',
            'KR': 'Южная Корея',
            'AE': 'ОАЭ',
            'RU': 'Россия',  # Babel может вернуть "Российская Федерация"
        }

        # Исторические страны (которых нет в активном списке ISO 3166-1)
        # Коды для них можно придумать свои (обычно берут те, что были раньше)
        HISTORICAL_COUNTRIES = [
            ('SU', 'СССР'),
            ('CS', 'Чехословакия'),
            ('YU', 'Югославия'),
            ('DD', 'ГДР'),
        ]

        locale = Locale('ru')
        created_count = 0

        # 2. Обрабатываем современные страны из Babel
        for code, name in locale.territories.items():
            if len(code) == 2 and not code.isdigit():
                # Если код есть в списке переименований — берем наше название
                final_name = RENAME_MAP.get(code, name)

                Country.objects.get_or_create(
                    code=code,
                    defaults={'name': final_name}
                )
                created_count += 1

        # 3. Добавляем исторические страны
        for code, name in HISTORICAL_COUNTRIES:
            if not Country.objects.filter(code=code).exists():
                Country.objects.create(code=code, name=name)
                created_count += 1

        self.stdout.write(self.style.SUCCESS(f'Готово! Добавлено стран: {created_count}'))
