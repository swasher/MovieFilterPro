"""Сопоставление актеров ленты RSS с избранными персонами Vault.

Источники данных живут в разных приложениях и не связаны по ключу:
- MovieRSS.actors (moviefilter) — строка с именами актеров в том виде,
  как их отдал Kinozal (обычно русские имена, разделенные запятой).
- FavoritePerson -> vault.Person (vault) — персона с русским `name` и
  английским `original_name`.

Написание одного и того же человека в двух источниках может отличаться
("Дайан Лэйн" vs "Дайан Лейн", "Роберт Дауни мл." vs "Дауни младший Роберт").
Поэтому совпадение ищется в два шага:
1. Точный матч по нормализованному имени — быстро и без ложных срабатываний.
2. Если точного нет — нечеткое сравнение через rapidfuzz (token_sort_ratio
   устойчив к перестановке слов и опечаткам).
"""
import re

from rapidfuzz import fuzz, process

# 80% с токеном-сортировкой хорошо отделяет опечатки/варианты написания
# от случайных однофамильцев. 30% (для отладки) матчит почти все подряд —
# не использовать в проде.
DEFAULT_SCORE_CUTOFF = 80.0

_INITIALS_RE = re.compile(r"\b[а-яёa-z]{1,3}\.\s*")
_BRACKETS_RE = re.compile(r"\(.*?\)")
_JUNIOR_RE = re.compile(r"\b(мл|младший)\b\.?")
_SENIOR_RE = re.compile(r"\b(ст|старший)\b\.?")
_NON_WORD_RE = re.compile(r"[^\w\s]")


def normalize_actor_name(name: str) -> str:
    """Приводит имя к единому виду для сравнения."""
    if not name:
        return ""

    name = name.lower().replace("ё", "е")

    # Пометки вида "(дубляж)" / "(эпизод)" к имени не относятся
    name = _BRACKETS_RE.sub("", name)

    # "мл." / "младший" и "ст." / "старший" -> компактная форма
    name = _JUNIOR_RE.sub("мл", name)
    name = _SENIOR_RE.sub("ст", name)

    # Инициалы ("Дж. Депп", "Сэмюэл Л. Джексон") дают шум при сравнении
    name = _INITIALS_RE.sub("", name)

    # "Дауни-младший" -> "Дауни младший"
    name = _NON_WORD_RE.sub(" ", name)

    return " ".join(name.split())


class FavoriteActorMatcher:
    """Один экземпляр на запрос: загружает избранных персон, затем матчит актеров."""

    def __init__(
        self,
        favorite_names: list[str],
        score_cutoff: float = DEFAULT_SCORE_CUTOFF,
    ):
        # Точный матч по нормализованному имени обрабатываем отдельным set'ом,
        # чтобы не гонять fuzzy там, где имена совпадают дословно.
        normalized: set[str] = set()
        for raw in favorite_names:
            clean = normalize_actor_name(raw)
            if clean:
                normalized.add(clean)
        self._exact_names = normalized
        self._fuzzy_candidates = list(normalized)
        self._score_cutoff = score_cutoff

    def is_favorite(self, actor_name: str) -> bool:
        clean = normalize_actor_name(actor_name)
        if not clean:
            return False

        if clean in self._exact_names:
            return True

        if not self._fuzzy_candidates:
            return False

        match = process.extractOne(
            clean,
            self._fuzzy_candidates,
            scorer=fuzz.token_sort_ratio,
            score_cutoff=self._score_cutoff,
        )
        return match is not None

    def favorite_actors(self, actors: list[str]) -> list[str]:
        """Возвращает имена из списка, совпавшие с избранными."""
        return [actor for actor in actors if self.is_favorite(actor)]