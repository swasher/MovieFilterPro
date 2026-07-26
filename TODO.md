VAULT
------

[ ] Поиск без case  
[x] Добавление/удаление фильма в пользовательские списки (на странице фильма)  
[ ] CRUD на списках: удаление, создание, переименование  
[ ] TMDB needs_user_choice показать кандидатов TMDB и дать выбрать нужный фильм через fetch_tmdb_data_confirm  
[x] Сортировка фильмов (по году, по рейтингу, по названию,по дате добавления в список)  
[?] Выбор кандидата при Fetch если их несколько; вроде сделано, но не нашел на чем протестить  

Основные пробелы, которые ещё не перенесены из `vault` в новый фронт/API:

1. Поиск фильмов отсутствует  
   Файл-источник: [vault/urls.py](C:\Users\swasher\GitHub\MovieFilterPro\vault\urls.py), [vault/views.py](C:\Users\swasher\GitHub\MovieFilterPro\vault\views.py)  
   В старом `vault` есть `SearchView` и форма поиска в sidebar. В новом фронте сейчас нет ни endpoint-а поиска, ни UI-потока `q -> список фильмов`.

2. Пользовательские списки как отдельный раздел не реализованы  
   Файл-источник: [vault/urls.py](C:\Users\swasher\GitHub\MovieFilterPro\vault\urls.py), [vault/views.py](C:\Users\swasher\GitHub\MovieFilterPro\vault\views.py), [my_lists.html](C:\Users\swasher\GitHub\MovieFilterPro\vault\templates\vault\my_lists.html)  
   Нет новых страниц/endpoint-ов для:
- `Мои списки`
- страница конкретного списка
- страница системного списка как полноценная отдельная страница
- создание списка
- редактирование списка
- удаление списка
- переключение приватности списка

3. Добавление/удаление фильма в пользовательские списки не перенесено  
   Файл-источник: [vault/views.py](C:\Users\swasher\GitHub\MovieFilterPro\vault\views.py)  
   В старом Django есть `add_to_list`, `remove_from_list`, `toggle_list_privacy`. В новом фронте на странице фильма пока есть только системные статусы и рейтинг. Работы с custom lists нет вообще.


5. Сортировка списков фильмов не перенесена  
   Файл-источник: [movie_list.html](C:\Users\swasher\GitHub\MovieFilterPro\vault\templates\vault\movie_list.html), [list_detail.html](C:\Users\swasher\GitHub\MovieFilterPro\vault\templates\vault\list_detail.html), [vault/views.py](C:\Users\swasher\GitHub\MovieFilterPro\vault\views.py)  
   В старом `vault` есть сортировка:
- по году
- по рейтингу
- по названию
- по дате добавления в список  
  В новом фронте список фильмов сейчас без сортировок.

6. Страница персоны перенесена не полностью  
   Файл-источник: [person_detail.html](C:\Users\swasher\GitHub\MovieFilterPro\vault\templates\vault\person_detail.html), [vault/views.py](C:\Users\swasher\GitHub\MovieFilterPro\vault\views.py)  
   База есть, но отсутствует важная логика старого UI:
- разделение фильмографии по ролям
- вкладки `Все / Актер / Режиссер / Продюсер`
- отдельные счётчики по ролям уже есть в API, но на фронте не используются как фильтр

7. Страница фильма ещё не умеет работать с пользовательскими списками  
   Файл-источник: [movie_detail.html](C:\Users\swasher\GitHub\MovieFilterPro\vault\templates\vault\movie_detail.html)  
   Из того, что логично ожидается для нового UI, но пока нет:
- показать, в каких пользовательских списках фильм уже находится
- добавить фильм в выбранный список
- убрать фильм из списка

8. Отдельные list-страницы во фронте отсутствуют на уровне роутинга  
   Текущее состояние фронта: [front/src/routes](C:\Users\swasher\GitHub\MovieFilterPro\front\src\routes)  
   Сейчас есть только:
- главная со списком фильмов
- фильм
- персона  
  Нет маршрутов под list-management сценарии старого `vault`.

Краткий вывод: критически не хватает именно блока `custom lists + search + TMDB candidate choice`. Остальное уже скорее развитие UI.

Предлагаю следующий порядок внедрения:
1. Поиск
2. Добавление фильма в пользовательские списки
3. Страница `Мои списки`
4. Страница конкретного списка
5. `TMDB needs_user_choice`

Если хочешь, могу следующим сообщением сразу разложить это в конкретный backlog endpoint-ов для `django-ninja`.