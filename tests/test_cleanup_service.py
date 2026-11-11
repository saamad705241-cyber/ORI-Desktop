"""Tests for core/cleanup_service.py."""
import threading
import time
import unittest

from core.cleanup_service import (
    CleanupService,
    _DEFAULT_INTERVAL_S,
    _MIN_INTERVAL_S,
    get_service,
    make_bounded_list_cleaner,
    make_dict_ttl_cleaner,
)
import core.cleanup_service as csmod


class CleanupServiceTests(unittest.TestCase):

    def _make(self, interval=9999, notify=None):
        return CleanupService(interval_seconds=interval, notify_ui=notify)

    # ------------------------------------------------------------------
    # Constructor / defaults
    # ------------------------------------------------------------------

    def test_default_interval_is_30_minutes(self):
        self.assertEqual(_DEFAULT_INTERVAL_S, 30 * 60)

    def test_minimum_interval_floor(self):
        svc = self._make(interval=1)
        self.assertGreaterEqual(svc._interval, _MIN_INTERVAL_S)

    def test_set_interval_updates(self):
        svc = self._make()
        svc.set_interval(120)
        self.assertEqual(svc._interval, 120)

    # ------------------------------------------------------------------
    # Register / unregister
    # ------------------------------------------------------------------

    def test_register_adds_cleaner(self):
        svc = self._make()
        svc.register("test", lambda: (0, 0), "test cleaner")
        self.assertIn("test", svc._cleaners)

    def test_unregister_removes_cleaner(self):
        svc = self._make()
        svc.register("test", lambda: (0, 0))
        removed = svc.unregister("test")
        self.assertTrue(removed)
        self.assertNotIn("test", svc._cleaners)

    def test_unregister_nonexistent_returns_false(self):
        svc = self._make()
        self.assertFalse(svc.unregister("nope"))

    # ------------------------------------------------------------------
    # run_now
    # ------------------------------------------------------------------

    def test_run_now_increments_count(self):
        svc = self._make()
        svc.run_now()
        self.assertEqual(svc._run_count, 1)

    def test_run_now_returns_summary_dict(self):
        svc = self._make()
        svc.register("dummy", lambda: (100, 3))
        result = svc.run_now()
        self.assertIn("items_freed", result)
        self.assertIn("bytes_freed", result)
        self.assertEqual(result["items_freed"], 3)
        self.assertEqual(result["bytes_freed"], 100)

    def test_failing_cleaner_does_not_crash_service(self):
        svc = self._make()
        svc.register("bad", lambda: 1 / 0)  # will raise ZeroDivisionError
        result = svc.run_now()
        self.assertEqual(len(result["errors"]), 1)
        self.assertIn("bad", result["errors"][0])

    def test_multiple_cleaners_aggregated(self):
        svc = self._make()
        svc.register("a", lambda: (10, 2))
        svc.register("b", lambda: (20, 5))
        result = svc.run_now()
        self.assertEqual(result["bytes_freed"], 30)
        self.assertEqual(result["items_freed"], 7)

    def test_notify_ui_called_when_items_freed(self):
        messages = []
        svc = CleanupService(interval_seconds=9999, notify_ui=messages.append)
        svc.register("work", lambda: (0, 4))
        svc.run_now()
        self.assertEqual(len(messages), 1)
        self.assertIn("4", messages[0])

    def test_notify_ui_not_called_when_nothing_freed(self):
        messages = []
        svc = CleanupService(interval_seconds=9999, notify_ui=messages.append)
        svc.register("noop", lambda: (0, 0))
        svc.run_now()
        self.assertEqual(len(messages), 0)

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def test_status_has_expected_keys(self):
        svc = self._make()
        s = svc.status()
        for k in ("interval_s", "run_count", "registered_cleaners", "thread_alive"):
            self.assertIn(k, s)

    # ------------------------------------------------------------------
    # Built-in factory cleaners
    # ------------------------------------------------------------------

    def test_bounded_list_cleaner_trims(self):
        lst = list(range(20))
        cleaner = make_bounded_list_cleaner(lst, max_items=5, name="test")
        _, freed = cleaner()
        self.assertEqual(freed, 15)
        self.assertEqual(len(lst), 5)
        self.assertEqual(lst, list(range(15, 20)))

    def test_bounded_list_cleaner_noop_within_limit(self):
        lst = list(range(3))
        cleaner = make_bounded_list_cleaner(lst, max_items=10)
        _, freed = cleaner()
        self.assertEqual(freed, 0)
        self.assertEqual(len(lst), 3)

    def test_dict_ttl_cleaner_evicts_old_entries(self):
        d = {
            "old": {"ts": time.monotonic() - 100},
            "fresh": {"ts": time.monotonic() + 9999},
        }
        cleaner = make_dict_ttl_cleaner(d, ttl_seconds=10)
        _, freed = cleaner()
        self.assertEqual(freed, 1)
        self.assertNotIn("old", d)
        self.assertIn("fresh", d)

    def test_dict_ttl_cleaner_keeps_all_fresh(self):
        d = {"a": {"ts": time.monotonic() + 9999}}
        cleaner = make_dict_ttl_cleaner(d, ttl_seconds=10)
        _, freed = cleaner()
        self.assertEqual(freed, 0)
        self.assertIn("a", d)

    # ------------------------------------------------------------------
    # Module singleton
    # ------------------------------------------------------------------

    def test_get_service_returns_singleton(self):
        csmod._service = None
        a = get_service()
        b = get_service()
        self.assertIs(a, b)
        csmod._service = None  # clean up


if __name__ == "__main__":
    unittest.main()
