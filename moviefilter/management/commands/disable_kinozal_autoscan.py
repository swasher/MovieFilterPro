from django.core.management.base import BaseCommand

from moviefilter.models import UserPreferences


class Command(BaseCommand):
    help = "Disable scheduled Kinozal scan (set scan_interval_minutes to None) in UserPreferences."

    def handle(self, *args, **options):
        prefs = UserPreferences.get()
        if prefs.scan_interval_minutes is None:
            self.stdout.write(self.style.SUCCESS("Scheduled Kinozal scan is already disabled."))
            return
        prefs.scan_interval_minutes = None
        prefs.save(update_fields=["scan_interval_minutes"])
        self.stdout.write(self.style.SUCCESS("Scheduled Kinozal scan disabled (scan_interval_minutes=None)."))