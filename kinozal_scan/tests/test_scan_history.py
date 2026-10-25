from unittest.mock import patch

from django.test import TestCase

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
