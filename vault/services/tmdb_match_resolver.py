from __future__ import annotations

from dataclasses import replace
import html
import logging
import re
from typing import TYPE_CHECKING

from vault.models import Movie
from web_logger import send_match_log


logger = logging.getLogger("vault.tmdb_sync")

if TYPE_CHECKING:
    from vault.services.tmdb_ai_matching_service import AICandidateChoice, AIPlotComparison
    from vault.services.tmdb_groq_matching_service import GroqChoice
    from vault.services.tmdb_movie_matching_service import TMDBCandidate, TMDBMatchingResult


# ------------------------------------ #
#          APPLICATION LAYER           #
# ------------------------------------ #


class TMDBMatchResolver:
    """Конвейер fuzzy-результат -> AI.

    Порядок стадий (дешевые первые, дорогие последние):
      1. eligibility (только needs_confirmation / needs_user_choice),
      2. pre-AI правила (_apply_pre_ai_rules: дословное совпадение описаний),
      3. стадия актёрских составов (_stage_cast_overlap: пересечение каста через локальный AI),
      4. GROQ-стадия (семантическое попарное сравнение сюжетов через облако),
      5. локальный AI-выбор лучшего из всей кучи,
      6. проверка уверенности выбора,
      7. независимая попарная проверка победителя по сюжетам,
      8. повышение до auto_match.

    Новые промежуточные правила между детерминированным алгоритмом и AI
    добавляются в _apply_pre_ai_rules и не трогают остальные стадии.
    """

    ELIGIBLE_STATUSES = frozenset({"needs_confirmation", "needs_user_choice"})

    # Дословное совпадение описаний: сайты копируют синопсисы друг у друга.
    # Короткие фразы слишком общие, поэтому требуем минимум значимого текста.
    LITERAL_MIN_CHARS = 50

    # Стадия актёрских составов: промоут только при уникальном победителе
    # с этим числом общих актёров. Локальный каст берём топ-10 по популярности.
    CAST_MIN_OVERLAP = 2
    CAST_TOP_LOCAL_NAMES = 10

    @classmethod
    def resolve_with_ai_if_confident(
        cls,
        movie: Movie,
        fuzzy_result: TMDBMatchingResult,
        *,
        auto_match_min_score: int = 90,
    ) -> TMDBMatchingResult:
        if not cls._is_eligible(fuzzy_result):
            return fuzzy_result

        early = cls._apply_pre_ai_rules(movie, fuzzy_result, auto_match_min_score=auto_match_min_score)
        if early is not None:
            return early

        cast_early = cls._stage_cast_overlap(movie, fuzzy_result, auto_match_min_score=auto_match_min_score)
        if cast_early is not None:
            return cast_early

        groq_early = cls._stage_groq_if_confident(movie, fuzzy_result, auto_match_min_score)
        if groq_early is not None:
            return groq_early

        choice = cls._stage_choose(movie, fuzzy_result.candidates)
        if not cls._stage_is_choice_confident(choice, fuzzy_result.candidates):
            return fuzzy_result

        assert choice is not None and choice.selected_candidate is not None
        comparison = cls._stage_verify_plot(movie, choice)
        if not cls._stage_is_verified(comparison):
            return fuzzy_result

        return cls._promote_to_auto_match(fuzzy_result, choice, comparison, auto_match_min_score)

    # ------------------------------------ #
    #            DOMAIN LAYER              #
    # ------------------------------------ #

    @classmethod
    def _is_eligible(cls, fuzzy_result: TMDBMatchingResult) -> bool:
        return fuzzy_result.status in cls.ELIGIBLE_STATUSES and bool(fuzzy_result.candidates)

    @classmethod
    def _apply_pre_ai_rules(
        cls,
        movie: Movie,
        fuzzy_result: TMDBMatchingResult,
        *,
        auto_match_min_score: int = 90,
    ) -> TMDBMatchingResult | None:
        """Правила между детерминированным скорингом и AI.

        Дословное совпадение описаний: синопсисы кочуют по сайтам как есть,
        поэтому точная копия сюжета — верный признак того же произведения.
        Возвращает готовый auto_match чтобы пропустить AI,
        или None чтобы идти дальше по конвейеру.
        """
        source = movie.description or ""
        if len(source.strip()) < cls.LITERAL_MIN_CHARS:
            return None
        hits = [
            candidate
            for candidate in fuzzy_result.candidates
            if cls._plots_match_literally(source, candidate.overview or "")
        ]
        if len(hits) != 1:
            return None
        winner = hits[0]
        logger.info(
            "TMDB_LITERAL_MATCH | movie_id=%s | tmdb_id=%s | candidates=%s",
            getattr(movie, "id", None),
            winner.tmdb_id,
            ",".join(str(candidate.tmdb_id) for candidate in fuzzy_result.candidates),
        )
        send_match_log(
            "literal_match",
            movie_id=getattr(movie, "id", None),
            tmdb_id=winner.tmdb_id,
        )
        return cls._promote_literal_match(fuzzy_result, winner, auto_match_min_score)

    @classmethod
    def _plots_match_literally(cls, source: str, overview: str) -> bool:
        """Дословно: только равенство нормализованных текстов.

        Вхождение одного текста в другой НЕ засчитывается: короткий синопсис
        может целиком входить в длинное описание совершенно другого фильма.
        Спорные пары «аннотация внутри пересказа» решает AI-стадия конвейера.
        """
        left = cls._normalize_plot(source)
        right = cls._normalize_plot(overview)
        if len(left) < cls.LITERAL_MIN_CHARS or len(right) < cls.LITERAL_MIN_CHARS:
            return False
        return left == right

    @staticmethod
    def _normalize_plot(value: str) -> str:
        text = html.unescape(value or "")
        text = re.sub(r"<[^>]+>", " ", text)
        text = text.lower().replace("ё", "е")
        text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
        text = re.sub(r"_", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    @classmethod
    def _promote_literal_match(
        cls,
        fuzzy_result: TMDBMatchingResult,
        winner: TMDBCandidate,
        auto_match_min_score: int,
    ) -> TMDBMatchingResult:
        from vault.services.tmdb_movie_matching_service import TMDBMatchingResult

        promoted = replace(
            winner,
            score=max(winner.score, auto_match_min_score),
            score_reasons=tuple(winner.score_reasons or ()) + ("plot_literal_match",),
        )
        candidates = tuple(
            promoted
            if candidate.tmdb_id == promoted.tmdb_id and candidate.media_type == promoted.media_type
            else candidate
            for candidate in fuzzy_result.candidates
        )
        return TMDBMatchingResult(
            status="auto_match",
            selected_candidate=promoted,
            candidates=candidates,
            message="Точное совпадение описаний — фильм тот же, AI не понадобился.",
        )

    @classmethod
    def _stage_cast_overlap(
        cls,
        movie: Movie,
        fuzzy_result: TMDBMatchingResult,
        auto_match_min_score: int,
    ) -> TMDBMatchingResult | None:
        """Стадия актёрских составов: уникальный кандидат с общим кастом >= CAST_MIN_OVERLAP.

        Работает без описаний (спасает source_plot_too_short) и при названиях-
        неоднозначностях: одно произведение почти наверняка делит актёров, разные —
        почти никогда. Сравнение имён через LLM (кириллица vs латиница).
        Только позитивный промоут: нулевое пересечение не демоутит кандидата —
        каст Kinorium бывает неполным для нишевых фильмов.
        """
        local_names = cls._local_actor_names(movie)
        if not local_names:
            return None

        from vault.services.tmdb_ai_matching_service import TMDBAIMatchingService

        winners: list[tuple] = []
        for candidate in fuzzy_result.candidates:
            comparison = TMDBAIMatchingService.compare_casts(local_names, list(candidate.cast_names or ()))
            send_match_log(
                "ai_cast",
                movie_id=getattr(movie, "id", None),
                tmdb_id=candidate.tmdb_id,
                overlap=comparison.overlap if comparison is not None else None,
            )
            if comparison is not None and comparison.overlap >= cls.CAST_MIN_OVERLAP:
                winners.append((candidate, comparison))

        if len(winners) != 1:
            return None
        winner, comparison = winners[0]
        return cls._promote_cast_match(fuzzy_result, winner, comparison, auto_match_min_score)

    @classmethod
    def _local_actor_names(cls, movie: Movie) -> list[str]:
        """Топ-N локальных актёров по популярности. Пусто для unsaved Movie (guard для тестов)."""
        if getattr(movie, "pk", None) is None:
            return []
        names: list[str] = []
        items = (
            movie.movie_persons.filter(role="actor")
            .select_related("person")
            .order_by("order", "id")[: cls.CAST_TOP_LOCAL_NAMES]
        )
        for item in items:
            value = (getattr(item.person, "name", "") or "").strip()
            if value and value not in names:
                names.append(value)
        return names

    @classmethod
    def _promote_cast_match(
        cls,
        fuzzy_result: TMDBMatchingResult,
        winner: TMDBCandidate,
        comparison,
        auto_match_min_score: int,
    ) -> TMDBMatchingResult:
        from vault.services.tmdb_movie_matching_service import TMDBMatchingResult

        promoted = replace(
            winner,
            score=max(winner.score, auto_match_min_score),
            score_reasons=tuple(winner.score_reasons or ()) + ("cast_match",),
        )
        candidates = tuple(
            promoted
            if candidate.tmdb_id == promoted.tmdb_id and candidate.media_type == promoted.media_type
            else candidate
            for candidate in fuzzy_result.candidates
        )
        pairs_text = "; ".join(comparison.matched_pairs) if comparison.matched_pairs else ""
        suffix = f" Пары: {pairs_text}." if pairs_text else ""
        return TMDBMatchingResult(
            status="auto_match",
            selected_candidate=promoted,
            candidates=candidates,
            message=(
                f"Совпадение актёрского состава подтвердило матч "
                f"(общих актёров: {comparison.overlap}).{suffix}"
            ),
        )

    @classmethod
    def _stage_groq_if_confident(
        cls,
        movie: Movie,
        fuzzy_result: TMDBMatchingResult,
        auto_match_min_score: int,
    ) -> TMDBMatchingResult | None:
        """GROQ-стадия: семантическое сравнение сюжетов, когда дословного нет.

        Возвращает готовый auto_match при одном явном победителе,
        иначе None — конвейер идет дальше к локальному AI.
        """
        from vault.services.tmdb_groq_matching_service import GroqChoice, TMDBGROQMatchingService

        choice: GroqChoice | None = TMDBGROQMatchingService.choose_confident(
            movie,
            fuzzy_result.candidates,
        )
        if not TMDBGROQMatchingService.is_auto_match(choice):
            return None
        assert choice is not None and choice.selected_candidate is not None
        return cls._promote_groq_match(fuzzy_result, choice, auto_match_min_score)

    @classmethod
    def _promote_groq_match(
        cls,
        fuzzy_result: TMDBMatchingResult,
        choice: GroqChoice,
        auto_match_min_score: int,
    ) -> TMDBMatchingResult:
        from vault.services.tmdb_movie_matching_service import TMDBMatchingResult

        selected = choice.selected_candidate
        assert selected is not None
        promoted = replace(
            selected,
            score=max(selected.score, auto_match_min_score),
            score_reasons=tuple(selected.score_reasons or ()) + ("groq_plot_match",),
        )
        candidates = tuple(
            promoted
            if candidate.tmdb_id == promoted.tmdb_id and candidate.media_type == promoted.media_type
            else candidate
            for candidate in fuzzy_result.candidates
        )
        reason = f" {choice.reason}" if choice.reason else ""
        return TMDBMatchingResult(
            status="auto_match",
            selected_candidate=promoted,
            candidates=candidates,
            message=f"GROQ подтвердил матч TMDB по описаниям (confidence={choice.confidence:.2f}).{reason}",
        )

    @classmethod
    def _stage_choose(
        cls,
        movie: Movie,
        candidates: tuple[TMDBCandidate, ...],
    ) -> AICandidateChoice | None:
        from vault.services.tmdb_ai_matching_service import TMDBAIMatchingService

        choice = TMDBAIMatchingService.choose_best_candidate(movie, candidates)
        if choice is not None:
            send_match_log(
                "ai_choose",
                movie_id=getattr(movie, "id", None),
                selected_tmdb_id=getattr(choice.selected_candidate, "tmdb_id", None),
                confidence=round(choice.confidence, 2),
            )
        return choice

    @classmethod
    def _stage_is_choice_confident(
        cls,
        choice: AICandidateChoice | None,
        candidates: tuple[TMDBCandidate, ...],
    ) -> bool:
        from vault.services.tmdb_ai_matching_service import TMDBAIMatchingService

        if choice is None or choice.selected_candidate is None:
            return False
        return TMDBAIMatchingService.is_auto_match(
            choice,
            deterministic_best=candidates[0] if candidates else None,
            deterministic_second=candidates[1] if len(candidates) > 1 else None,
        )

    @classmethod
    def _stage_verify_plot(cls, movie: Movie, choice: AICandidateChoice) -> AIPlotComparison | None:
        from vault.services.tmdb_ai_matching_service import TMDBAIMatchingService

        selected = choice.selected_candidate
        assert selected is not None
        comparison: AIPlotComparison | None = TMDBAIMatchingService.compare_plots(
            movie.description or "",
            selected.overview or "",
            title=movie.title or selected.title or "",
            original_title=movie.original_title or selected.original_title or "",
            year=movie.year or selected.year,
        )
        send_match_log(
            "ai_verify",
            movie_id=getattr(movie, "id", None),
            same_work=comparison.same_work if comparison is not None else None,
            confidence=round(comparison.confidence, 2) if comparison is not None else None,
        )
        return comparison

    @classmethod
    def _stage_is_verified(cls, comparison: AIPlotComparison | None) -> bool:
        from vault.services.tmdb_ai_matching_service import TMDBAIMatchingService

        return TMDBAIMatchingService.is_plot_verified(comparison)

    @classmethod
    def _promote_to_auto_match(
        cls,
        fuzzy_result: TMDBMatchingResult,
        choice: AICandidateChoice,
        comparison: AIPlotComparison | None,
        auto_match_min_score: int,
    ) -> TMDBMatchingResult:
        from vault.services.tmdb_movie_matching_service import TMDBMatchingResult

        selected = choice.selected_candidate
        assert selected is not None
        promoted = replace(
            selected,
            score=max(selected.score, auto_match_min_score),
            score_reasons=tuple(selected.score_reasons or ())
            + (
                "ai_plot_match",
                "ai_plot_verified",
            ),
        )
        candidates = tuple(
            promoted
            if candidate.tmdb_id == promoted.tmdb_id and candidate.media_type == promoted.media_type
            else candidate
            for candidate in fuzzy_result.candidates
        )
        reason = f" {choice.reason}" if choice.reason else ""
        verify_conf = comparison.confidence if comparison is not None else 0.0
        return TMDBMatchingResult(
            status="auto_match",
            selected_candidate=promoted,
            candidates=candidates,
            message=(
                f"AI подтвердил матч TMDB по описаниям "
                f"(choice={choice.confidence:.2f}, verify={verify_conf:.2f}).{reason}"
            ),
        )
