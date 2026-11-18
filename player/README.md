# player — запуск фильма во внешнем плеере (VLC)

Кнопка «Смотреть в VLC» на странице фильма открывает файл с сетевой шары
**силами клиентского компьютера**: сервер не отдаёт видео и ничего не
перекодирует, поэтому играет всё, что умеет VLC, включая 4K remux и HEVC.

## Как это работает

```text
браузер (localhost:8009 / 5173)
  → ссылка mfp://<slug>?t=<token>
  → Windows: обработчик протокола mfp (HKCU\Software\Classes\mfp)
  → powershell -File mfp-play.ps1 "mfp://<slug>?t=<token>"
  → GET http://qnap:8009/api/vault/playback-target/<slug>?t=<token>
  → {"unc_path": "\\\\qnap\\Movies\\Film.mkv", ...}
  → vlc.exe "\\\\qnap\\Movies\\Film.mkv"   (VLC читает шару сам)
```

Сервер только переводит путь «как его видит Plex» в UNC-путь «как его видит
Windows-клиент» и выдаёт короткоживущий подписанный токен (12 часов).
Путь берётся из `plex.PlexLibraryItem.file_path`, то есть нужен рабочий
Plex-синк (Plex → Vault link).

## Установка на клиенте (Windows, один раз)

1. `mfp-play.ps1` — положить, например, в `C:\Users\<user>\.tools\mfp-play.ps1`.
2. `play.reg` — поправить путь к скрипту и импортировать (двойной клик).
   Ключ пишется в `HKCU`, права администратора не нужны.
3. При первом клике по кнопке Chrome/Edge спросят разрешение на открытие
   внешнего приложения — отметить «Всегда разрешать».

Проверка вручную (окно видно, ошибки не прячутся):

```powershell
powershell -NoProfile -File C:\Users\<user>\.tools\mfp-play.ps1 "mfp://<slug>?t=<token>"
```

Токен можно взять из `playback.url` в ответе `GET /api/vault/movies/<slug>`.

## Настройка в приложении

Preferences → **Плеер**:

- «Кнопка Смотреть» — общий выключатель фичи.
- «Маппинг путей Plex → UNC» — по одному правилу на строку,
  `<префикс пути Plex> => <префикс UNC>`; выигрывает самое длинное совпадение,
  строки с `#` — комментарии. Пример для шар QNAP:

```text
/share/Movies => \\qnap\Movies
/share/Erotic => \\qnap\Erotic
/share/CACHEDEV3_DATA/Review => \\qnap\Review
/share/CACHEDEV3_DATA/TVShow => \\qnap\TVShow
/share/TVShow => \\qnap\TVShow
```

Plex внутри контейнера видит шары как `/share/<шара>` или
`/share/CACHEDEV*_DATA/<шара>`, а Windows — как `\\qnap\<шара>`.

## Диагностика

Ответы `GET /api/vault/playback-target/<slug>?t=<token>`:

- `403` — токен битый или просрочен (перезагрузить страницу фильма);
- `404` — фильм не найден;
- `409` — запуск невозможен, причина в тексте ответа: нет Plex-элемента с путём,
  путь не подходит ни под одно правило, кнопка выключена в Preferences.

Если клик по кнопке ничего не делает, а запрос к endpoint проходит — виноват
обработчик протокола: проверьте ключ `HKCU\Software\Classes\mfp` и путь к
`mfp-play.ps1` в нём.

Серверные причины видны в логе `vault.playback` (logger
`vault/services/movie_playback_service.py`).
