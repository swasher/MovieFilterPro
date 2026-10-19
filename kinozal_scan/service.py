import asyncio
from datetime import date

from .runtime import executor, tasks, cancel_events
from .parse import kinozal_scan
from .exceptions import DetailsFetchError, ScanCancelled, KinozalRateLimitError
from moviefilter.models import UserPreferences
from web_logger import alog, LogType, asend_notification


async def start_scan_task(task_id: str, start_page: int, scan_to_date: date, user):
    cancel_event = asyncio.Event()
    cancel_events[task_id] = cancel_event

    loop = asyncio.get_running_loop()

    async def runner():
        try:
            number_of_new_movies = await loop.run_in_executor(
                executor,
                kinozal_scan,
                start_page,
                scan_to_date,
                user,
                cancel_event,
            )
        except ScanCancelled:
            # Если отменили вручную, просто выходим, не отправляя уведомлений
            await alog("Scan cancelled by user.", logger_name=LogType.SCAN)
        except KinozalRateLimitError as e:
            # 429 от Kinozal: не долбим забаненный сайт, скан остановлен.
            # Прогресс сохранён чекпойнтом — следующий запуск продолжит с места остановки.
            await alog(f"Scan stopped due to Kinozal rate limit (429): {e}", logger_name=LogType.ERROR)
            await asend_notification({
                'type': 'scan_complete',
                'status': 'error',
                'message': 'Сканирование остановлено: Kinozal ответил 429 (слишком много запросов). Прогресс сохранён — подожди и запусти скан позже.'
            })
        except DetailsFetchError:
            # Эта ошибка уже залогирована на более низком уровне.
            # Здесь мы просто сообщаем пользователю о проблеме.
            await asend_notification({
                'type': 'scan_complete',
                'status': 'error',
                'message': 'Сканирование прервано. Не удалось получить данные со страницы фильма. Возможно, сайт недоступен или IP заблокирован.'
            })
        except Exception as e:
            # Ловим любые другие непредвиденные ошибки
            await alog(f'An unexpected error occurred in the scan task: {e}', logger_name=LogType.ERROR)
            await asend_notification({
                'type': 'scan_complete',
                'status': 'error',
                'message': f'Произошла непредвиденная ошибка: {e}'
            })
        else:
            # Логика, которая раньше была в `else` блока try/except во view
            await alog(f"Scan complete, new entries: {number_of_new_movies}", logger_name=LogType.SCAN)

            def db_update():
                pref = UserPreferences.get()
                pref.scan_from_page = None
                pref.save(update_fields=['scan_from_page'])

            # Обновляем UserPreferences в синхронном исполнителе, чтобы избежать проблем с Django ORM
            await loop.run_in_executor(
                executor,
                db_update
            )

            await asend_notification({
                'type': 'scan_complete',
                'status': 'success',
                'message': f'Added {number_of_new_movies} movies.'
            })
        finally:
            # cleanup
            cancel_events.pop(task_id, None)
            tasks.pop(task_id, None)

    task = asyncio.create_task(runner())
    tasks[task_id] = task
