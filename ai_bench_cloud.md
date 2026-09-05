Запрос на рефактор:

dots3-note - хоть как-то вник, но не нашел проблем
Inkinkg - не стал даже вникать
Muse Spark - очень подробный ответ со всеми граблями, наверно самый лучший.
DeepSeekV4 Flash - нашел все проблемы, задал вопросы
North MiniCode - вообще ничего не нашел, сказал "все ок, можно делать"
Nemotron 3 Ultra Free - не нашел проблем
Ling 3.0 Flash Fin - не нашел проблем
MiMo 2.5 - вникал, но проблем не увидел
Laguna S 2.1 - никаких проблем не увидел



### Тесты AI

**1. Симптом - LOW приоритет живет своей жизнью**

> Что-то странное с низким приоритетом. Я настраиваю отдельно списки для обычного и для низкого приоритета (страны, жанры там и т.д.), а ощущение что низкий вообще игнорит свои настройки и берет что-то от обычного. Если основные фильтры очистить - низкий тоже ломается. Проверь логику приоритетов, будто там перепутаны поля.

Ответ: 

Проверяет `if self.countries`/`if self.genres` вместо `low_*`

    def get_low_priority_preferences(self):
        countries = self.low_countries.split(', ') if self.countries else [] # BUG: должно быть self.low_countries
        genres = self.low_genres.split(', ') if self.genres else []           # BUG: должно быть self.low_genres

Если countries="", а low_countries заполнено — вернет []. И наоборот даст ['']. Ломает всю двух-уровневую систему в kinozal_scan/checks.py:97.

dots3-note - 
Inkinkg - 
Muse Spark 1.2 - 
Muse Spark 1.3 - 
DeepSeekV4 Flash - 
North MiniCode - 
Nemotron 3 Ultra Free - 
Nemotron 3.5 Lighting - 
Ling 3.0 Flash Fin - 
MiMo 2.5 - 
Laguna S 2.1 - 



**2. Подозрение - фильтр по жанрам будто выключен**
> Заметил что фильтр по странам работает, а по жанрам - нет. Ставлю "Мюзикл" / "Ужасы" в стоп-лист, а они всё равно пролетают и в HIGH и в LOW ленту, хотя по странам такие же стоп-слова отлично отсекают. Может фильтр по жанрам вообще не применяется? Глянь на всякий случай.

Ответ:

Что на самом деле: kinozal_scan/checks.py:113

genre_intersection = set(m.genres) & set(stop_genres) # BUG

    # m.genres = "Драма, Комедия" -> set("Драма, Комедия") = {'Д','р','а',',',' '} - множество символов!
    # правильно: set(m.genres.split(', ')) & set(stop_genres) как сделано для countries строкой выше

Фильтр никогда не срабатывает, весь genres/low_genres из UserPreferences игнорируется.





**3. Проверка на всякий случай - дубли и странности скана**
> Иногда после скана в ленте появляются дубли одного и того же фильма, хотя дедупликация должна быть. На локалке с sqlite не видел, а на проде с postgres бывает. Еще переход "жду дубляж" -> "найден дубляж" не всегда срабатывает, особенно для сборников где год указан диапазоном типа `1982-1994`. И если быстро два раза запустить скан - риск дублей выше. Глянь, всё ли ок с дедупликацией и записью в этом месте.

Что на самом деле: kinozal_scan/parse.py:476-482, 532-536, 76-103

1. year__in=[int(y) for y in ...] — MovieRSS.year это CharField, на postgres varchar = integer не матчится → предзагрузка пустая → дубли.

2. Q(title__in=...) | Q(original_title__in=...) + year__in — это декартово произведение, а ключ dict — точный кортеж (title,original_title,year). False positive/negative.

3. for m in movies: get_or_create(...) без transaction.atomic и без UniqueConstraint(title,original_title,year) — гонка при двух параллельных сканах + year_str_for_check = m.year[:4] vs filter(year=m.year) для 1982-1994 — TRANS_FOUND не сработает.



---
### Шпаргалка для себя (куда на самом деле смотреть)

2. `kinozal_scan/checks.py:113` `set(m.genres)` - множество символов вместо `set(m.genres.split(', '))`
3. `kinozal_scan/parse.py:476-482` `year__in=[int(y)...]` vs `CharField` + картезианский `Q(title__in) | Q(original__in)` + нет `UniqueConstraint` и `transaction.atomic` в `kinozal_scan:76-103`

---
### Бонусные в блокнотик (архитектурные, тоже надо разобрать)

* **Синглтон KinozalClient** `moviefilter/kinozal/kinozal_client.py:158-196` - кэширует `domain/cookies` навсегда, смена домена в настройках не инвалидирует клиента без рестарта.
* **NPE на актерах/жанрах** `kinozal_scan/parse.py:330` `m.actors = ['']` (list) + `moviefilter/models.py:70-80` `actors_as_list -> self.actors.split()` - упадет на фильмах без блока "В ролях:", аналогично `genres/countries` могут быть `None`.
* **Глобальные dict в сигналах** `vault/signals.py:16,34` + `vault/services/tmdb_writeback_dispatch.py:35` - `_pending_*` без `Lock`, `pop` + `on_commit` теряют diff при быстрых кликах/rollback.
* **Спавн потоков на каждый постер** `moviefilter/image_caching.py:277` - на каждый `GET /api/kinozal/movies` без кэша стартует `Thread`, при скролле на 50+ фильмов - сотни daemon-потоков без пула/семафора.