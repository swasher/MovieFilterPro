"""Локальный пересчёт скора bestfilmsof по своим весам.

Формула реверс-инжинирена в прототипе и сверена с сервером до цента:
score = 100 * sum(w_i * c_i) / sum(w_i), где c_i — компонент или его fallback.
"""

from __future__ import annotations

from .constants import WEIGHT_KEYS, WEIGHT_PRESETS


def clamp_weight(value) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, min(100, number))


def parse_weights(raw: dict) -> dict[str, int]:
    return {key: clamp_weight(raw.get(key, 0)) for key in WEIGHT_KEYS}


def resolve_preset(preset: str | None) -> tuple[str, dict[str, int] | None]:
    """Возвращает (имя пресета, веса или None для дефолтного порядка)."""
    if preset not in WEIGHT_PRESETS and preset != "custom":
        preset = "default"
    if preset != "custom":
        return preset, WEIGHT_PRESETS[preset]
    return preset, None


def rescore(entry, weights: dict[str, int]) -> float | None:
    total = sum(weights.get(key, 0) for key in WEIGHT_KEYS)
    if total <= 0:
        return None
    acc = 0.0
    for key in WEIGHT_KEYS:
        weight = weights.get(key, 0)
        if not weight:
            continue
        component = getattr(entry, "comp_" + key)
        if component is None:
            component = getattr(entry, "fb_" + key, None)
        if component is None:
            return None
        acc += weight * component
    return round(100 * acc / total, 2)
