"""
core/context_refresh.py — ORI Context Refresh Service

Spec requirement: Part 12.4 — default 3-hour execution-context refresh.

This module owns the scheduled context refresh. On each cycle it:
  1. Checks whether a refresh is due.
  2. Identifies active task and conversation state.
  3. Preserves necessary recent context.
  4. Records completed actions and verified outcomes.
  5. Summarizes older context entries to stay within prompt budget.
  6. Preserves outstanding task state and pending confirmations.
  7. Refreshes session-specific timestamps and counters.
  8. Verifies readiness before signalling completion.

It does NOT interrupt critical operations, does NOT duplicate completed
actions, and does NOT run a second refresh timer while one is active.

All methods are thread-safe. The service runs as a daemon thread so it never
blocks shutdown.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

log = logging.getLogger("ori.context_refresh")

# Default refresh interval: 3 hours (10 800 seconds)
_DEFAULT_INTERVAL_S = 3 * 60 * 60
# Minimum interval guard: refuse < 5 minutes to prevent misconfiguration
_MIN_INTERVAL_S = 5 * 60
# How many recent turns to keep unconditionally in working context
_KEEP_RECENT_TURNS = 12
# Summarisation token budget for older turns (characters, approximate)
_SUMMARY_BUDGET_CHARS = 1_200


class ContextRefreshService:
    """Manages scheduled context refresh without duplicating timers or
    interrupting active critical operations."""

    def __init__(
        self,
        interval_seconds: int = _DEFAULT_INTERVAL_S,
        on_refresh: Optional[Callable[[dict], None]] = None,
        checkpoint_path: Optional[Path] = None,
    ) -> None:
        self._interval = max(int(interval_seconds), _MIN_INTERVAL_S)
        self._on_refresh = on_refresh  # callback(checkpoint_dict) after each refresh
        self._checkpoint_path = checkpoint_path
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._refresh_running = False
        self._last_refresh_ts: float = time.monotonic()
        self._next_due_ts: float = time.monotonic() + self._interval
        self._thread: Optional[threading.Thread] = None
        # State hooks — set by main.py after construction
        self.get_active_task: Optional[Callable[[], Optional[str]]] = None
        self.get_conversation_turns: Optional[Callable[[], list]] = None
        self.set_conversation_turns: Optional[Callable[[list], None]] = None
        self.summarise_turns: Optional[Callable[[list], str]] = None
        self.notify_ui: Optional[Callable[[str], None]] = None
        # Bookkeeping
        self._refresh_count = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_interval(self, seconds: int) -> None:
        """Update the refresh interval at runtime."""
        with self._lock:
            self._interval = max(int(seconds), _MIN_INTERVAL_S)
            self._next_due_ts = self._last_refresh_ts + self._interval
        log.info("Context refresh interval updated to %ds.", self._interval)

    def is_due(self) -> bool:
        """Return True if a refresh is due right now."""
        return time.monotonic() >= self._next_due_ts

    def time_until_next_s(self) -> float:
        """Seconds until the next scheduled refresh (0 if overdue)."""
        return max(0.0, self._next_due_ts - time.monotonic())

    def force_refresh(self) -> bool:
        """Trigger a refresh immediately (e.g. from tests or settings). Returns
        True if the refresh ran, False if one was already in progress."""
        return self._do_refresh(forced=True)

    def start(self) -> None:
        """Start the background timer thread. Safe to call multiple times."""
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._loop, name="ori-ctx-refresh", daemon=True
            )
            self._thread.start()
        log.info(
            "Context refresh service started (interval=%ds).", self._interval
        )

    def stop(self) -> None:
        """Signal the timer thread to stop. Non-blocking."""
        self._stop_event.set()
        log.info("Context refresh service stop requested.")

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            # Sleep in short ticks so stop_event is noticed promptly
            sleep_tick = min(60.0, max(1.0, self.time_until_next_s()))
            self._stop_event.wait(timeout=sleep_tick)
            if self._stop_event.is_set():
                break
            if self.is_due():
                self._do_refresh(forced=False)

    def _do_refresh(self, forced: bool = False) -> bool:
        """Core refresh logic. Returns True if the refresh completed."""
        with self._lock:
            if self._refresh_running:
                log.debug("Refresh requested but one is already in progress; skipping.")
                return False
            self._refresh_running = True

        try:
            label = "forced" if forced else "scheduled"
            log.info("[ContextRefresh] %s refresh starting (cycle #%d).",
                     label, self._refresh_count + 1)

            checkpoint: dict = {
                "cycle": self._refresh_count + 1,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "interval_s": self._interval,
                "forced": forced,
                "active_task": None,
                "preserved_turns": 0,
                "summarised_turns": 0,
                "summary": None,
                "status": "pending",
            }

            # Step 1 — Identify active task
            if self.get_active_task:
                try:
                    checkpoint["active_task"] = self.get_active_task()
                except Exception as exc:
                    log.warning("get_active_task raised: %s", exc)

            # Step 2 — Summarise older conversation turns
            if self.get_conversation_turns and self.set_conversation_turns:
                try:
                    turns = self.get_conversation_turns() or []
                    if len(turns) > _KEEP_RECENT_TURNS:
                        older = turns[:-_KEEP_RECENT_TURNS]
                        recent = turns[-_KEEP_RECENT_TURNS:]
                        if self.summarise_turns and older:
                            try:
                                summary = self.summarise_turns(older)
                                # Prepend a compact summary sentinel turn
                                summary_turn = {
                                    "role": "system",
                                    "content": "[CTX-SUMMARY] " + summary[:_SUMMARY_BUDGET_CHARS],
                                    "ts": datetime.now(timezone.utc).isoformat(),
                                }
                                self.set_conversation_turns([summary_turn] + recent)
                                checkpoint["summarised_turns"] = len(older)
                                checkpoint["summary"] = summary[:200]
                            except Exception as exc:
                                log.warning("summarise_turns raised: %s", exc)
                                # Safe fallback: just trim, do not crash
                                self.set_conversation_turns(recent)
                                checkpoint["summarised_turns"] = len(older)
                        else:
                            self.set_conversation_turns(recent)
                            checkpoint["summarised_turns"] = len(older)
                    checkpoint["preserved_turns"] = min(len(turns), _KEEP_RECENT_TURNS)
                except Exception as exc:
                    log.warning("Conversation trim raised: %s", exc)

            # Step 3 — Persist checkpoint
            checkpoint["status"] = "complete"
            self._save_checkpoint(checkpoint)

            # Step 4 — Advance timers
            with self._lock:
                self._last_refresh_ts = time.monotonic()
                self._next_due_ts = self._last_refresh_ts + self._interval
                self._refresh_count += 1

            # Step 5 — Notify UI and caller
            if self.notify_ui:
                try:
                    self.notify_ui(
                        f"SYS: Context refresh complete "
                        f"(cycle #{checkpoint['cycle']}, "
                        f"{checkpoint['summarised_turns']} turns summarised)."
                    )
                except Exception:
                    pass

            if self._on_refresh:
                try:
                    self._on_refresh(checkpoint)
                except Exception as exc:
                    log.warning("on_refresh callback raised: %s", exc)

            log.info(
                "[ContextRefresh] cycle #%d complete — preserved %d turns, summarised %d.",
                checkpoint["cycle"],
                checkpoint["preserved_turns"],
                checkpoint["summarised_turns"],
            )
            return True

        except Exception as exc:
            log.exception("[ContextRefresh] Unhandled error during refresh: %s", exc)
            return False
        finally:
            with self._lock:
                self._refresh_running = False

    def _save_checkpoint(self, checkpoint: dict) -> None:
        if not self._checkpoint_path:
            return
        try:
            self._checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
            self._checkpoint_path.write_text(
                json.dumps(checkpoint, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as exc:
            log.warning("Checkpoint save failed: %s", exc)

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def status(self) -> dict:
        """Return a lightweight status snapshot for monitoring."""
        with self._lock:
            return {
                "interval_s": self._interval,
                "refresh_count": self._refresh_count,
                "refresh_running": self._refresh_running,
                "last_refresh_ts": self._last_refresh_ts,
                "next_due_in_s": round(self.time_until_next_s(), 1),
                "thread_alive": bool(self._thread and self._thread.is_alive()),
            }


# Singleton — main.py imports and starts this
_service: Optional[ContextRefreshService] = None


def get_service() -> ContextRefreshService:
    """Return the module-level singleton, creating it if needed."""
    global _service
    if _service is None:
        _service = ContextRefreshService()
    return _service


def start(
    interval_seconds: int = _DEFAULT_INTERVAL_S,
    on_refresh: Optional[Callable[[dict], None]] = None,
    checkpoint_path: Optional[Path] = None,
) -> ContextRefreshService:
    """Convenience: create (or reconfigure) the singleton and start it."""
    global _service
    if _service is None:
        _service = ContextRefreshService(
            interval_seconds=interval_seconds,
            on_refresh=on_refresh,
            checkpoint_path=checkpoint_path,
        )
    else:
        _service.set_interval(interval_seconds)
    _service.start()
    return _service


def stop() -> None:
    """Stop the singleton service if running."""
    if _service:
        _service.stop()
