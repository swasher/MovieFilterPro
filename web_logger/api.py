import os
from ninja import Router
from django.http import HttpResponse
from django.conf import settings

router = Router()


@router.get("/{log_type}")
def get_log(request, log_type: str):
    if not request.user.is_authenticated:
        return HttpResponse("Unauthorized", status=401)
        
    log_file_map = {
        'error': 'error.log',
        'debug': 'debug.log',
        'scan': 'scan.log',
    }

    if log_type not in log_file_map:
        return HttpResponse(f"Invalid log type: {log_type}", status=400)

    log_filename = log_file_map[log_type]
    log_filepath = os.path.join(settings.BASE_DIR, 'logs', log_filename)

    if not os.path.exists(log_filepath):
        return HttpResponse(f"Log file not found: {log_filename}", status=404)

    try:
        with open(log_filepath, 'r', encoding='utf-8') as f:
            log_content = f.read()
    except Exception as e:
        return HttpResponse(f"Error reading log file: {e}", status=500)

    return HttpResponse(log_content, content_type="text/plain")


@router.delete("/{log_type}")
def clear_log(request, log_type: str):
    if not request.user.is_authenticated:
        return HttpResponse("Unauthorized", status=401)
        
    log_file_map = {
        'scan': settings.SCAN_LOG,
        'debug': settings.DEBUG_LOG,
        'error': settings.ERROR_LOG,
    }

    if log_type not in log_file_map:
        return HttpResponse(f"Invalid log type: {log_type}", status=400)

    log_file = log_file_map[log_type]

    try:
        if os.path.exists(log_file):
            with open(log_file, 'r+') as file:
                file.truncate(0)
        return {"status": "success"}
    except Exception as e:
        return HttpResponse(f"Ошибка при очистке логов: {e}", status=500)
