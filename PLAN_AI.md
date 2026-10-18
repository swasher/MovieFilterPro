# План внедрения AI-системы (Groq) для `kinozal` и `vault`

## 1) Что уже есть в проекте (и на что опираемся)

### `kinozal`/очередь
- Очередь кандидатов уже хранится в `moviefilter.MovieRSS` (приоритеты: HIGH/LOW/DEFER/SKIP/WAIT_TRANS/TRANS_FOUND).
- Сканирование Kinozal уже асинхронное, с отменой и уведомлениями (`kinozal_scan.service.start_scan_task`, `kinozal.api`).
- В `movie_audit` уже есть базовая фильтрация (страны/жанры/год/рейтинг), проверка пересечений с Kinorium, разбор деталей раздачи.
- Скачивание `.torrent` уже реализовано в `moviefilter.api` и использует настроенную hotfolder-папку.

### `vault`/хранилище
- `vault.Movie` + `Rating` + `UserList(UserListMovie)` уже дают полный профиль предпочтений: оценки, «буду смотреть», «не буду», «избранное», «просмотрено».
- `MovieStatusService` уже централизует изменения статусов и оценок.

**Вывод:** у вас уже есть сильная база для AI. На первом этапе лучше не ломать текущий pipeline, а добавить AI-слой рядом.

---

## 2) Цели AI и границы ответственности

### Цель A: Подсказки (Recommend)
Система не скачивает автоматически, а выставляет:
- `ai_score` (0..1),
- `ai_verdict` (`watch` / `maybe` / `skip`),
- краткое объяснение «почему».

### Цель B: Авто-анализ + авто-скачивание (Autopilot)
Система сама:
1. анализирует новую запись из `MovieRSS`,
2. принимает решение по порогам,
3. вызывает существующий механизм скачивания torrent,
4. логирует «почему скачали» и «какой confidence».

### Ключевое правило
Autopilot включается только после периода наблюдения (например, 2-4 недели), когда качество рекомендаций подтверждено.

---

## 3) Архитектура (рекомендуемая)

## 3.1 Новый модуль `ai_recommendation`
Создать Django app: `ai_recommendation`.

Слои:
1. **Feature Layer** (сбор фичей)
    - из `vault`: рейтинги, списки, любимые жанры/страны/персоны;
    - из `MovieRSS`: рейтинг imdb/kinopoisk, перевод, год, жанры, страны, режиссер/актеры, флаг `dubbed`.
2. **LLM Layer (Groq)**
    - клиент + prompt templates;
    - строгий JSON-ответ по схеме.
3. **Decision Layer**
    - пороги (например `>=0.85` → auto-download);
    - policy (тихий режим, dry-run, расписание, лимит скачиваний/сутки).
4. **Audit Layer**
    - хранение входных фич, промпта, результата, confidence, ошибок, длительности.

## 3.2 Новые таблицы

### `AIRecommendation`
- `source_movie_rss` (FK -> MovieRSS)
- `user` (FK, nullable если single-user)
- `model_name` (`llama-3.3-70b-versatile` или другой на Groq)
- `score` (float 0..1)
- `verdict` (`watch/maybe/skip`)
- `reasons` (JSON/text)
- `feature_snapshot` (JSON)
- `prompt_version` (str)
- `created_at`

### `AIDownloadDecision`
- `movie_rss` (FK)
- `recommendation` (FK)
- `decision` (`downloaded/rejected/manual_override`)
- `decision_reason`
- `torrent_id` (опционально)
- `executed_at`

### `AIUserProfileSnapshot` (опционально)
Кэш агрегированных предпочтений, чтобы не пересчитывать на каждый фильм.

---

## 4) Интеграция с Groq

## 4.1 Конфиг
В `UserPreferences` добавьте:
- `groq_api_key` (или лучше через ENV),
- `groq_model_name`,
- `ai_enabled`,
- `ai_autopilot_enabled`,
- `ai_auto_download_threshold` (например 0.85),
- `ai_daily_download_limit`.

Лучше хранить ключ в ENV (`GROQ_API_KEY`), а в БД — только флаги и параметры политики.

## 4.2 Клиент
Сервис `ai_recommendation/services/groq_client.py`:
- timeout + retry + circuit breaker,
- принудительный JSON output (строгий парсинг),
- защита от пустых/битых ответов.

## 4.3 Структура промпта
В prompt передавать только важные сигналы:
- user taste profile (top genres, disliked genres, любимые режиссеры/актеры, средний рейтинг по жанрам),
- movie candidate features,
- бизнес-правила (например: не рекомендовать если в `wont_watch`, снижать score если слабый рейтинг + плохой перевод).

Ожидать JSON:
```json
{
  "score": 0.0,
  "verdict": "watch|maybe|skip",
  "confidence": 0.0,
  "reasons": ["..."],
  "risk_flags": ["low_rating", "no_dubbed"]
}
```

---

## 5) Пайплайны (как связать `kinozal` и `vault`)

## 5.1 Режим подсказок
1. `kinozal_scan` добавляет фильмы в `MovieRSS` как сейчас.
2. Фоновая задача берет новые `MovieRSS`.
3. Считает фичи + вызывает Groq.
4. Пишет `AIRecommendation`.
5. UI показывает badge: score/verdict/объяснение.

## 5.2 Режим автоскачивания
1. После получения `AIRecommendation` применяем policy:
    - `score >= threshold`
    - `confidence >= threshold_confidence`
    - нет стоп-флагов
    - не превышен дневной лимит.
2. Выполняем `kinozal_search` + выбираем лучший релиз (правила качества).
3. Вызываем `get_torrent_file` (или выделенный сервисный метод без HTTP view).
4. Пишем `AIDownloadDecision`.
5. Отправляем уведомление в `web_logger`/нотификации.

---

## 6) Алгоритм выбора релиза (важно для autopilot)

Сделать deterministic-ранжирование релизов перед скачиванием:
- Must-have: достаточные сиды, размер в заданных пределах, корректный перевод.
- Плюс-баллы: 4K при вашем профиле/TV, HDR/SDR по настройке, свежесть, trusted uploader.
- Минус-баллы: мало сидов, сомнительный перевод, слишком большой/маленький размер.

Итог: `best_torrent = argmax(rule_score)`.

LLM может помочь, но final decision лучше оставить rule-based (контролируемость выше).

---

## 7) Feature engineering: что брать из `vault`

Базовый профиль пользователя:
- распределение оценок по жанрам,
- топ-актеры/режиссеры из high-rated,
- доля фильмов в `wont_watch`,
- recency: что смотрели/оценивали недавно,
- tolerance к старым фильмам и странам.

Простой baseline score (без LLM):
- жанровое сходство,
- совпадение по персоне,
- рейтинг imdb/kp,
- штраф за `wont_watch`-паттерны.

Затем LLM делает re-ranking + explanation.

---

## 8) Безопасность и надежность

- **Fail-safe:** если Groq недоступен — система работает как раньше (без AI).
- **Dry-run режим:** autopilot считает, но не скачивает; пишет «что БЫ сделал».
- **Rate limit + budget control:** ограничить запросы к Groq и число скачиваний/сутки.
- **Idempotency:** не скачивать один и тот же `kinozal_id` повторно.
- **Auditability:** сохранять решение и причины (для ручного разбора ошибок).

---

## 9) UI/UX изменения

В ленте `MovieRSS` добавить:
- `AI score` badge,
- `AI verdict`,
- кнопки: `Accept AI`, `Reject AI`, `Download by AI` (если autopilot off),
- подсказку «почему рекомендовали».

В `vault` добавить страницу «AI аналитика»:
- precision@K по последним N рекомендациям,
- какие причины чаще всего приводят к удачным рекомендациям,
- быстрый контроль порогов autopilot.

---

## 10) Метрики качества

Онлайн-метрики:
- CTR на AI-рекомендации,
- conversion to watched,
- доля ручных override.

Оффлайн-метрики:
- precision@10,
- recall по «просмотренным и оцененным >= X»,
- calibration score vs фактическая оценка.

Цель перед включением autopilot:
- precision@10 >= 0.7 (пример),
- override rate < 20%.

---

## 11) Дорожная карта (по спринтам)

### Sprint 1 (1 неделя): фундамент
- app `ai_recommendation` + модели `AIRecommendation`, `AIDownloadDecision`;
- Groq client + prompt v1;
- management command для пакетного анализа новых `MovieRSS`.

### Sprint 2 (1 неделя): режим подсказок
- интеграция в UI ленты;
- логирование и метрики;
- dry-run отчеты.

### Sprint 3 (1 неделя): autopilot beta
- policy engine,
- deterministic torrent ranking,
- авто-скачивание с лимитами и стоп-правилами.

### Sprint 4 (1 неделя): стабилизация
- A/B порогов,
- улучшение prompt/features,
- отчеты качества и тонкая настройка.

---

## 12) Технический долг, который лучше закрыть до AI

1. В `MovieStatusService.add_to_list` используется `defaults={'note': note}` и последующее `list_movie.note`, но у `UserListMovie` поле `note` удалено (DEPRECATED), это потенциальная ошибка при выполнении. Лучше исправить до запуска AI-автоматизаций.
2. Логика `kinozal_search` / `get_torrent_file` сейчас завязана на view-функции; для autopilot надежнее вынести в чистый сервисный слой (без request/messages).
3. Желательно нормализовать поле `MovieRSS.year` (сейчас `CharField`) для устойчивых фильтров/сопоставлений.

---

## 13) Минимальный MVP (если нужно быстро)

Если хотите старт «за 3-5 дней»:
1. Только режим подсказок (без автоскачивания).
2. Только один prompt v1 + один score.
3. Кнопка «Скачать по рекомендации» вручную.
4. Сбор feedback (`agree/disagree`) для последующей автополитики.

Это даст быструю ценность и безопасный запуск без риска «накачать лишнего».

---

## 14) Рекомендуемый стек внутри проекта

- Django app: `ai_recommendation`
- Background jobs: Celery/RQ (или ваш текущий async-task подход, но для надежности лучше очередь задач)
- Хранилище фич: Postgres JSONField (на старте)
- Инференс: Groq API
- Observability: существующий `web_logger` + отдельный logger `ai`

---

## 15) Что делать прямо сейчас (первые 5 шагов)

1. Завести `ai_recommendation` app + миграции моделей аудита.
2. Добавить ENV `GROQ_API_KEY` и `GROQ_MODEL_NAME`.
3. Реализовать `build_user_profile(user)` и `build_movie_features(movie_rss)`.
4. Реализовать `recommend_movie(movie_rss, user)` с JSON-валидацией ответа Groq.
5. Привязать запуск к новым `MovieRSS` (по cron/command), вывести score в таблице.

После этого можно переходить к controlled autopilot.
