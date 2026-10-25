import asyncio
from datetime import date

from django.utils import timezone

from .runtime import executor, tasks, cancel_events
from .parse import kinozal_scan
from .exceptions import DetailsFetchError, ScanCancelled, KinozalRateLimitError
from moviefilter.kinozal import CloudflareBlockedError
from moviefilter.models import ScanRun, UserPreferences
from web_logger import alog, LogType, asend_notification, scan_log_context


def _run_scan(start_page: int, scan_to_date: date, user, cancel_event, run_id: int):
    """Выполняет скан внутри scan_log_context, чтобы log() писал ScanLogEntry."""
    with scan_log_context(run_id):
        return kinozal_scan(start_page, scan_to_date, user, cancel_event)


async def start_scan_task(task_id: str, start_page: int, scan_to_date: date, user, run_id: int):
    cancel_event = asyncio.Event()
    cancel_events[task_id] = cancel_event

    loop = asyncio.get_running_loop()

    async def runner():
        status = ScanRun.Status.RUNNING
        error_type = None
        error_message = ""
        number_of_new_movies = 0

        try:
            number_of_new_movies = await loop.run_in_executor(
                executor,
                _run_scan,
                start_page,
                scan_to_date,
                user,
                cancel_event,
                run_id,
            )
        except ScanCancelled:
            # Если отменили вручную, просто выходим, не отправляя уведомлений
            status = ScanRun.Status.CANCELLED
            await alog("Scan cancelled by user.", logger_name=LogType.SCAN)
        except KinozalRateLimitError as e:
            # 429 от Kinozal: не долбим забаненный сайт, скан остановлен.
            # Прогресс сохранён чекпойнтом — следующий запуск продолжит с места остановки.
            status = ScanRun.Status.RATE_LIMITED
            error_type = "KinozalRateLimitError"
            error_message = str(e)
            await alog(f"Scan stopped due to Kinozal rate limit (429): {e}", logger_name=LogType.ERROR)
            await asend_notification({
                'type': 'scan_complete',
                'status': 'error',
                'message': 'Сканирование остановлено: Kinozal ответил 429 (слишком много запросов). Прогресс сохранён — подожди и запусти скан позже.'
            })
        except CloudflareBlockedError as e:
            # Cloudflare не пропустил даже после браузерной эскалации. Обычно это
            # репутация IP на данный момент — ретраи в это окно бесполезны.
            status = ScanRun.Status.CLOUDFLARE_BLOCKED
            error_type = "CloudflareBlockedError"
            error_message = str(e)
            await alog(f"Scan stopped due to Cloudflare block: {e}", logger_name=LogType.ERROR)
            await asend_notification({
                'type': 'scan_complete',
                'status': 'error',
                'message': 'Сканирование остановлено: Cloudflare заблокировал доступ (обход не помог). Попробуй позже или смени IP-адрес.'
            })
        except DetailsFetchError:
            # Эта ошибка уже залогирована на более низком уровне.
            # Здесь мы просто сообщаем пользователю о проблеме.
            status = ScanRun.Status.ERROR
            error_type = "DetailsFetchError"
            error_message = "Не удалось получить данные со страницы фильма."
            await asend_notification({
                'type': 'scan_complete',
                'status': 'error',
                'message': 'Сканирование прервано. Не удалось получить данные со страницы фильма. Возможно, сайт недоступен или IP заблокирован.'
            })
        except Exception as e:
            # Ловим любые другие непредвиденные ошибки
            status = ScanRun.Status.ERROR
            error_type = type(e).__name__
            error_message = str(e)
            await alog(f'An unexpected error occurred in the scan task: {e}', logger_name=LogType.ERROR)
            await asend_notification({
                'type': 'scan_complete',
                'status': 'error',
                'message': f'Произошла непредвиденная ошибка: {e}'
            })
        else:
            # Логика, которая раньше была в `else` блока try/except во view
            status = ScanRun.Status.SUCCESS
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

            # Финализируем ScanRun (статус, завершение, счётчик, ошибка).
            def finalize_run():
                ScanRun.objects.filter(pk=run_id).update(
                    status=status,
                    finished_at=timezone.now(),
                    new_movies_count=number_of_new_movies,
                    error_type=error_type,
                    error_message=error_message,
                )

            # Снимаем DB-флаг scan_in_progress, чтобы планировщик по расписанию
            # (HUEY) видел, что ручной скан завершился. Заодно чистим запрос отмены.
            def clear_flags():
                UserPreferences.objects.filter(pk=1).update(
                    scan_in_progress=False,
                    scan_cancel_requested=False,
                )

            try:
                await loop.run_in_executor(executor, finalize_run)
            except Exception:
                pass

            # Ограничиваем историю запусков (удаляем слишком старые).
            try:
                await loop.run_in_executor(executor, ScanRun.prune_history)
            except Exception:
                pass

            try:
                await loop.run_in_executor(executor, clear_flags)
            except Exception:
                # Очистка флага не должна ронять завершение задачи.
                pass

    task = asyncio.create_task(runner())
    tasks[task_id] = task
