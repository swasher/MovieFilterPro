"""
Фоновые задачи сканирования Kinozal по расписанию.

Скан по расписанию выполняется в HUEY-воркере (отдельный процесс от web),
поэтому:
  - взаимное исключение с ручным сканом идёт через DB-флаг
    UserPreferences.scan_in_progress (атомарный захват);
  - отмена идёт через DB-флаг UserPreferences.scan_cancel_requested
    (DBCancelEvent), так как in-memory event web-процесса воркеру недоступен;
  - логи и уведомления маршрутизируются через PG-мост (bridge_mode), чтобы
    доехать до WebSocket-клиентов.
"""
from __future__ import annotations

from datetime import timedelta

from django.db import close_old_connections
from django.utils import timezone
from huey import crontab

from movie_filter_pro.huey import HUEY
from moviefilter.kinozal import CloudflareBlockedError
from moviefilter.models import ScanRun, UserPreferences
from kinozal_scan.exceptions import (
    DetailsFetchError,
    KinozalRateLimitError,
    ScanCancelled,
)
from kinozal_scan.parse import kinozal_scan
from web_logger import LogType, bridge_mode, log, scan_log_context, send_notification


class DBCancelEvent:
    """Cancel-сигнал для сканов по расписанию.

    Парсер проверяет cancel_event.is_set() в точках прерывания. В web-процессе
    это asyncio.Event в памяти, а в HUEY-воркере — этот адаптер, читающий
    DB-флаг scan_cancel_requested.
    """

    def is_set(self) -> bool:
        return bool(
            UserPreferences.objects.filter(pk=1)
            .values_list("scan_cancel_requested", flat=True)
            .first()
        )


def _should_run(prefs: UserPreferences, now) -> bool:
    """Проверяет, пора ли запускать плановый скан.

    Интервал считается от завершения предыдущего запуска (last_scheduled_run_at).
    """
    interval = prefs.scan_interval_minutes
    if not interval:
        return False
    if prefs.scan_in_progress:
        return False
    if prefs.last_scheduled_run_at:
        elapsed = now - prefs.last_scheduled_run_at
        if elapsed < timedelta(minutes=interval):
            return False
    return True


def _run_scheduled_scan(prefs: UserPreferences) -> dict:
    """Выполняет полный скан (тот же код, что и ручной запуск)."""
    # На пустой базе пользователя ещё нет — скан всё равно может выполняться
    # (user в ScanRun и фильтрах не обязателен).
    user = prefs.user
    scan_to_date = prefs.last_scan or timezone.now().date()
    cancel_event = DBCancelEvent()

    run = ScanRun.objects.create(
        trigger=ScanRun.Trigger.SCHEDULED,
        status=ScanRun.Status.RUNNING,
        scan_to_date=scan_to_date,
        user=user,
    )

    status = ScanRun.Status.RUNNING
    error_type = None
    error_message = ""
    number = 0

    log("Scheduled Kinozal scan started.", logger_name=LogType.SCAN)
    try:
        with bridge_mode():
            with scan_log_context(run.id):
                number = kinozal_scan(
                    start_page=0,
                    scan_to_date=scan_to_date,
                    user=user,
                    cancel_event=cancel_event,
                )
    except ScanCancelled:
        status = ScanRun.Status.CANCELLED
        log("Scheduled scan cancelled by user.", logger_name=LogType.SCAN)
        send_notification({
            "type": "scan_complete",
            "status": "cancelled",
            "message": "Сканирование по расписанию отменено пользователем.",
        })
    except KinozalRateLimitError as e:
        status = ScanRun.Status.RATE_LIMITED
        error_type = "KinozalRateLimitError"
        error_message = str(e)
        log(f"Scheduled scan stopped due to rate limit (429): {e}", logger_name=LogType.ERROR)
        send_notification({
            "type": "scan_complete",
            "status": "error",
            "message": "Сканирование остановлено: Kinozal ответил 429 (слишком много запросов). Прогресс сохранён.",
        })
    except CloudflareBlockedError as e:
        status = ScanRun.Status.CLOUDFLARE_BLOCKED
        error_type = "CloudflareBlockedError"
        error_message = str(e)
        log(f"Scheduled scan stopped due to Cloudflare block: {e}", logger_name=LogType.ERROR)
        send_notification({
            "type": "scan_complete",
            "status": "error",
            "message": "Сканирование остановлено: Cloudflare заблокировал доступ. Попробуй позже.",
        })
    except DetailsFetchError:
        status = ScanRun.Status.ERROR
        error_type = "DetailsFetchError"
        error_message = "Не удалось получить данные со страницы фильма."
        send_notification({
            "type": "scan_complete",
            "status": "error",
            "message": "Сканирование прервано: не удалось получить данные со страницы фильма.",
        })
    except Exception as e:
        status = ScanRun.Status.ERROR
        error_type = type(e).__name__
        error_message = str(e)
        log(f"Scheduled scan unexpected error: {e}", logger_name=LogType.ERROR)
        send_notification({
            "type": "scan_complete",
            "status": "error",
            "message": f"Произошла непредвиденная ошибка: {e}",
        })
    else:
        status = ScanRun.Status.SUCCESS
        send_notification({
            "type": "scan_complete",
            "status": "success",
            "message": f"Added {number} movies.",
        })

    ScanRun.objects.filter(pk=run.id).update(
        status=status,
        finished_at=timezone.now(),
        new_movies_count=number,
        error_type=error_type,
        error_message=error_message,
    )
    UserPreferences.objects.filter(pk=1).update(
        last_scheduled_run_at=timezone.now(),
        last_scheduled_status=status,
    )
    ScanRun.prune_history()
    return {"status": status}


@HUEY.periodic_task(crontab(minute="*"))
def kinozal_scheduled_scan_tick():
    """Тик планировщика (каждую минуту): запускает скан, если пора и свободно."""
    close_old_connections()
    prefs = UserPreferences.get()
    now = timezone.now()

    if not _should_run(prefs, now):
        return None

    # Атомарный захват: только один воркер/поток выигрывает, остальные пропускают.
    claimed = UserPreferences.objects.filter(pk=1, scan_in_progress=False).update(
        scan_in_progress=True,
        scan_cancel_requested=False,
    )
    if not claimed:
        return None

    try:
        return _run_scheduled_scan(prefs)
    finally:
        UserPreferences.objects.filter(pk=1).update(
            scan_in_progress=False,
            scan_cancel_requested=False,
        )
