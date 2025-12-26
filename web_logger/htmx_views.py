import os
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse
from django.conf import settings


@login_required
def get_log(request, log_type):
    """
    Reads and returns the content of a specified log file.

    Args:
        request: The HTTP request object.
        log_type: The type of log ('error', 'debug', or 'scan').

    Returns:
        An HTTP response with the log file content.
    """
    log_file_map = {
        'error': 'error.log',
        'debug': 'debug.log',
        'scan': 'scan.log',
        # 'full': 'full.log',
        # 'short': 'short.log',
    }

    if log_type not in log_file_map:
        return HttpResponse(f"Invalid log type: {log_type}", status=400)

    log_filename = log_file_map[log_type]
    log_filepath = os.path.join(settings.BASE_DIR, 'logs', log_filename)

    if not os.path.exists(log_filepath):
        return HttpResponse(f"Log file not found: {log_filename}", status=404)

    try:
        with open(log_filepath, 'r') as f:
            log_content = f.read()
    except Exception as e:
        return HttpResponse(f"Error reading log file: {e}", status=500)

    return HttpResponse(log_content, content_type="text/plain")


@login_required()
def clear_log(request):
    log_type = request.GET.get('inlineRadioOptions')
    log_file_map = {
        'scan': settings.SCAN_LOG,
        'debug': settings.DEBUG_LOG,
        'error': settings.ERROR_LOG,
    }

    if log_type not in log_file_map:
        messages.error(request, f"Invalid log type: {log_type}")
        return HttpResponse(f"Invalid log type: {log_type}", status=400)

    log_file = log_file_map[log_type]
    print('log_file', log_file)

    try:
        if os.path.exists(log_file):
            with open(log_file, 'r+') as file:
                file.truncate(0)
        messages.success(request, 'Clear success!')
        return HttpResponse(status=200)
    except Exception as e:
        messages.error(request, f"Ошибка при очистке логов: {e}")
        return HttpResponse(status=500)
