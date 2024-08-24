from django import template
from pathlib import PurePath

register = template.Library()


@register.filter
def cutfilename(value):
    return PurePath(value).name
