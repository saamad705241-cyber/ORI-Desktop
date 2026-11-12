"""Tests for core/context_refresh.py."""
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from core.context_refresh import ContextRefreshService


class ContextRefreshTests(unittest.TestCase):

    def _make_service(self, interval=9999, checkpoint_dir=None):
        cp_path = Path(checkpoint_dir) / "checkpoint.json" if checkpoint_dir else None
        svc = ContextRefreshService(
            interval_seconds=interval,
            checkpoint_path=cp_path,
        )
        return svc

    # ------------------------------------------------------------------
    # Constructor / configuration
    # ------------------------------------------------------------------

    def test_default_interval_is_three_hours(self):
        from core.context_refresh import _DEFAULT_INTERVAL_S
        self.assertEqual(_DEFAULT_INTERVAL_S, 3 * 60 * 60)

    def test_minimum_interval_guard(self):
        svc = self._make_service(interval=1)  # below 5-minute floor
        from core.context_refresh import _MIN_INTERVAL_S
        self.assertGreaterEqual(svc._interval, _MIN_INTERVAL_S)

    def test_set_interval_updates_next_due(self):
        svc = self._make_service(interval=9999)
        before = svc._next_due_ts
        svc.set_interval(600)
        self.assertEqual(svc._interval, 600)
        # next_due_ts should have shifted
        self.assertNotEqual(svc._next_due_ts, before)

    # ------------------------------------------------------------------
    # is_due / time_until_next_s
    # ------------------------------------------------------------------

    def test_is_due_false_when_interval_far_future(self):
        svc = self._make_service(interval=9999)
        self.assertFalse(svc.is_due())

    def test_is_due_true_after_forcing_past_due(self):
        svc = self._make_service(interval=9999)
        # Wind the next_due_ts into the past
        svc._next_due_ts = time.monotonic() - 1.0
        self.assertTrue(svc.is_due())

    def test_time_until_next_is_zero_when_overdue(self):
        svc = self._make_service(interval=9999)
        svc._next_due_ts = time.monotonic() - 10.0
        self.assertEqual(svc.time_until_next_s(), 0.0)

    # ------------------------------------------------------------------
    # force_refresh
    # ------------------------------------------------------------------

    def test_force_refresh_returns_true(self):
        svc = self._make_service()
        result = svc.force_refresh()
        self.assertTrue(result)

    def test_force_refresh_increments_count(self):
        svc = self._make_service()
        svc.force_refresh()
        self.assertEqual(svc._refresh_count, 1)

    
       def test_force_refresh_advances_next_due_ts(self):
        svc = self._make_service(interval=600)

        # Simulate an old scheduled deadline.
        svc._next_due_ts = time.monotonic() - 1.0
        before = svc._next_due_ts

        svc.force_refresh()

        self.assertGreater(svc._next_due_ts, before)
        self.assertGreater(svc.time_until_next_s(), 0.0)


    def test_concurrent_refresh_blocked(self):
        """A second force_refresh called while one is artificially in-progress
        should return False without incrementing the counter."""
        svc = self._make_service()
        # Simulate a refresh already in progress
        svc._refresh_running = True
        result = svc.force_refresh()
        self.assertFalse(result)
        self.assertEqual(svc._refresh_count, 0)  # nothing ran
        svc._refresh_running = False

    def test_on_refresh_callback_called(self):
        called = []
        svc = ContextRefreshService(
            interval_seconds=9999,
            on_refresh=lambda cp: called.append(cp),
        )
        svc.force_refresh()
        self.assertEqual(len(called), 1)
        self.assertEqual(called[0]["status"], "complete")

    # ------------------------------------------------------------------
    # Conversation trim
    # ------------------------------------------------------------------

    def test_trim_keeps_recent_turns(self):
        from core.context_refresh import _KEEP_RECENT_TURNS
        turns = [f"turn-{i}" for i in range(_KEEP_RECENT_TURNS + 5)]
        result = []

        svc = self._make_service()
        svc.get_conversation_turns = lambda: list(turns)
        svc.set_conversation_turns = lambda t: result.extend(t)
        svc.force_refresh()

        self.assertLessEqual(len(result), _KEEP_RECENT_TURNS + 1)  # +1 for summary sentinel

    def test_trim_noop_when_turns_within_limit(self):
        from core.context_refresh import _KEEP_RECENT_TURNS
        turns = [f"turn-{i}" for i in range(_KEEP_RECENT_TURNS - 1)]
        result_holder = {"turns": None}

        svc = self._make_service()
        svc.get_conversation_turns = lambda: list(turns)
        svc.set_conversation_turns = lambda t: result_holder.update({"turns": t})
        svc.force_refresh()

        # set_conversation_turns should not have been called (no trim needed)
        self.assertIsNone(result_holder["turns"])

    # ------------------------------------------------------------------
    # Checkpoint persistence
    # ------------------------------------------------------------------

    def test_checkpoint_written_to_disk(self):
        import json
        with TemporaryDirectory() as tmp:
            svc = self._make_service(checkpoint_dir=tmp)
            svc.force_refresh()
            cp_path = Path(tmp) / "checkpoint.json"
            self.assertTrue(cp_path.exists())
            data = json.loads(cp_path.read_text())
            self.assertEqual(data["status"], "complete")
            self.assertEqual(data["cycle"], 1)

    # ------------------------------------------------------------------
    # Status diagnostic
    # ------------------------------------------------------------------

    def test_status_returns_dict(self):
        svc = self._make_service()
        s = svc.status()
        for key in ("interval_s", "refresh_count", "refresh_running",
                    "next_due_in_s", "thread_alive"):
            self.assertIn(key, s)

    # ------------------------------------------------------------------
    # Module-level helpers
    # ------------------------------------------------------------------

    def test_get_service_returns_singleton(self):
        import core.context_refresh as cr
        # Reset module singleton for isolation
        cr._service = None
        a = cr.get_service()
        b = cr.get_service()
        self.assertIs(a, b)
        cr._service = None  # clean up


if __name__ == "__main__":
    unittest.main()
