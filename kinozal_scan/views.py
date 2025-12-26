from django.shortcuts import render
from django.utils import timezone


def scan_page(request):
    return render(request, 'scan_page.html')


def deleting_page(request):
    return render(request, 'deleting.html', {'today': timezone.now()})
