Эти маппинги можно прописать в настройках Pycharm, и тогда можно будет заливать файлы одним нажатием deployment.

C:\Users\<user>\GitHub\MovieFilterPro\remote_QNAP\webhook -> /share/CACHEDEV1_DATA/homes/swasher/webhook
C:\Users\<user>\GitHub\MovieFilterPro\remote_QNAP\init.d -> /share/CACHEDEV1_DATA/.qpkg/RunLast/init.d

Файл `docker-compose.yml` мы не можем непосредственно заливать на QNAP, потому что Container Station так 
не понимает - файл `docker-compose.yml` нужно менять только через его web-интерфейс.

Сама база SQLite лежит в `share/homes/swasher/PERSISTENT_VOLUME`.

Попасть внурь контейнера

    docker exec -it movie-filter-pro /bin/sh

В контейнере создается горячая папка для торрентов, `\torrents_hotfolder`. Ее так же нужно установить в настройках
Movie-filter-pro, чтобы в нее скачивались торренты, а битторрент клиент должен, соотв., использовать ее как горячую папку для входящих.

`entrypoint.sh` нужен для того, чтобы ПОСЛЕ обновления образа и запуска контейнера, но ДО запуска gunicorn мы могли запустить миграции.
