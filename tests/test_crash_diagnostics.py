from __future__ import annotations

import io

from core.crash_diagnostics import _write_report


def test_crash_report_writes_timestamp_and_full_python_traceback():
    stream = io.StringIO()
    try:
        raise RuntimeError("simulated media playback failure")
    except RuntimeError:
        import sys
        _write_report(stream, "ORI runtime failed", sys.exc_info())

    report = stream.getvalue()
    assert "ORI runtime failed" in report
    assert "RuntimeError: simulated media playback failure" in report
    assert "Traceback (most recent call last)" in report
