import os
from django.conf import settings


def version_processor(request):
    return {"VERSION": settings.VERSION}


def dev_banner_processor(request):
    return {"is_dev": "PyCharm" in os.environ}
