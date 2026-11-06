import uuid
from ninja import Router
from django.db.models import Count
from django.http import HttpResponse
from asgiref.sync import async_to_sync
from moviefilter.models import ScanRun, UserPreferences
from .service import start_scan_task
from .runtime import tasks, cancel_events

router = Router()


@router.post("/start")
def start_scan(request):
    if not request.user.is_authenticated:
        return HttpResponse("Unauthorized", status=401)

    # Взаимное исключение с планировщиком по расписанию: атомарно занимаем
    # флаг scan_in_progress. Если уже идёт скан (ручной или плановый) — 409.
    claimed = UserPreferences.objects.filter(pk=1, scan_in_progress=False).update(
        scan_in_progress=True,
        scan_cancel_requested=False,
    )
    if not claimed:
        return HttpResponse("Scan already in progress", status=409)

    pref = UserPreferences.get()
    task_id = uuid.uuid4().hex
    user = request.user

    run = ScanRun.objects.create(
        trigger=ScanRun.Trigger.MANUAL,
        status=ScanRun.Status.RUNNING,
        scan_to_date=pref.last_scan,
        user=user,
    )
    
    async_to_sync(start_scan_task)(
        task_id=task_id,
        start_page=0,
        scan_to_date=pref.last_scan,
        user=user,
        run_id=run.id,
    )
    
    return {"task_id": task_id}


@router.post("/cancel/{task_id}")
def cancel_scan(request, task_id: str):
    if not request.user.is_authenticated:
        return HttpResponse("Unauthorized", status=401)
        
    from web_logger import log, LogType
    log('Scan cancellation request received.', logger_name=LogType.SCAN)

    # DB-флаг отмены нужен для сканов по расписанию (HUEY-воркер читает его,
    # так как не имеет доступа к in-memory event web-процесса).
    UserPreferences.objects.filter(pk=1).update(scan_cancel_requested=True)

    event = cancel_events.get(task_id)
    if event:
        event.set()

    task = tasks.get(task_id)
    if task:
        task.cancel()

    return HttpResponse(status=204)


@router.get("/status")
def get_scan_status(request):
    if not request.user.is_authenticated:
        return HttpResponse("Unauthorized", status=401)
        
    active_task_ids = list(tasks.keys())
    prefs = UserPreferences.get()
    return {
        "is_scanning": len(active_task_ids) > 0 or prefs.scan_in_progress,
        "active_task_ids": active_task_ids,
        "scan_in_progress": prefs.scan_in_progress,
        "last_scheduled_run_at": prefs.last_scheduled_run_at.isoformat() if prefs.last_scheduled_run_at else None,
        "last_scheduled_status": prefs.last_scheduled_status,
    }


def _serialize_run(run: ScanRun, entries_count: int | None = None) -> dict:
    data = {
        "id": run.id,
        "trigger": run.trigger,
        "status": run.status,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "scan_to_date": run.scan_to_date.isoformat() if run.scan_to_date else None,
        "new_movies_count": run.new_movies_count,
        "error_type": run.error_type,
        "error_message": run.error_message or "",
    }
    if entries_count is not None:
        data["entries_count"] = entries_count
    return data


@router.get("/history")
def scan_history(request, limit: int = 50):
    if not request.user.is_authenticated:
        return HttpResponse("Unauthorized", status=401)

    bounded = max(1, min(limit, 200))
    # ВАЖНО: при annotate() с агрегатом Django сбрасывает Meta.ordering (чтобы не добавлять
    # поля сортировки в GROUP BY), поэтому порядок задаём явно: свежие запуски — сверху.
    runs = ScanRun.objects.annotate(entries_count=Count("entries")).order_by(
        "-started_at", "-id"
    )[:bounded]
    return {"items": [_serialize_run(run, entries_count=run.entries_count) for run in runs]}


@router.get("/history/{run_id}")
def scan_history_detail(request, run_id: int):
    if not request.user.is_authenticated:
        return HttpResponse("Unauthorized", status=401)

    run = ScanRun.objects.filter(pk=run_id).first()
    if run is None:
        return HttpResponse("Not found", status=404)

    entries = run.entries.all()
    return {
        "run": _serialize_run(run, entries_count=len(entries)),
        "entries": [
            {
                "id": entry.id,
                "level": entry.level,
                "message": entry.message,
                "created_at": entry.created_at.isoformat() if entry.created_at else None,
            }
            for entry in entries
        ],
    }
