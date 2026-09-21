import json
import re
import time
from ddgs import DDGS
from openai import OpenAI
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Конфигурация
# ---------------------------------------------------------------------------
SERVER_HOST = "localhost"
SERVER_PORT = 13305
MODEL_NAME = "Qwen3.5-9B-GGUF-UD-Q4_K_XL"

BASE_URL = f"http://{SERVER_HOST}:{SERVER_PORT}/api/v1"

# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------
def print_section(title: str, symbol: str = "="):
    width = 70
    print(f"\n{symbol * width}")
    print(f" {title}")
    print(f"{symbol * width}")

def truncate_text(text: str, max_length: int = 150) -> str:
    text_clean = " ".join(text.split())
    if len(text_clean) > max_length:
        return text_clean[:max_length] + "..."
    return text_clean

def build_search_query(user_task: str) -> str:
    # Берем строго первое предложение до точки (как в успешном Тесте №4)
    first_sentence = user_task.split(".")[0].strip()
    return f"site:themoviedb.org {first_sentence}"

# ---------------------------------------------------------------------------
# Pydantic-схема ответа
# ---------------------------------------------------------------------------
class MovieSearchResult(BaseModel):
    tmdb_id: int = Field(
        description="Найденный ID фильма на TMDb. Если не найден, укажи -1"
    )
    title: str = Field(description="Название найденного фильма")
    confidence: float = Field(description="Уверенность от 0.0 до 1.0")


# ---------------------------------------------------------------------------
# Модуль поиска
# ---------------------------------------------------------------------------
def search_internet(query: str, max_results: int = 3) -> str:
    print_section("ЭТАП 1: Поиск в сети (DuckDuckGo)")
    print(f"[>] Сформированный поисковый запрос: '{query}'")

    t0 = time.time()
    ddgs = DDGS()

    # ВАЖНО: Добавлен region="ru-ru"
    results = list(
        ddgs.text(query, region="ru-ru", max_results=max_results)
    )

    print(
        f"[✓] Найдено результатов: {len(results)} (за {time.time() - t0:.2f} сек)\n"
    )

    formatted_context = ""
    for idx, r in enumerate(results, 1):
        title = truncate_text(r.get("title", ""), max_length=80)
        body = truncate_text(r.get("body", ""), max_length=160)
        url = r.get("href", "")

        print(f"--- Результат #{idx} ---")
        print(f"Заголовок : {title}")
        print(f"URL       : {url}")
        print(f"Вырезка   : {body}\n")

        formatted_context += (
            f"Заголовок: {r.get('title')}\n"
            f"Ссылка/URL: {url}\n"
            f"Описание: {r.get('body')}\n\n"
        )

    return formatted_context


# ---------------------------------------------------------------------------
# Основная логика работы с LLM
# ---------------------------------------------------------------------------
def process_query_with_llm(user_task: str):
    print_section("ВХОДНЫЕ ДАННЫЕ")
    print(f"Задача/Описание: {truncate_text(user_task, max_length=200)}")

    # 1. Поисковый запрос
    search_query = build_search_query(user_task)
    search_context = search_internet(search_query)

    # 2. Подготовка промпта
    system_prompt = (
        "Ты — ассистент-аналитик. Твоя задача — проанализировать предоставленный контекст из поиска "
        "и извлечь точный ID фильма/сериала на TMDb.\n"
        "ID обычно содержится прямо в URL (например: themoviedb.org/movie/12345 или /tv/12345).\n"
        "Отвечай СТРОГО в формате JSON без разметки markdown (без ```json).\n"
        "Формат ответа:\n"
        "{\n"
        '  "tmdb_id": int,\n'
        '  "title": "string",\n'
        '  "confidence": float\n'
        "}"
    )
    user_prompt = (
        f"Описание/Задача: {user_task}\n\n"
        f"Результаты поиска в сети:\n{search_context}"
    )

    print_section("ЭТАП 2: Подготовка данных для AI (Промпт)")
    print("[System Prompt]:")
    print(f"  {system_prompt}")
    print("\n[User Prompt]:")
    for line in user_prompt.split("\n"):
        if line.strip():
            print(f"  {truncate_text(line, max_length=120)}")

    # 3. Запрос к Lemonade Server
    print_section("ЭТАП 3: Запрос к Lemonade Server")
    print(f"[>] Подключение к серверу: {BASE_URL}")
    print(f"[>] Целевая модель: {MODEL_NAME}")

    client = OpenAI(
        base_url=BASE_URL,
        api_key="lemonade",
        timeout=180.0,  # Запас времени на случай перезагрузки VRAM
    )

    t1 = time.time()
    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0.1,
    )
    print(f"[✓] Генерация завершена за {time.time() - t1:.2f} сек.")

    # 4. Вывод и валидация результатов
    raw_json = response.choices[0].message.content
    parsed_data = MovieSearchResult.model_validate_json(raw_json)

    print_section("ЭТАП 4: Ответ от AI")
    print("[Сырой JSON от модели]:")
    print(f"  {raw_json}")

    print("\n[Распарсенный Pydantic-объект]:")
    print(f"  TMDb ID    : {parsed_data.tmdb_id}")
    print(f"  Название   : {parsed_data.title}")
    print(f"  Уверенность: {parsed_data.confidence}")

    return parsed_data


# ---------------------------------------------------------------------------
# Запуск
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    task = (
        "Кара Зор-Эл путешествует по галактике со своим псом Крипто. "
        "На неё нападает пират и разбойник, который угоняет её корабль и ранит Крипто. "
        "Объединив силы с новой подругой и союзницей Рути, семью которой ранее убил пират, "
        "Кара отправляется мстить."
    )

    process_query_with_llm(task)