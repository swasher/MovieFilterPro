"""
Движок предсказания: собирает промпт, спрашивает локальную LLM, нормализует ответ
и рендерит человекочитаемый отчёт для модалки.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ai_predict.models import TasteProfile
from core.services.ai_client import chat_json, get_ai_config
from ai_predict.services.prompt import build_system_prompt, build_user_prompt

VERDICT_LABELS = {"watch": "брать", "maybe": "может быть", "skip": "не брать"}

MAX_LIST_ITEMS = 3


class EngineError(Exception):
    """Движок не смог получить результат. Текст показывается пользователю."""


@dataclass
class EngineResult:
    text: str
    score: int | None
    verdict: str | None
    confidence: float | None
    raw: dict[str, Any]


def run_taste_engine(*, card: dict[str, Any], taste_profile: TasteProfile | None) -> EngineResult:
    profile_content = (taste_profile.content or "").strip() if taste_profile else ""
    if not profile_content:
        raise EngineError(
            "Профиль вкусов не выбран или пуст — заполните его в Preferences → Taste."
        )

    config = get_ai_config()
    raw, _content = chat_json(
        config=config,
        system_prompt=build_system_prompt(profile_content),
        user_prompt=build_user_prompt(card),
    )

    verdict = normalize_verdict(raw)
    text = render_report(
        card=card,
        taste_profile=taste_profile,
        model_name=config.model,
        verdict=verdict,
    )
    return EngineResult(
        text=text,
        score=verdict["score"],
        verdict=verdict["verdict"],
        confidence=verdict["confidence"],
        raw=raw,
    )


def normalize_verdict(raw: dict[str, Any]) -> dict[str, Any]:
    """Приводит ответ модели к предсказуемому виду (типы, границы, вердикт)."""
    score = _as_score(raw.get("score"))
    verdict = _as_verdict(raw.get("verdict"))
    # Вердикт модели оставляем как есть; подставляем свой только если его нет.
    if verdict is None and score is not None:
        verdict = "watch" if score >= 7 else ("maybe" if score >= 5 else "skip")

    return {
        "score": score,
        "verdict": verdict,
        "confidence": _as_confidence(raw.get("confidence")),
        "plus": _as_list(raw.get("plus")),
        "minus": _as_list(raw.get("minus")),
        "unknowns": _as_list(raw.get("unknowns")),
        "summary": _as_summary(raw.get("summary")),
    }


def render_report(
    *,
    card: dict[str, Any],
    taste_profile: TasteProfile | None,
    model_name: str,
    verdict: dict[str, Any],
) -> str:
    profile_name = taste_profile.name if taste_profile else "не выбран"

    lines = [
        f"Профиль: {profile_name}",
        f"Модель: {model_name or 'не настроена'}",
        "",
    ]

    score = verdict.get("score")
    if score is None:
        lines.append("Оценка: модель не вернула score")
    else:
        label = VERDICT_LABELS.get(verdict.get("verdict") or "", "")
        lines.append(f"Оценка: {score}/10 — {label}" if label else f"Оценка: {score}/10")
        confidence = verdict.get("confidence")
        if confidence is not None:
            lines.append(f"Уверенность: {confidence:.2f}")

    summary = verdict.get("summary")
    if summary:
        lines += ["", f"Кратко: {summary}"]

    for key, title in (("plus", "Плюсы"), ("minus", "Минусы"), ("unknowns", "Неясно")):
        items = verdict.get(key) or []
        if items:
            lines += ["", f"{title}:"]
            lines += [f"• {item}" for item in items]

    return "\n".join(lines).strip()


def _as_score(value: Any) -> int | None:
    try:
        number = int(round(float(value)))
    except (TypeError, ValueError):
        return None
    return max(1, min(10, number))


def _as_verdict(value: Any) -> str | None:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in VERDICT_LABELS else None


def _as_confidence(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, min(1.0, number))


def _as_list(value: Any) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    items = [" ".join(str(item).split()) for item in value]
    return [item for item in items if item][:MAX_LIST_ITEMS]


def _as_summary(value: Any) -> str:
    return " ".join(str(value or "").split())[:240]
