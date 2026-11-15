"""
Прогон AI-предсказания: оркестрация (БД, тайминг, ошибки).

Вся работа с моделью — в `ai_predict.services.engine`.
"""

from __future__ import annotations

import time

from ai_predict.models import MoviePrediction, TasteProfile
from ai_predict.services.engine import run_taste_engine
from ai_predict.services.movie_card import build_movie_card
from moviefilter.models import UserPreferences
from vault.models import Movie

# ------------------------------------ #
#          APPLICATION LAYER           #
# ------------------------------------ #


def predict_movie(movie: Movie, taste_profile: TasteProfile | None = None) -> MoviePrediction:
    """
    Прогоняет предсказание для пары (фильм, профиль) и сохраняет результат.

    Синхронно: локальная модель отвечает ~10 с. Если понадобится очередь,
    этот метод станет постановщиком задачи HUEY, а API начнёт возвращать
    статус `running` вместо готового результата.
    """
    started = time.monotonic()
    card = build_movie_card(movie)
    model_name = _current_model_name()

    prediction = MoviePrediction.objects.create(
        movie=movie,
        taste_profile=taste_profile,
        status=MoviePrediction.Status.RUNNING,
        input_snapshot=card,
        model_name=model_name,
    )

    try:
        result = run_taste_engine(card=card, taste_profile=taste_profile)
        prediction.status = MoviePrediction.Status.DONE
        prediction.result_text = result.text
        prediction.score = result.score
        prediction.verdict = result.verdict or ""
        prediction.confidence = result.confidence
        prediction.raw_response = result.raw
        prediction.model_name = model_name or ""
    except Exception as exc:  # noqa: BLE001 — прогон не должен ронять API
        prediction.status = MoviePrediction.Status.ERROR
        prediction.error = str(exc)

    prediction.duration_ms = int((time.monotonic() - started) * 1000)
    prediction.save()
    return prediction


def last_prediction(movie_id: int, taste_profile_id: int | None = None) -> MoviePrediction | None:
    """Последний прогон для фильма (и профиля, если указан)."""
    queryset = MoviePrediction.objects.filter(movie_id=movie_id)
    if taste_profile_id is not None:
        queryset = queryset.filter(taste_profile_id=taste_profile_id)
    return queryset.first()


# ------------------------------------ #
#            DOMAIN LAYER              #
# ------------------------------------ #


def _current_model_name() -> str:
    try:
        return (UserPreferences.get().ai_model or "").strip()
    except Exception:  # noqa: BLE001 — Preferences может быть ещё не создан
        return ""
