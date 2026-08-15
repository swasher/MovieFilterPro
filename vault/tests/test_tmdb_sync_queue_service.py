from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase

from moviefilter.models import UserPreferences
from vault.models import Movie, TMDBSyncQueueItem
from vault.services.tmdb_movie_matching_service import TMDBCandidate
from vault.services.tmdb_movie_sync_service import TMDBSyncResult, TMDBMovieSyncService
from vault.services.tmdb_sync_queue_service import TMDBSyncQueueService


def _candidate(tmdb_id: int):
    return TMDBCandidate(
        tmdb_id=tmdb_id,
        media_type="movie",
        title=f"Title {tmdb_id}",
        original_title=f"Original {tmdb_id}",
        year=2010,
        score=10,
        score_reasons=("auto",),
        poster_path=None,
        popularity=None,
        vote_average=None,
    )


class TMDBSyncQueueServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="tester", password="x")
        prefs = UserPreferences(user=self.user)
        prefs.save()  # save() принудительно ставит pk=1 (синглтон)

        schedule_patcher = patch.object(TMDBSyncQueueService, "_schedule_tick")
        self.mock_schedule_tick = schedule_patcher.start()
        self.addCleanup(schedule_patcher.stop)

    # ------------------------------------------------------------------ #
    #                      Вспомогательные фабрики                        #
    # ------------------------------------------------------------------ #

    def _movie(self, *, title="Movie", year=2000, source=Movie.Source.KINORIUM, tmdb_id=None):
        return Movie.objects.create(
            title=title,
            original_title=f"Original {title}",
            year=year,
            movie_type=Movie.MovieType.MOVIE,
            status=Movie.Status.RELEASED,
            source=source,
            tmdb_id=tmdb_id,
        )

    # ------------------------------------------------------------------ #
    #                         enqueue_unsynced                            #
    # ------------------------------------------------------------------ #

    @patch.object(TMDBMovieSyncService, "sync_movie")
    def test_enqueue_unsynced_adds_only_kinorium_without_tmdb_id(self, sync_mock):
        target1 = self._movie(title="Target 1")
        target2 = self._movie(title="Target 2")
        self._movie(title="Already synced", tmdb_id=321)
        self._movie(title="From tmdb", source=Movie.Source.TMDB)

        result = TMDBSyncQueueService.enqueue_unsynced()
        self.assertEqual(result["added"], 2)
        self.assertEqual(TMDBSyncQueueItem.objects.count(), 2)

        ids = set(TMDBSyncQueueItem.objects.values_list("movie_id", flat=True))
        self.assertEqual(ids, {target1.id, target2.id})

    @patch.object(TMDBMovieSyncService, "sync_movie")
    def test_enqueue_unsynced_does_not_create_duplicates(self, sync_mock):
        movie = self._movie(title="Target")
        TMDBSyncQueueService.enqueue_unsynced()
        result = TMDBSyncQueueService.enqueue_unsynced()
        self.assertEqual(result["added"], 0)
        self.assertEqual(TMDBSyncQueueItem.objects.filter(movie=movie).count(), 1)

    @patch.object(TMDBMovieSyncService, "sync_movie")
    def test_enqueue_unsynced_keeps_existing_history(self, sync_mock):
        movie = self._movie(title="Target")
        movie2 = self._movie(title="Target 2")

        existing = TMDBSyncQueueItem.objects.create(
            movie=movie2,
            state=TMDBSyncQueueItem.State.SYNCED,
            snapshot_title=movie2.title,
            snapshot_movie_type=movie2.movie_type,
            result_title="Synced",
        )

        result = TMDBSyncQueueService.enqueue_unsynced()
        self.assertEqual(result["added"], 1)  # только movie без записи

        existing.refresh_from_db()
        self.assertEqual(existing.state, TMDBSyncQueueItem.State.SYNCED)  # история не перезаписана
        movies_in_queue = set(TMDBSyncQueueItem.objects.values_list("movie_id", flat=True))
        self.assertIn(movie.id, movies_in_queue)
        self.assertIn(movie2.id, movies_in_queue)

    # ------------------------------------------------------------------ #
    #                        process_one: flow                            #
    # ------------------------------------------------------------------ #

    @patch.object(TMDBMovieSyncService, "sync_movie")
    def test_process_one_noop_when_disabled(self, sync_mock):
        movie = self._movie(title="Target")
        TMDBSyncQueueService.enqueue_unsynced()

        self.assertFalse(UserPreferences.get().tmdb_sync_enabled)
        result = TMDBSyncQueueService.process_one()
        self.assertIsNone(result)

        item = TMDBSyncQueueItem.objects.get(movie=movie)
        self.assertEqual(item.state, TMDBSyncQueueItem.State.PENDING)
        sync_mock.assert_not_called()

    @patch.object(TMDBMovieSyncService, "sync_movie")
    def test_process_one_pending_to_synced_fills_results(self, sync_mock):
        movie = self._movie(title="Target", year=1999)
        TMDBSyncQueueService.enqueue_unsynced()
        candidate = _candidate(321)
        sync_mock.return_value = TMDBSyncResult(
            status="ok",
            message="Данные фильма обновлены из TMDB",
            updated_fields=("title", "year"),
            selected_candidate=candidate,
        )

        TMDBSyncQueueService.start()
        result = TMDBSyncQueueService.process_one()
        self.assertEqual(result["state"], TMDBSyncQueueItem.State.SYNCED)

        item = TMDBSyncQueueItem.objects.get(movie=movie)
        self.assertEqual(item.result_tmdb_id, 321)
        self.assertEqual(item.result_media_type, "movie")
        self.assertEqual(item.result_title, movie.title)
        self.assertEqual(item.result_year, movie.year)
        self.assertFalse(item.error_trace)

    @patch.object(TMDBMovieSyncService, "sync_movie")
    def test_process_one_needs_user_choice_sets_confirm(self, sync_mock):
        movie = self._movie(title="Target")
        TMDBSyncQueueService.enqueue_unsynced()
        sync_mock.return_value = TMDBSyncResult(
            status="needs_user_choice",
            message="Несколько кандидатов",
            candidates=(_candidate(123), _candidate(456)),
        )

        TMDBSyncQueueService.start()
        result = TMDBSyncQueueService.process_one()
        self.assertEqual(result["state"], TMDBSyncQueueItem.State.CONFIRM)

        item = TMDBSyncQueueItem.objects.get(movie=movie)
        self.assertEqual(item.state, TMDBSyncQueueItem.State.CONFIRM)
        self.assertEqual(item.result_status, "needs_user_choice")
        self.assertIn("123", item.result_message)
        self.assertIn("456", item.result_message)

    @patch.object(TMDBMovieSyncService, "sync_movie")
    def test_process_one_exception_sets_error_with_trace(self, sync_mock):
        movie = self._movie(title="Target")
        TMDBSyncQueueService.enqueue_unsynced()
        sync_mock.side_effect = RuntimeError("tmdb is down")

        TMDBSyncQueueService.start()
        result = TMDBSyncQueueService.process_one()
        self.assertEqual(result["state"], TMDBSyncQueueItem.State.ERROR)

        item = TMDBSyncQueueItem.objects.get(movie=movie)
        self.assertEqual(item.state, TMDBSyncQueueItem.State.ERROR)
        self.assertIn("tmdb is down", item.result_message)
        self.assertIn("Traceback", item.error_trace)

    @patch.object(TMDBMovieSyncService, "sync_movie")
    def test_process_one_reschedules_tick_when_more_pending(self, sync_mock):
        movie1 = self._movie(title="Target 1")
        movie2 = self._movie(title="Target 2")
        TMDBSyncQueueService.enqueue_unsynced()
        sync_mock.return_value = TMDBSyncResult(
            status="ok",
            message="ok",
            updated_fields=(),
            selected_candidate=_candidate(321),
        )

        TMDBSyncQueueService.start()
        self.mock_schedule_tick.assert_called_once_with(delay=1)

        TMDBSyncQueueService.process_one()
        movie2_item = TMDBSyncQueueItem.objects.get(movie=movie2)
        self.assertEqual(movie2_item.state, TMDBSyncQueueItem.State.PENDING)

        # второй вызов _schedule_tick — с текущим темпом
        self.assertEqual(self.mock_schedule_tick.call_count, 2)
        self.assertEqual(self.mock_schedule_tick.call_args.kwargs["delay"], 60)

        # после обработки последнего pending перепланирования нет
        TMDBSyncQueueService.process_one()
        self.assertEqual(self.mock_schedule_tick.call_count, 2)

    # ------------------------------------------------------------------ #
    #                      start / stop / remove_all                      #
    # ------------------------------------------------------------------ #

    @patch.object(TMDBMovieSyncService, "sync_movie")
    def test_start_stop_toggle_flag(self, sync_mock):
        self.assertFalse(UserPreferences.get().tmdb_sync_enabled)

        TMDBSyncQueueService.start()
        self.assertTrue(UserPreferences.get().tmdb_sync_enabled)

        TMDBSyncQueueService.stop()
        self.assertFalse(UserPreferences.get().tmdb_sync_enabled)

    @patch.object(TMDBMovieSyncService, "sync_movie")
    def test_remove_all_deletes_items_and_stops(self, sync_mock):
        self._movie(title="Target 1")
        self._movie(title="Target 2")
        TMDBSyncQueueService.enqueue_unsynced()
        TMDBSyncQueueService.start()
        self.assertEqual(TMDBSyncQueueItem.objects.count(), 2)

        removed = TMDBSyncQueueService.remove_all()
        self.assertEqual(removed, 2)
        self.assertEqual(TMDBSyncQueueItem.objects.count(), 0)
        self.assertFalse(UserPreferences.get().tmdb_sync_enabled)

    @patch.object(TMDBMovieSyncService, "sync_movie")
    def test_remove_item_deletes_single_pending_entry(self, sync_mock):
        movie1 = self._movie(title="Target 1")
        movie2 = self._movie(title="Target 2")
        TMDBSyncQueueService.enqueue_unsynced()

        item1 = TMDBSyncQueueItem.objects.get(movie=movie1)
        item2 = TMDBSyncQueueItem.objects.get(movie=movie2)

        removed = TMDBSyncQueueService.remove_item(item1.id)
        self.assertIsNotNone(removed)
        self.assertFalse(TMDBSyncQueueItem.objects.filter(pk=item1.id).exists())
        self.assertTrue(TMDBSyncQueueItem.objects.filter(pk=item2.id).exists())

        self.assertIsNone(TMDBSyncQueueService.remove_item(99999))

    @patch.object(TMDBMovieSyncService, "sync_movie")
    def test_remove_item_rejects_in_progress_entry(self, sync_mock):
        movie = self._movie(title="Target")
        TMDBSyncQueueService.enqueue_unsynced()
        item = TMDBSyncQueueItem.objects.get(movie=movie)
        item.state = TMDBSyncQueueItem.State.IN_PROGRESS
        item.save(update_fields=["state"])

        with self.assertRaises(ValueError):
            TMDBSyncQueueService.remove_item(item.id)
        self.assertTrue(TMDBSyncQueueItem.objects.filter(pk=item.id).exists())

    @patch.object(TMDBMovieSyncService, "sync_movie")
    def test_remove_synced_deletes_only_synced_entries(self, sync_mock):
        movie1 = self._movie(title="Target 1")
        movie2 = self._movie(title="Target 2")
        movie3 = self._movie(title="Target 3")
        TMDBSyncQueueService.enqueue_unsynced()

        item1 = TMDBSyncQueueItem.objects.get(movie=movie1)
        item2 = TMDBSyncQueueItem.objects.get(movie=movie2)
        item3 = TMDBSyncQueueItem.objects.get(movie=movie3)

        item1.state = TMDBSyncQueueItem.State.SYNCED
        item1.save(update_fields=["state"])
        item2.state = TMDBSyncQueueItem.State.CONFIRM
        item2.save(update_fields=["state"])
        # item3 остаётся PENDING

        removed = TMDBSyncQueueService.remove_synced()
        self.assertEqual(removed, 1)
        self.assertFalse(TMDBSyncQueueItem.objects.filter(pk=item1.id).exists())
        self.assertTrue(TMDBSyncQueueItem.objects.filter(pk=item2.id).exists())
        self.assertTrue(TMDBSyncQueueItem.objects.filter(pk=item3.id).exists())