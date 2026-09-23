from __future__ import annotations

from dataclasses import replace
import html
import logging
import re
from typing import TYPE_CHECKING

from vault.models import Movie


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
      3. GROQ-стадия (семантическое попарное сравнение сюжетов через облако),
      4. локальный AI-выбор лучшего из всей кучи,
      5. проверка уверенности выбора,
      6. независимая попарная проверка победителя по сюжетам,
      7. повышение до auto_match.

    Новые промежуточные правила между детерминированным алгоритмом и AI
    добавляются в _apply_pre_ai_rules и не трогают остальные стадии.
    """

    ELIGIBLE_STATUSES = frozenset({"needs_confirmation", "needs_user_choice"})

    # Дословное совпадение описаний: сайты копируют синопсисы друг у друга.
    # Короткие фразы слишком общие, поэтому требуем минимум значимого текста.
    LITERAL_MIN_CHARS = 50

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
        return cls._promote_literal_match(fuzzy_result, winner, auto_match_min_score)

    @classmethod
    def _plots_match_literally(cls, source: str, overview: str) -> bool:
        """Дословно: нормализованные тексты равны либо один содержит другой."""
        left = cls._normalize_plot(source)
        right = cls._normalize_plot(overview)
        if len(left) < cls.LITERAL_MIN_CHARS or len(right) < cls.LITERAL_MIN_CHARS:
            return False
        if left == right:
            return True
        if len(left) <= len(right):
            return left in right
        return right in left

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

        return TMDBAIMatchingService.choose_best_candidate(movie, candidates)

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
