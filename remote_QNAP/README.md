Mappings
------------
Эти маппинги можно прописать в настройках Pycharm, и тогда можно будет заливать файлы одним нажатием deployment.

C:\Users\<user>\GitHub\MovieFilterPro\remote_QNAP\webhook -> /share/CACHEDEV1_DATA/homes/swasher/webhook
C:\Users\<user>\GitHub\MovieFilterPro\remote_QNAP\init.d -> /share/CACHEDEV1_DATA/.qpkg/RunLast/init.d

Файл `docker-compose.yml` мы не можем непосредственно заливать на QNAP, потому что Container Station так 
не понимает - файл `docker-compose.yml` нужно менять только через его web-интерфейс.

База
--------------------

Сама база SQLite лежит в `share/homes/swasher/PERSISTENT_VOLUME`.
Эта папка монтируется в контейнер, это задается в `docker-compose.yml`




Hotfolder
----------------------------

В контейнере создается горячая папка для торрентов, `\torrents_hotfolder`. Ее так же нужно установить в настройках
Movie-filter-pro, чтобы в нее скачивались торренты, а битторрент клиент должен, соотв., использовать ее как горячую папку для входящих.

Миграции
------------------

Чтобы применить новые миграции базы данных, проект специально для этого запускается через `entrypoint.sh`.
Этот файл нужен для того, чтобы ПОСЛЕ обновления образа и запуска контейнера, но ДО запуска gunicorn мы могли запустить миграции.

Логи
--------------------

tail -f /share/CACHEDEV1_DATA/homes/swasher/webhook/initd.log
tail -f /share/CACHEDEV1_DATA/homes/swasher/webhook/webhook.log

Команды docker
---------------------

### Попасть внутрь запущенного контейнера

    docker exec -it movie-filter-pro /bin/sh

### Запустить образ и зайти в него 

    docker run -it --entrypoint /bin/sh swasher/movie-filter-pro:armv7

### Логи

    docker ps -a
    docker logs <container_id>
