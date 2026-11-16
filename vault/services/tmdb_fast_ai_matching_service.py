from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import re
from typing import Any, TYPE_CHECKING

from core.services.ai_client import (
    new_ai_session_id,
    post_chat_completion,
    try_get_ai_config,
)
from vault.models import Movie
from web_logger import send_match_log

if TYPE_CHECKING:
    from vault.services.tmdb_movie_matching_service import TMDBCandidate


logger = logging.getLogger("vault.tmdb_sync")


@dataclass(slots=True, frozen=True)
class FastAIPlotScore:
    tmdb_id: int
    media_type: str
    confidence: float
    reason: str = ""


@dataclass(slots=True, frozen=True)
class FastAIChoice:
    selected_candidate: TMDBCandidate | None
    confidence: float = 0.0
    runner_up_confidence: float = 0.0
    reason: str = ""

    @property
    def confidence_gap(self) -> float:
        return self.confidence - self.runner_up_confidence


class TMDBFastAIMatchingService:
    """Быстрая стадия матчинга: попарное семантическое сравнение сюжетов через активный AI.

    Используется когда плоты написаны разными людьми и дословный матч
    не сработал: по каждому кандидату спрашиваем активный AI endpoint и
    отдаем победу только одному явному победителю. Провайдер не важен —
    подходит любой OpenAI-совместимый сервер (локальный или облачный).
    """

    # ------------------------------------ #
    #          APPLICATION LAYER           #
    # ------------------------------------ #

    PROMPT_VERSION = "tmdb_fast_ai_plot_v1"
    REQUEST_TIMEOUT_SECONDS = 45
    MIN_PLOT_CHARS = 40
    # Практика показала: 0.6+ уже означает тот же фильм — совпадение
    # по значимым тропам, даже без уникальных имен в обоих описаниях.
    AUTO_MATCH_MIN_CONFIDENCE = 0.6
    AUTO_MATCH_MIN_GAP = 0.10

    SYSTEM_PROMPT = """
Ты — система анализа сходства текстов.
Твоя задача — сравнить два описания сюжетов фильмов и определить, описывают ли они один и тот же фильм.

Правила анализа:
1. Имена собственные и уникальные детали:
   - Совпадение редких имен персонажей, специфических топонимов (названий городов, заведений), нестандартных предметов или уникальных комбинаций имен существенно повышает вероятность того, что это один фильм. Наличие таких совпадений должно давать оценку уверенности близкую к 1.0 (0.85 – 1.0), даже если одно из описаний гораздо короче другого.
   - Частые имена или общеизвестные локации сами по себе не гарантируют совпадение и требуют анализа сюжетного контекста.

2. Сюжетный контекст:
   - Сравнивай ключевые действия, роли персонажей и завязку конфликта.
   - Одно описание может быть краткой аннотацией, а второе — подробным пересказом. Игнорируй разницу в объеме, стиле и детализации, если ключевые факты совпадают.

Оценка уверенности (confidence):
- 0.85 – 1.0: Есть совпадения по уникальным именам собственным, топонимам или специфическим сюжетным ходам.
- 0.50 – 0.84: Сюжетные линии похожи, но имена отсутствуют или различаются, либо совпадения касаются только базовых штампов.
- 0.00 – 0.49: Описания содержат прямые противоречия в ключевых фактах или рассказывают о совершенно разных событиях и персонажах.

Верни ответ строго в формате JSON:
- 'confidence': число от 0.0 до 1.0.
- 'reason': краткое объяснение, какие именно элементы (имена, локации, события) повлияли на оценку.
"""

    @classmethod
    def choose_confident(
        cls,
        movie: Movie,
        candidates: tuple[TMDBCandidate, ...],
    ) -> FastAIChoice | None:
        """Попарно сравнивает сюжет источника с каждым кандидатом через активный AI.

        Возвращает None если AI не настроен, некому сравнивать или все
        запросы упали — тогда конвейер идет дальше к глубокому AI-выбору.
        """
        source_plot = movie.description or ""
        if not cls._has_meaningful_plot(source_plot):
            logger.info(
                "TMDB_FAST_AI_SKIPPED | prompt=%s | reason=source_plot_too_short | movie_id=%s",
                cls.PROMPT_VERSION,
                getattr(movie, "id", None),
            )
            return None
        viable = tuple(c for c in candidates if cls._has_meaningful_plot(c.overview or ""))
        if not viable:
            logger.info(
                "TMDB_FAST_AI_SKIPPED | prompt=%s | reason=no_candidate_overviews | movie_id=%s",
                cls.PROMPT_VERSION,
                getattr(movie, "id", None),
            )
            return None
        if not cls._is_configured():
            logger.info(
                "TMDB_FAST_AI_SKIPPED | prompt=%s | reason=ai_not_configured | movie_id=%s",
                cls.PROMPT_VERSION,
                getattr(movie, "id", None),
            )
            return None

        scored: list[FastAIPlotScore] = []
        # Один session id на весь прогон: Go роутит запросы диалога стабильно
        # и переиспользует prompt cache.
        session_id = new_ai_session_id()
        for candidate in viable:
            score = cls.compare_pair(source_plot, candidate.overview or "", session_id=session_id)
            send_match_log(
                "ai_pair_call",
                movie_id=getattr(movie, "id", None),
                tmdb_id=candidate.tmdb_id,
                confidence=round(score.confidence, 2) if score is not None else None,
                ok=score is not None,
            )
            if score is None:
                continue
            scored.append(
                FastAIPlotScore(
                    tmdb_id=candidate.tmdb_id,
                    media_type=candidate.media_type,
                    confidence=score.confidence,
                    reason=score.reason,
                )
            )
        if not scored:
            logger.warning(
                "TMDB_FAST_AI_FAILED | prompt=%s | movie_id=%s | reason=all_requests_failed",
                cls.PROMPT_VERSION,
                getattr(movie, "id", None),
            )
            return None

        scored.sort(key=lambda item: item.confidence, reverse=True)
        best, runner_up = scored[0], scored[1] if len(scored) > 1 else None
        candidate_by_id = {(c.tmdb_id, c.media_type): c for c in viable}
        choice = FastAIChoice(
            selected_candidate=candidate_by_id.get((best.tmdb_id, best.media_type)),
            confidence=best.confidence,
            runner_up_confidence=runner_up.confidence if runner_up else 0.0,
            reason=best.reason,
        )
        logger.info(
            "TMDB_FAST_AI_CHOICE | prompt=%s | movie_id=%s | best=%s | confidence=%.2f | runner_up=%.2f | reason=%s",
            cls.PROMPT_VERSION,
            getattr(movie, "id", None),
            getattr(choice.selected_candidate, "tmdb_id", None),
            choice.confidence,
            choice.runner_up_confidence,
            choice.reason,
        )
        return choice

    @classmethod
    def is_auto_match(cls, choice: FastAIChoice | None) -> bool:
        """Один явный победитель: уверенность 0.6+ (имена или значимые тропы) + отрыв."""
        if choice is None or choice.selected_candidate is None:
            return False
        return (
            choice.confidence >= cls.AUTO_MATCH_MIN_CONFIDENCE
            and choice.confidence_gap >= cls.AUTO_MATCH_MIN_GAP
        )

    @classmethod
    def compare_pair(
        cls,
        plot_a: str,
        plot_b: str,
        *,
        session_id: str | None = None,
    ) -> FastAIPlotScore | None:
        """Одно попарное сравнение двух сюжетов через активный AI."""
        if not cls._has_meaningful_plot(plot_a) or not cls._has_meaningful_plot(plot_b):
            return None
        response = cls._chat_json(
            user_prompt=(
                f"Описание 1:\n{cls._clip(plot_a, 1800)}\n\n"
                f"Описание 2:\n{cls._clip(plot_b, 1800)}"
            ),
            session_id=session_id,
        )
        if response is None:
            return None
        return FastAIPlotScore(
            tmdb_id=0,
            media_type="",
            confidence=cls._clamp_confidence(response.get("confidence")),
            reason=cls._safe_text(response.get("reason"), 500),
        )

    # ------------------------------------ #
    #            DOMAIN LAYER              #
    # ------------------------------------ #

    @classmethod
    def _chat_json(cls, *, user_prompt: str, session_id: str | None = None) -> dict[str, Any] | None:
        config = try_get_ai_config()
        if config is None:
            return None

        try:
            result = post_chat_completion(
                config,
                messages=[
                    {"role": "system", "content": cls.SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0,
                json_mode=True,
                session_id=session_id,
                timeout=cls.REQUEST_TIMEOUT_SECONDS,
            )
        except Exception as exc:
            logger.warning("TMDB_FAST_AI_FAILED | prompt=%s | %s", cls.PROMPT_VERSION, exc)
            return None

        if not result.content:
            return None
        parsed = cls._parse_json_object(result.content)
        if parsed is None:
            logger.warning(
                "TMDB_FAST_AI_BAD_JSON | prompt=%s | content=%s",
                cls.PROMPT_VERSION,
                cls._clip(result.content, 500),
            )
        return parsed

    @classmethod
    def _is_configured(cls) -> bool:
        return try_get_ai_config() is not None

    @classmethod
    def _has_meaningful_plot(cls, value: str) -> bool:
        return len((value or "").strip()) >= cls.MIN_PLOT_CHARS

    @staticmethod
    def _parse_json_object(content: str) -> dict[str, Any] | None:
        text = content.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
            text = re.sub(r"\s*```$", "", text)
        try:
            parsed = json.loads(text)
        except ValueError:
            match = re.search(r"\{.*\}", text, flags=re.DOTALL)
            if not match:
                return None
            try:
                parsed = json.loads(match.group(0))
            except ValueError:
                return None
        return parsed if isinstance(parsed, dict) else None

    @staticmethod
    def _clamp_confidence(value: object) -> float:
        try:
            result = float(value)
        except (TypeError, ValueError):
            return 0.0
        return max(0.0, min(1.0, result))

    @staticmethod
    def _safe_text(value: object, max_chars: int) -> str:
        if value is None:
            return ""
        return str(value).strip()[:max_chars]

    @staticmethod
    def _clip(value: str, max_chars: int) -> str:
        text = (value or "").strip()
        if len(text) <= max_chars:
            return text
        return f"{text[:max_chars].rstrip()}..."
