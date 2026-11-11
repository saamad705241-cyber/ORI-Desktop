"""
core/cleanup_service.py — ORI Periodic RAM Cleanup Service

Spec requirement: Part 12.3 — periodic RAM cleanup.

Manages configurable periodic cleanup of expired in-memory state. It never
deletes persistent user data or saved memories — it only clears bounded
in-RAM structures such as transcript buffers, completed-task payloads, and
cached intermediate responses.

Design rules:
  - Single daemon thread per service instance; never spawns a second.
  - Each registered cleaner is a named callable; failures are logged and skipped.
  - Cleanup summary is written to the UI notifier without leaking data.
  - All public methods are thread-safe.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Dict, List, Optional, Tuple

log = logging.getLogger("ori.cleanup")

# Default cleanup interval: 30 minutes
_DEFAULT_INTERVAL_S = 30 * 60
_MIN_INTERVAL_S = 60  # 1 minute floor


class CleanupService:
    """Runs registered cleaner functions on a configurable schedule.

    Cleaners must be fast, non-blocking, and idempotent. They receive no
    arguments and return (freed_bytes_estimate: int, items_freed: int).
    Returning (0, 0) is valid when there was nothing to clean.
    """

    def __init__(
        self,
        interval_seconds: int = _DEFAULT_INTERVAL_S,
        notify_ui: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._interval = max(int(interval_seconds), _MIN_INTERVAL_S)
        self._notify_ui = notify_ui
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        # name → (cleaner_fn, description)
        self._cleaners: Dict[str, Tuple[Callable, str]] = {}
        self._last_run_ts: float = 0.0
        self._run_count: int = 0

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, name: str, fn: Callable, description: str = "") -> None:
        """Register a named cleaner. Overwrites any previous entry with the
        same name so hot-reload is safe."""
        with self._lock:
            self._cleaners[name] = (fn, description)
        log.debug("Cleanup: registered cleaner '%s'.", name)

    def unregister(self, name: str) -> bool:
        """Remove a registered cleaner. Returns True if it existed."""
        with self._lock:
            existed = name in self._cleaners
            self._cleaners.pop(name, None)
        return existed

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def set_interval(self, seconds: int) -> None:
        with self._lock:
            self._interval = max(int(seconds), _MIN_INTERVAL_S)

    def start(self) -> None:
        """Start the cleanup thread. Safe to call multiple times."""
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._loop, name="ori-cleanup", daemon=True
            )
            self._thread.start()
        log.info("Cleanup service started (interval=%ds).", self._interval)

    def stop(self) -> None:
        self._stop_event.set()
        log.info("Cleanup service stop requested.")

    def run_now(self) -> dict:
        """Trigger an immediate cleanup pass and return its summary."""
        return self._run_pass()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            with self._lock:
                interval = self._interval
            self._stop_event.wait(timeout=interval)
            if self._stop_event.is_set():
                break
            self._run_pass()

    def _run_pass(self) -> dict:
        with self._lock:
            cleaners = dict(self._cleaners)

        total_bytes = 0
        total_items = 0
        errors: List[str] = []

        for name, (fn, _desc) in cleaners.items():
            try:
                result = fn()
                if isinstance(result, (tuple, list)) and len(result) == 2:
                    b, i = int(result[0]), int(result[1])
                else:
                    b, i = 0, 0
                total_bytes += b
                total_items += i
                if i or b:
                    log.debug(
                        "Cleanup '%s': freed %d items, ~%d bytes.", name, i, b
                    )
            except Exception as exc:
                err = f"{name}: {exc}"
                errors.append(err)
                log.warning("Cleanup '%s' raised: %s", name, exc)

        with self._lock:
            self._last_run_ts = time.monotonic()
            self._run_count += 1
            run_n = self._run_count

        summary = {
            "run": run_n,
            "items_freed": total_items,
            "bytes_freed": total_bytes,
            "errors": errors,
        }

        if self._notify_ui and (total_items or errors):
            msg_parts = []
            if total_items:
                msg_parts.append(f"{total_items} expired objects released")
            if errors:
                msg_parts.append(f"{len(errors)} cleaner error(s)")
            try:
                self._notify_ui("SYS: RAM cleanup — " + "; ".join(msg_parts) + ".")
            except Exception:
                pass

        log.info(
            "[Cleanup] run #%d: %d items freed, ~%d bytes, %d errors.",
            run_n, total_items, total_bytes, len(errors),
        )
        return summary

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def status(self) -> dict:
        with self._lock:
            return {
                "interval_s": self._interval,
                "run_count": self._run_count,
                "last_run_ts": self._last_run_ts,
                "registered_cleaners": list(self._cleaners.keys()),
                "thread_alive": bool(self._thread and self._thread.is_alive()),
            }


# ---------------------------------------------------------------------------
# Built-in cleaner factories
# ---------------------------------------------------------------------------

def make_bounded_list_cleaner(
    lst: list,
    max_items: int,
    lock: Optional[threading.Lock] = None,
    name: str = "list",
) -> Callable:
    """Return a cleaner that trims `lst` to the most recent `max_items` entries."""
    _lock = lock or threading.Lock()

    def _clean():
        with _lock:
            before = len(lst)
            if before > max_items:
                del lst[:before - max_items]
                freed = before - max_items
                return 0, freed
        return 0, 0

    _clean.__name__ = f"bounded_list_{name}"
    return _clean


def make_dict_ttl_cleaner(
    d: dict,
    ttl_seconds: float,
    ts_key: str = "ts",
    lock: Optional[threading.Lock] = None,
) -> Callable:
    """Return a cleaner that evicts entries from `d` older than `ttl_seconds`.
    Each value must be a dict with a float timestamp at `ts_key`."""
    _lock = lock or threading.Lock()

    def _clean():
        cutoff = time.monotonic() - ttl_seconds
        to_delete = []
        with _lock:
            for k, v in d.items():
                if isinstance(v, dict) and v.get(ts_key, float("inf")) < cutoff:
                    to_delete.append(k)
            for k in to_delete:
                del d[k]
        return 0, len(to_delete)

    return _clean


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_service: Optional[CleanupService] = None


def get_service() -> CleanupService:
    global _service
    if _service is None:
        _service = CleanupService()
    return _service


def start(
    interval_seconds: int = _DEFAULT_INTERVAL_S,
    notify_ui: Optional[Callable[[str], None]] = None,
) -> CleanupService:
    global _service
    if _service is None:
        _service = CleanupService(
            interval_seconds=interval_seconds, notify_ui=notify_ui
        )
    else:
        _service.set_interval(interval_seconds)
        if notify_ui:
            _service._notify_ui = notify_ui
    _service.start()
    return _service


def stop() -> None:
    if _service:
        _service.stop()
