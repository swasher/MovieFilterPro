from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.utils import timezone

from moviefilter.models import ScanLogEntry, ScanRun
from web_logger import LogType, log, scan_log_context


class ScanHistoryPersistenceTests(TestCase):
    def setUp(self):
        self.run = ScanRun.objects.create(
            trigger=ScanRun.Trigger.MANUAL,
            status=ScanRun.Status.RUNNING,
        )

    @patch("web_logger.weblogger.send_log_to_websocket")
    def test_log_inside_context_creates_entry(self, _ws):
        with scan_log_context(self.run.id):
            log("PROCESS: Test Movie - 2025", logger_name=LogType.SCAN)

        self.assertEqual(self.run.entries.count(), 1)
        entry = self.run.entries.first()
        self.assertEqual(entry.level, ScanLogEntry.Level.INFO)
        self.assertEqual(entry.message, "PROCESS: Test Movie - 2025")

    @patch("web_logger.weblogger.send_log_to_websocket")
    def test_debug_logs_are_not_persisted(self, _ws):
        with scan_log_context(self.run.id):
            log("debug line", logger_name=LogType.DEBUG)

        self.assertEqual(self.run.entries.count(), 0)

    @patch("web_logger.weblogger.send_log_to_websocket")
    def test_log_outside_context_does_not_create_entry(self, _ws):
        log("orphan line", logger_name=LogType.SCAN)
        self.assertEqual(ScanLogEntry.objects.count(), 0)


class ScanHistoryPruneTests(TestCase):
    def test_prune_keeps_only_recent_runs(self):
        runs = []
        for _ in range(5):
            run = ScanRun.objects.create(
                trigger=ScanRun.Trigger.MANUAL,
                status=ScanRun.Status.SUCCESS,
            )
            ScanLogEntry.objects.create(run=run, level=ScanLogEntry.Level.INFO, message="x")
            runs.append(run)

        ScanRun.prune_history(max_runs=3)

        self.assertEqual(ScanRun.objects.count(), 3)
        # Каскадное удаление лог-строк вместе с запусками.
        self.assertEqual(ScanLogEntry.objects.count(), 3)


class ScanHistoryApiOrderingTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="tester", password="x")
        self.client = Client()
        self.client.force_login(self.user)

    def test_history_returns_newest_runs_first(self):
        # Регрессия: annotate() с агрегатом сбрасывает Meta.ordering, поэтому
        # порядок в /scan/history должен задаваться явно (свежие сверху).
        base = timezone.now() - timedelta(days=1)
        runs = []
        for index in range(3):
            run = ScanRun.objects.create(
                trigger=ScanRun.Trigger.MANUAL,
                status=ScanRun.Status.SUCCESS,
            )
            ScanRun.objects.filter(pk=run.pk).update(started_at=base + timedelta(hours=index))
            runs.append(run)

        response = self.client.get("/api/kinozal/scan/history?limit=10")

        self.assertEqual(response.status_code, 200)
        ids = [item["id"] for item in response.json()["items"]]
        self.assertEqual(ids, [runs[2].id, runs[1].id, runs[0].id])
