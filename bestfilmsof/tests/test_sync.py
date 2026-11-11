from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from bestfilmsof.models import (
    BestfilmsCache,
    BestfilmsEntry,
    BestfilmsGenreYear,
    BestfilmsSync,
)
from bestfilmsof.services.sync_service import SyncService


def raw_movie(imdb_id, tmdb_id, title, score=10.0, position_components=None):
    components = position_components or {}
    return {
        "imdb_id": imdb_id,
        "primary_title": title,
        "weighted_score": score,
        "average_rating": 7.5,
        "num_votes": 1234,
        "tomato_meter": 80,
        "metascore": 70,
        "gross": 1000000,
        "gross_scope": "worldwide",
        "oscar_wins": 1,
        "oscar_nominations": 2,
        "best_picture": False,
        "award_points": 5,
        "awards_wins": 3,
        "awards_nominations": 4,
        "other_awards": [],
        "imdb_component": components.get("imdb"),
        "critics_component": components.get("critics"),
        "awards_component": components.get("awards"),
        "boxoffice_component": components.get("boxoffice"),
        "critics_fallback": components.get("critics_fallback"),
        "boxoffice_fallback": components.get("boxoffice_fallback"),
        "metadata": {
            "id": tmdb_id,
            "title": title,
            "overview": f"{title} overview",
            "poster_path": f"/{tmdb_id}.jpg",
            "release_date": "2010-01-01",
        },
    }


def page(movies):
    return {
        "movies": movies,
        "pagination": {"page": 1, "limit": 50, "total": len(movies), "totalPages": 1},
    }


def client_factory(pages, summary=None):
    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def close(self):
            pass

        def fetch_page(self, year, genre=None, page=1, limit=50):
            return pages[page - 1]

        def fetch_genre_summary(self, genre):
            return summary or {"genre": genre, "years": []}

    return FakeClient


@patch("bestfilmsof.services.sync_service._enqueue_russian_backfill")
class SyncServiceTests(TestCase):
    def _run(self, year, genre, pages, summary=None, force=True):
        claimed, row, token = SyncService.claim(year, genre, force=force)
        self.assertTrue(claimed)
        with patch(
            "bestfilmsof.services.sync_service.BestfilmsofClient",
            client_factory(pages, summary),
        ):
            return SyncService.run_claimed(year, genre, token)

    def test_list_sync_creates_entries_and_cache(self, _enqueue):
        pages = [
            page(
                [
                    raw_movie("tt1", 101, "First"),
                    raw_movie("tt2", 102, "Second"),
                ]
            )
        ]
        result = self._run(2010, "drama", pages)

        self.assertEqual(result["status"], "ok")
        self.assertEqual(BestfilmsEntry.objects.count(), 2)
        self.assertEqual(BestfilmsCache.objects.count(), 2)
        self.assertEqual(
            list(
                BestfilmsEntry.objects.order_by("position").values_list(
                    "imdb_id", flat=True
                )
            ),
            ["tt1", "tt2"],
        )
        row = BestfilmsSync.objects.get(key="list:2010:drama")
        self.assertEqual(row.status, BestfilmsSync.Status.IDLE)
        self.assertIsNotNone(row.synced_at)
        self.assertEqual(row.last_stats["entries_created"], 2)

    def test_list_sync_is_incremental(self, _enqueue):
        self._run(2010, "drama", [page([raw_movie("tt1", 101, "First")])])
        self._run(
            2010,
            "drama",
            [page([raw_movie("tt1", 101, "First changed", score=20.0)])],
        )

        entry = BestfilmsEntry.objects.get(imdb_id="tt1")
        self.assertEqual(entry.title, "First changed")
        self.assertEqual(entry.score, 20.0)
        row = BestfilmsSync.objects.get(key="list:2010:drama")
        self.assertEqual(row.last_stats["entries_created"], 0)
        self.assertEqual(row.last_stats["entries_updated"], 1)
        self.assertEqual(row.last_stats["entries_deleted"], 0)

    def test_list_sync_deletes_stale_entries(self, _enqueue):
        self._run(
            2010,
            "drama",
            [
                page(
                    [
                        raw_movie("tt1", 101, "First"),
                        raw_movie("tt2", 102, "Second"),
                    ]
                )
            ],
        )
        self._run(2010, "drama", [page([raw_movie("tt1", 101, "First")])])

        self.assertEqual(
            list(BestfilmsEntry.objects.values_list("imdb_id", flat=True)), ["tt1"]
        )
        row = BestfilmsSync.objects.get(key="list:2010:drama")
        self.assertEqual(row.last_stats["entries_deleted"], 1)

    def test_genre_summary_sync(self, _enqueue):
        summary = {
            "genre": "drama",
            "years": [
                {
                    "year": 2010,
                    "count": 282,
                    "movie": raw_movie("tt1", 101, "Top film", score=55.5),
                },
                {
                    "year": 2009,
                    "count": 200,
                    "movie": raw_movie("tt2", 102, "Older top"),
                },
            ],
        }
        result = self._run(None, "drama", [], summary=summary)

        self.assertEqual(result["status"], "ok")
        self.assertEqual(BestfilmsGenreYear.objects.count(), 2)
        self.assertEqual(BestfilmsCache.objects.count(), 2)
        row = BestfilmsSync.objects.get(key="summary:drama")
        self.assertEqual(row.status, BestfilmsSync.Status.IDLE)
        self.assertEqual(row.last_stats["years_created"], 2)

    def test_stale_claim_is_rejected(self, _enqueue):
        self._run(2010, "drama", [page([raw_movie("tt1", 101, "First")])])
        claimed, row, _ = SyncService.claim(2010, "drama", force=False)
        self.assertFalse(claimed)
        self.assertEqual(row.synced_at is not None, True)

    def test_duplicate_task_with_old_token_is_skipped(self, _enqueue):
        claimed, row, token = SyncService.claim(2010, "drama", force=True)
        self.assertTrue(claimed)
        result = SyncService.run_claimed(2010, "drama", "deadbeef")
        self.assertEqual(result["status"], "skipped")

    def test_error_cooldown_blocks_auto_retry_but_not_force(self, _enqueue):
        BestfilmsSync.objects.create(
            key="list:2010:drama",
            year=2010,
            genre="drama",
            status=BestfilmsSync.Status.ERROR,
            finished_at=timezone.now(),
        )
        claimed, _, _ = SyncService.claim(2010, "drama", force=False)
        self.assertFalse(claimed)

        claimed, _, token = SyncService.claim(2010, "drama", force=True)
        self.assertTrue(claimed)
        self.assertTrue(token)

    def test_queued_task_is_requeued_after_pickup_timeout(self, _enqueue):
        claimed, row, first_token = SyncService.claim(2010, "drama", force=True)
        self.assertTrue(claimed)

        BestfilmsSync.objects.filter(pk=row.pk).update(
            started_at=timezone.now() - timedelta(seconds=61),
            worker_started_at=None,
        )
        claimed, row, second_token = SyncService.claim(2010, "drama", force=False)
        self.assertTrue(claimed)
        self.assertNotEqual(first_token, second_token)
        self.assertIsNone(row.worker_started_at)

    def test_running_worker_is_not_reclaimed(self, _enqueue):
        claimed, row, _ = SyncService.claim(2010, "drama", force=True)
        self.assertTrue(claimed)
        BestfilmsSync.objects.filter(pk=row.pk).update(
            worker_started_at=timezone.now(),
            started_at=timezone.now() - timedelta(hours=1),
        )
        claimed, _, _ = SyncService.claim(2010, "drama", force=True)
        self.assertFalse(claimed)
