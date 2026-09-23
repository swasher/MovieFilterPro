import json
import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv
from groq import Groq
from pydantic import BaseModel, Field

# Загрузка переменных окружения
load_dotenv()

# --- Константы для конфигурации и экспериментов ---
GROQ_API_KEY: Optional[str] = os.getenv("GROQ_API_KEY")

MODEL_NAME0: str = "openai/gpt-oss-120b"
MODEL_NAME1: str = "openai/gpt-oss-20b"
MODEL_NAME2: str = "qwen/qwen3.8-27b"  # <== best

MODEL_NAME = MODEL_NAME2

TEMPERATURE: float = 0.0
MOVIES_DIR: Path = Path("movies")

# --- Системный промпт ---
SYSTEM_PROMPT: str = """
Ты — система анализа сходства текстов.
Твоя задача — сравнить два описания сюжетов фильмов и определить, описывают ли они один и тот же фильм.

Правила анализа:
1. Имена собственные и уникальные детали:
   - Совпадение редких имен персонажей, специфических топонимов (названий городов, заведений), нестандартных предметов или уникальных комбинаций имен (например, "Адель" и "Эгисхайм") существенно повышает вероятность того, что это один фильм. Наличие таких совпадений должно давать оценку уверенности близкую к 1.0 (0.85 – 1.0), даже если одно из описаний гораздо короче другого.
   - Частые имена или общеизвестные локации (например, "Джон", "Анна", "Нью-Йорк") сами по себе не гарантируют совпадение и требуют анализа сюжетного контекста.

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


class SimilarityResponse(BaseModel):
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Степень уверенности от 0.0 до 1.0."
    )
    reason: str = Field(
        ...,
        description="Краткое обоснование решения."
    )


def compare_plots(client: Groq, plot_a: str, plot_b: str) -> SimilarityResponse:
    """Отправляет два описания сюжета в Groq API и возвращает структурированный ответ."""
    user_prompt = f"""
Описание 1:
{plot_a}

Описание 2:
{plot_b}
"""

    response = client.chat.completions.create(
        model=MODEL_NAME,
        temperature=TEMPERATURE,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt}
        ],
        response_format={
            "type": "json_object",
            "schema": SimilarityResponse.model_json_schema()
        }
    )

    raw_json = response.choices[0].message.content
    return SimilarityResponse.model_validate_json(raw_json)


def process_movie_files() -> None:
    """Читает все JSON файлы из папки MOVIES_DIR и проводит тестирование."""
    if not GROQ_API_KEY:
        raise ValueError("Переменная окружения GROQ_API_KEY не найдена в .env")

    if not MOVIES_DIR.exists() or not MOVIES_DIR.is_dir():
        print(f"Папка '{MOVIES_DIR}' не найдена. Создайте её и добавьте .json файлы.")
        return

    json_files = sorted(list(MOVIES_DIR.glob("*.json")))

    if not json_files:
        print(f"В папке '{MOVIES_DIR}' нет файлов с расширением .json")
        return

    client = Groq(api_key=GROQ_API_KEY)

    print(f"=== Старт тестирования ===")
    print(f"Модель: {MODEL_NAME}")
    print(f"Найдено файлов для проверки: {len(json_files)}\n" + "=" * 50)

    for file_path in json_files:
        print(f"\n Обработка файла: {file_path.name}")

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            title = data.get("title", "Без названия")
            plot_a = data.get("plot_a", "").strip()
            plot_b = data.get("plot_b", "").strip()

            if not plot_a or not plot_b:
                print(" Пропущен: в файле отсутствуют поля 'plot_a' или 'plot_b'")
                continue

            print(f"Фильм: {title}")

            result = compare_plots(client, plot_a, plot_b)

            print(f"Уверенность: {result.confidence:.2f}")
            print(f"Причина:     {result.reason}")

        except json.JSONDecodeError:
            print(f"Ошибка: Некорректный формат JSON в файле {file_path.name}")
        except Exception as e:
            print(f"Ошибка при обработке {file_path.name}: {e}")

    print("\n" + "=" * 50)
    print("=== Тестирование завершено ===")


if __name__ == "__main__":
    process_movie_files()
