import uuid
from ninja import Router
from django.http import HttpResponse
from asgiref.sync import async_to_sync
from moviefilter.models import UserPreferences
from .service import start_scan_task
from .runtime import tasks, cancel_events

router = Router()


@router.post("/start")
def start_scan(request):
    if not request.user.is_authenticated:
        return HttpResponse("Unauthorized", status=401)
        
    pref = UserPreferences.get()
    task_id = uuid.uuid4().hex
    user = request.user
    
    async_to_sync(start_scan_task)(
        task_id=task_id,
        start_page=pref.scan_from_page or 0,
        scan_to_date=pref.last_scan,
        user=user,
    )
    
    return {"task_id": task_id}


@router.post("/cancel/{task_id}")
def cancel_scan(request, task_id: str):
    if not request.user.is_authenticated:
        return HttpResponse("Unauthorized", status=401)
        
    from web_logger import log, LogType
    log('Scan cancellation request received.', logger_name=LogType.SCAN)

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
    return {
        "is_scanning": len(active_task_ids) > 0,
        "active_task_ids": active_task_ids
    }
