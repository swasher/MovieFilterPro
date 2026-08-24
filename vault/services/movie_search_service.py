"""
Гибридный поиск по фильмам (Vault).

Адаптация ТЗ из задания под реальную модель vault.Movie:
- title            -> Movie.title
- original_title   -> Movie.original_title
- plot/description -> Movie.description

Режимы:
- search_plot=False (Search in Title): только по названию через icontains, без стемминга.
- search_plot=True  (Search in Plot) : title/original_title/description через icontains + FTS (russian, стемминг, веса A/B), ранжирование SearchRank.
"""

from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector
from django.db import connection
from django.db.models import Q, QuerySet


# ------------------------------------ #
#          APPLICATION LAYER           #
# ------------------------------------ #


class MovieSearchService:
    """Сервис гибридного поиска по Movie."""

    @staticmethod
    def _is_postgres() -> bool:
        return connection.vendor == "postgresql"

    @classmethod
    def apply_search(cls, queryset: QuerySet, query: str | None, search_plot: bool) -> QuerySet:
        """
        Применяет гибридный фильтр к queryset.
        - query: строка поиска (trim внутри)
        - search_plot: False = только title/original_title icontains; True = + FTS по description
        Возвращает queryset с применённым фильтром и, в расширенном режиме, с аннотациями search/rank + сортировкой по rank.
        Если query пустой — возвращает исходный queryset без изменений.
        """
        raw = (query or "").strip()
        if not raw:
            return queryset

        # Базовое условие по названию — без стемминга, сохраняет точные формы / короткие слова / бренды
        title_condition = Q(title__icontains=raw) | Q(original_title__icontains=raw)

        # Режим 1: только название
        if not search_plot:
            return queryset.filter(title_condition)

        # Режим 2: название + сюжет со стеммингом
        # Fallback для не-postgres (tests/sqlite): оставляем icontains по description
        if not cls._is_postgres():
            return queryset.filter(title_condition | Q(description__icontains=raw))

        # Защита от тяжелых OR на коротких паттернах:
        # - pg_trgm GIN эффективен от 3 символов, 1-2 символа дают Seq Scan и низкую селективность
        # - plainto_tsquery('russian','а') -> '' (стоп-слово), тогда @@ '' false и ts_rank бессмысленен
        # Для len<2 оставляем только title_condition без дорогого FTS+rank.
        if len(raw) < 2:
            return queryset.filter(title_condition)

        # Postgres FTS: веса A для заголовков, B для описания — config единый russian!
        # Важно: у всех полей одинаковый config, иначе CombinedSearchVector смешает разные словари
        # (default_text_search_config -> simple/english) и SearchQuery(config='russian') не сматчится.
        vector = (
            SearchVector("title", weight="A", config="russian")
            + SearchVector("original_title", weight="A", config="russian")
            + SearchVector("description", weight="B", config="russian")
        )
        # plain — разбивает на лексемы через &, применяет стемминг russian
        ts_query = SearchQuery(raw, config="russian")

        # Если ts_query пустой (стоп-слова вроде 'в','и','на' после стемминга), не аннотируем rank
        # Проверка через plainto_tsquery, чтобы не делать лишний ts_rank по ''::tsquery
        try:
            with connection.cursor() as cur:
                cur.execute("SELECT plainto_tsquery('russian', %s)::text", [raw])
                ts_text = (cur.fetchone() or [""])[0]
                if not ts_text or ts_text.strip() == "":
                    return queryset.filter(title_condition)
        except Exception:
            pass  # при ошибке — fallback к обычному FTS

        # Аннотируем и фильтруем объединённым условием; ранжируем — заголовок выше сюжета благодаря весам
        # На Postgres GIN индексы: pg_trgm для icontains и gin для tsvector ускоряют оба условия.
        # Сортировка по rank выполняется вызывающим кодом (vault/api.py) — чтобы корректно
        # сочетаться с пользовательской сортировкой order (как вторичный ключ).
        return queryset.annotate(
            search=vector,
            rank=SearchRank(vector, ts_query),
        ).filter(title_condition | Q(search=ts_query))

    @classmethod
    def get_filtered_queryset(cls, queryset: QuerySet, query: str | None, search_plot: bool) -> QuerySet:
        """Alias для совместимости с возможной внешней сигнатурой из ТЗ."""
        return cls.apply_search(queryset, query, search_plot)


# ------------------------------------ #
#            DOMAIN LAYER              #
# ------------------------------------ #

# Чистая функция из ТЗ (адаптированная под vault.Movie) — для импорта в других местах если нужен отдельный QuerySet.
def get_filtered_movies(queryset: QuerySet, user_input: str, include_plot: bool) -> QuerySet:
    """
    Иллюстративная функция из ТЗ, адаптированная под vault.Movie.
    Использует MovieSearchService внутри.
    """
    return MovieSearchService.apply_search(queryset, user_input, include_plot)
