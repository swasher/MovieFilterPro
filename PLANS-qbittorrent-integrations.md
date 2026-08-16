Идеи и что вообще можно сделать:

[ ] На каждом фильме в Vault должен быть значек: 
    - Фильм ЕСТЬ в qbittorrent
    - Фильм СКАЧИВАЕТСЯ в данный момент в qbittorrent
    - Фильма НЕТ в qbittorrent

[ ] Если фильм СКАЧИВАЕТСЯ, то на карточке отображается прогресс (Скачивается: 68% • 12 МБ/с • Осталось 4 мин)

[ ] Для сериалов сразу включать флаг "Sequential download"

[ ] При установке отметки "ПРОСМОТРЕНО" предлагать удалить файл из qbittorrent

[ ] Сделать добавление торрентов через API - тогда будет привязка по тегу между фильмом в Vault и торрентом в qbitttorent.

===========================

Реализация:

- есть готовая либа - uv add qbittorrent-api

Пример:

```python
from qbittorrentapi import Client
qbt_client = Client(host='http://localhost:8080', username='admin', password='your_password')
```

# Добавить торрент

```python
from qbittorrentapi import Client

qbt_client = Client(host='http://localhost:8080', username='admin', password='your_password')

# Добавить торрент
qbt_client.torrents_add(
    urls='magnet:?xt=urn:btih:...',
    category='movies',
    is_sequential_download=True
)

# Получить список активных скачек
downloading = qbt_client.torrents_info(status_filter='downloading')
```

Обновление статусов в реальном времени:
------------------------------------

Простой вариант: Svelte делает long-polling или короткие опросы (fetch) раз в 3–5 секунд.

Продвинутый вариант: Использовать Django Channels (WebSockets) или Server-Sent Events (SSE), чтобы Django сам стримил текущий прогресс скачивания на Svelte-фронтен