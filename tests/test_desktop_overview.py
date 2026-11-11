from actions.desktop_overview import get_desktop_overview


def test_desktop_overview_returns_realistic_snapshot_shape():
    data = get_desktop_overview()
    assert isinstance(data, dict)
    assert "ok" in data
    if data["ok"]:
        for key in ("cpu_percent", "ram_percent", "disk_percent", "process_count", "uptime_hours"):
            assert key in data
        assert 0 <= data["cpu_percent"] <= 100
        assert 0 <= data["ram_percent"] <= 100
