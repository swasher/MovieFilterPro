from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import re
from typing import Any, TYPE_CHECKING

import requests

from moviefilter.models import UserPreferences
from vault.models import Movie

if TYPE_CHECKING:
    from vault.services.tmdb_movie_matching_service import TMDBCandidate


logger = logging.getLogger("vault.tmdb_sync")


@dataclass(slots=True, frozen=True)
class AIPlotComparison:
    same_work: bool
    confidence: float
    reason: str = ""
    red_flags: tuple[str, ...] = ()


@dataclass(slots=True, frozen=True)
class AICandidateChoice:
    selected_candidate: TMDBCandidate | None
    confidence: float = 0.0
    runner_up_confidence: float = 0.0
    reason: str = ""
    red_flags: tuple[str, ...] = ()
    needs_human: bool = True

    @property
    def confidence_gap(self) -> float:
        return self.confidence - self.runner_up_confidence


class TMDBAIMatchingService:
    """AI arbiter for borderline TMDB matches.

    This service is deliberately conservative: deterministic title/year matching
    remains the primary path, and AI can only promote a candidate when it returns
    a clear, high-confidence winner.
    """

    PROMPT_VERSION = "tmdb_plot_match_v3"
    REQUEST_TIMEOUT_SECONDS = 45
    MIN_PLOT_CHARS = 40
    AUTO_MATCH_MIN_CONFIDENCE = 0.88
    AUTO_MATCH_MIN_GAP = 0.08
    SUPPORTED_AUTO_MATCH_MIN_CONFIDENCE = 0.70
    SUPPORTED_AUTO_MATCH_MIN_GAP = 0.05
    # Шаг 2 гибрида: независимая попарная проверка победителя.
    VERIFY_MIN_CONFIDENCE = 0.70

    @classmethod
    def compare_plots(
        cls,
        plot1: str,
        plot2: str,
        *,
        title: str = "",
        original_title: str = "",
        year: int | None = None,
    ) -> AIPlotComparison | None:
        """Compare two plot descriptions and return an AI confidence verdict."""
        if not cls._has_meaningful_plot(plot1) or not cls._has_meaningful_plot(plot2):
            return None

        context_parts: list[str] = []
        if title:
            context_parts.append(f"Название: {title}")
        if original_title:
            context_parts.append(f"Оригинальное название: {original_title}")
        if year:
            context_parts.append(f"Год: {year}")
        context_block = ""
        if context_parts:
            context_block = "Контекст проверяемого произведения:\n" + "\n".join(context_parts) + "\n\n"

        response = cls._chat_json(
            system_prompt=(
                "Ты сравниваешь описания фильмов/сериалов и определяешь, относятся ли они к одному произведению. "
                "Отвечай только JSON.\n\n"
                "Правила анализа:\n"
                "1. Комплементарные описания: описания одного и того же фильма часто пишутся с разных точек "
                "зрения (например, одно фокусируется на антагонисте/преступнике, а второе — на следователе/полиции; "
                "либо одно описывает завязку, а второе — развитие событий или конфликт). Если описания дополняют "
                "друг друга в рамках одного сеттинга, эпохи или конфликта — это одно произведение (same_work: true).\n"
                "2. Разные произведения: считай разными (same_work: false) только если описания содержат взаимоисключающие "
                "факты (совершенно разные жанры, разные исторические эпохи, несовместимые сеттинги, разные вымышленные вселенные).\n"
                "3. Не угадывай при полном отсутствии информации: если описания слишком общие или бессмысленные, "
                "понижай confidence и укажи red_flags."
            ),
            user_prompt=(
                f"{context_block}"
                "Сравни два описания и реши, один и тот же это фильм/сериал или нет.\n\n"
                "Верни JSON строго такого вида:\n"
                '{"same_work": true, "confidence": 0.0, "reason": "...", "red_flags": []}\n\n'
                f"Описание A:\n{cls._clip(plot1, 1800)}\n\n"
                f"Описание B:\n{cls._clip(plot2, 1800)}"
            ),
        )
        if response is None:
            return None
        comparison = AIPlotComparison(
            same_work=bool(response.get("same_work")),
            confidence=cls._clamp_confidence(response.get("confidence")),
            reason=cls._safe_text(response.get("reason"), 500),
            red_flags=cls._safe_text_tuple(response.get("red_flags")),
        )
        logger.info(
            "TMDB_AI_MATCH_VERIFY | prompt=%s | same_work=%s | confidence=%.2f | red_flags=%s | reason=%s",
            cls.PROMPT_VERSION,
            comparison.same_work,
            comparison.confidence,
            ";".join(comparison.red_flags),
            comparison.reason,
        )
        return comparison

    @classmethod
    def extract_web_hints(
        cls,
        title: str,
        original_title: str,
        plot: str,
        web_context: str,
    ) -> dict[str, Any] | None:
        """ШАГ 2 (урок find_tmdb_id.py): LLM извлекает чистые данные из веб-контекста.

        Возвращает {"clean_title": str, "year": int|None, "tmdb_queries": [str, ...]}
        или None, если локальный AI недоступен/ответ не распознан.
        """
        if not (web_context or "").strip():
            return None

        response = cls._chat_json(
            system_prompt=(
                "Ты определяешь точное оригинальное название фильма/сериала по искажённым "
                "данным и результатам веб-поиска. Отвечай только JSON. Не выдумывай данные: "
                "если веб-поиск пуст или неоднозначен, верни исходные названия и year null."
            ),
            user_prompt=(
                "Тебе даны искаженные данные фильма и результаты поиска в интернете по этим данным.\n\n"
                "Исходные данные:\n"
                f"Title: {title}\n"
                f"Original Title: {original_title}\n"
                f"Plot: {cls._clip(plot, 1800)}\n\n"
                "Результаты веб-поиска:\n"
                f"{cls._clip(web_context, 6000)}\n\n"
                "Задача: На основе веб-поиска определи точное официальное оригинальное название "
                "фильма и год выхода. Сформируй 2-3 точных запроса для базы данных TMDb "
                "(только названия, без года и лишних слов).\n\n"
                "Верни ответ СТРОГО в формате JSON:\n"
                '{"clean_title": "Точное оригинальное/международное название", '
                '"year": 2024, '
                '"tmdb_queries": ["Запрос 1", "Запрос 2"]}'
            ),
        )
        if response is None:
            return None

        clean_title = cls._safe_text(response.get("clean_title"), 300)
        year = cls._safe_int(response.get("year"))
        raw_queries = response.get("tmdb_queries")
        queries = [
            cls._safe_text(query, 300)
            for query in raw_queries
            if cls._safe_text(query, 300)
        ] if isinstance(raw_queries, list) else []
        hints = {"clean_title": clean_title, "year": year, "tmdb_queries": queries}
        logger.info(
            "TMDB_AI_WEB_HINTS | prompt=%s | clean_title=%s | year=%s | queries=%s",
            cls.PROMPT_VERSION,
            hints["clean_title"],
            hints["year"],
            hints["tmdb_queries"],
        )
        return hints

    @classmethod
    def choose_best_candidate(cls, movie: Movie, candidates: tuple[TMDBCandidate, ...]) -> AICandidateChoice | None:
        """Ask AI to choose one clear TMDB candidate from a borderline set."""
        source_plot = movie.description or ""
        viable_candidates = tuple(c for c in candidates if cls._has_meaningful_plot(c.overview))
        if not cls._has_meaningful_plot(source_plot):
            logger.info(
                "TMDB_AI_MATCH_SKIPPED | prompt=%s | reason=source_plot_too_short | movie_id=%s",
                cls.PROMPT_VERSION,
                getattr(movie, "id", None),
            )
            return None
        if not viable_candidates:
            logger.info(
                "TMDB_AI_MATCH_SKIPPED | prompt=%s | reason=no_candidate_overviews | movie_id=%s | candidates=%s",
                cls.PROMPT_VERSION,
                getattr(movie, "id", None),
                ",".join(str(candidate.tmdb_id) for candidate in candidates),
            )
            return None

        response = cls._chat_json(
            system_prompt=(
                "Ты помогаешь сопоставить локальный фильм/сериал с кандидатами TMDB. "
                "Отвечай только JSON. Будь консервативен, но если один кандидат имеет "
                "сильное совпадение названия/года/типа и его описание совместимо с "
                "локальным описанием, а остальные кандидаты сюжетно противоречат, "
                "выбирай сильного кандидата. Название, год и тип — важные сигналы, "
                "описания нужны для разрешения неоднозначности."
            ),
            user_prompt=cls._build_choice_prompt(movie, viable_candidates),
        )
        if response is None:
            return None

        candidate_by_id = {candidate.tmdb_id: candidate for candidate in viable_candidates}
        best_id = cls._safe_int(response.get("best_tmdb_id"))
        selected = candidate_by_id.get(best_id) if best_id is not None else None
        choice = AICandidateChoice(
            selected_candidate=selected,
            confidence=cls._clamp_confidence(response.get("confidence")),
            runner_up_confidence=cls._clamp_confidence(response.get("runner_up_confidence")),
            reason=cls._safe_text(response.get("reason"), 700),
            red_flags=cls._safe_text_tuple(response.get("red_flags")),
            needs_human=bool(response.get("needs_human", selected is None)),
        )
        logger.info(
            "TMDB_AI_MATCH_CHOICE | prompt=%s | movie_id=%s | best=%s | confidence=%.2f | runner_up=%.2f | needs_human=%s | red_flags=%s | reason=%s",
            cls.PROMPT_VERSION,
            getattr(movie, "id", None),
            getattr(choice.selected_candidate, "tmdb_id", None),
            choice.confidence,
            choice.runner_up_confidence,
            choice.needs_human,
            ";".join(choice.red_flags),
            choice.reason,
        )
        return choice

    @classmethod
    def is_auto_match(
        cls,
        choice: AICandidateChoice | None,
        *,
        deterministic_best: TMDBCandidate | None = None,
        deterministic_second: TMDBCandidate | None = None,
    ) -> bool:
        if choice is None or choice.selected_candidate is None:
            return False
        if choice.red_flags:
            return False
        if choice.confidence >= cls.AUTO_MATCH_MIN_CONFIDENCE and choice.confidence_gap >= cls.AUTO_MATCH_MIN_GAP:
            return True
        if deterministic_best is None:
            return False
        if (
            choice.selected_candidate.tmdb_id != deterministic_best.tmdb_id
            or choice.selected_candidate.media_type != deterministic_best.media_type
        ):
            return False
        deterministic_gap = deterministic_best.score - (deterministic_second.score if deterministic_second else 0)
        strong_reasons = {"original_exact", "title_exact", "year_exact"}
        best_reasons = set(deterministic_best.score_reasons or ())
        return (
            deterministic_best.score >= 80
            and deterministic_gap >= 10
            and len(strong_reasons & best_reasons) >= 2
            and choice.confidence >= cls.SUPPORTED_AUTO_MATCH_MIN_CONFIDENCE
            and choice.confidence_gap >= cls.SUPPORTED_AUTO_MATCH_MIN_GAP
        )

    @classmethod
    def is_plot_verified(cls, comparison: AIPlotComparison | None) -> bool:
        """Шаг 2 гибрида: независимая попарная проверка победителя.

        Возвращает True только если AI отдельно подтвердил, что описание
        источника и описание выбранного кандидата — одно произведение,
        без красных флагов и с достаточной уверенностью.
        """
        if comparison is None:
            return False
        if not comparison.same_work:
            return False
        if comparison.red_flags:
            return False
        return comparison.confidence >= cls.VERIFY_MIN_CONFIDENCE

    @classmethod
    def _build_choice_prompt(cls, movie: Movie, candidates: tuple[TMDBCandidate, ...]) -> str:
        source = {
            "title": movie.title or "",
            "original_title": movie.original_title or "",
            "year": movie.year,
            "movie_type": movie.movie_type,
            "duration_minutes": movie.duration,
            "description": cls._clip(movie.description or "", 1800),
        }
        candidate_payload = [
            {
                "tmdb_id": candidate.tmdb_id,
                "media_type": candidate.media_type,
                "title": candidate.title,
                "original_title": candidate.original_title,
                "year": candidate.year,
                "score": candidate.score,
                "score_reasons": list(candidate.score_reasons or ()),
                "overview": cls._clip(candidate.overview or "", 1400),
            }
            for candidate in candidates
        ]
        payload = {
            "source_movie": source,
            "tmdb_candidates": candidate_payload,
        }
        return (
            "Выбери кандидата TMDB, который является тем же произведением, что source_movie.\n"
            "Если явного победителя нет, верни best_tmdb_id=null и needs_human=true.\n"
            "Учитывай ремейки, сиквелы, одноименные фильмы и movie/tv различия как риск.\n\n"
            "Верни JSON строго такого вида:\n"
            "{"
            '"best_tmdb_id": 123, '
            '"confidence": 0.0, '
            '"runner_up_tmdb_id": null, '
            '"runner_up_confidence": 0.0, '
            '"needs_human": false, '
            '"reason": "...", '
            '"red_flags": []'
            "}\n\n"
            f"Данные:\n{json.dumps(payload, ensure_ascii=False)}"
        )

    @classmethod
    def _chat_json(cls, *, system_prompt: str, user_prompt: str) -> dict[str, Any] | None:
        prefs = cls._get_preferences()
        if prefs is None or not getattr(prefs, "ai_enabled", False):
            logger.info("TMDB_AI_MATCH_SKIPPED | prompt=%s | reason=ai_disabled", cls.PROMPT_VERSION)
            return None

        base_url = (getattr(prefs, "ai_base_url", "") or "").strip().rstrip("/")
        model = (getattr(prefs, "ai_model", "") or "").strip()
        if not base_url or not model:
            logger.info(
                "TMDB_AI_MATCH_SKIPPED | prompt=%s | reason=ai_not_configured | base_url=%s | model=%s",
                cls.PROMPT_VERSION,
                bool(base_url),
                bool(model),
            )
            return None

        url = cls._chat_completions_url(base_url)
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        api_key = (getattr(prefs, "ai_api_key", "") or "").strip()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        payload = {
            "model": model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }

        try:
            response = requests.post(url, headers=headers, json=payload, timeout=cls.REQUEST_TIMEOUT_SECONDS)
            response.raise_for_status()
            raw_payload = response.json()
        except Exception as exc:
            logger.warning("TMDB_AI_MATCH_FAILED | prompt=%s | %s", cls.PROMPT_VERSION, exc)
            return None

        content = cls._extract_message_content(raw_payload)
        if not content:
            return None
        parsed = cls._parse_json_object(content)
        if parsed is None:
            logger.warning("TMDB_AI_MATCH_BAD_JSON | prompt=%s | content=%s", cls.PROMPT_VERSION, cls._clip(content, 500))
        return parsed

    @staticmethod
    def _get_preferences():
        try:
            return UserPreferences.get()
        except Exception:
            return None

    @staticmethod
    def _chat_completions_url(base_url: str) -> str:
        if base_url.endswith("/v1"):
            return f"{base_url}/chat/completions"
        return f"{base_url}/v1/chat/completions"

    @staticmethod
    def _extract_message_content(payload: object) -> str:
        if not isinstance(payload, dict):
            return ""
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            return ""
        first = choices[0]
        if not isinstance(first, dict):
            return ""
        message = first.get("message")
        if isinstance(message, dict):
            content = message.get("content")
            return content if isinstance(content, str) else ""
        text = first.get("text")
        return text if isinstance(text, str) else ""

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

    @classmethod
    def _has_meaningful_plot(cls, value: str) -> bool:
        return len((value or "").strip()) >= cls.MIN_PLOT_CHARS

    @staticmethod
    def _clamp_confidence(value: object) -> float:
        try:
            result = float(value)
        except (TypeError, ValueError):
            return 0.0
        return max(0.0, min(1.0, result))

    @staticmethod
    def _safe_int(value: object) -> int | None:
        try:
            if value is None:
                return None
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _safe_text(value: object, max_chars: int) -> str:
        if value is None:
            return ""
        return str(value).strip()[:max_chars]

    @classmethod
    def _safe_text_tuple(cls, value: object) -> tuple[str, ...]:
        if not isinstance(value, list):
            return ()
        return tuple(cls._safe_text(item, 200) for item in value if cls._safe_text(item, 200))

    @staticmethod
    def _clip(value: str, max_chars: int) -> str:
        text = (value or "").strip()
        if len(text) <= max_chars:
            return text
        return f"{text[:max_chars].rstrip()}..."
