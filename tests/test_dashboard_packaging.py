from pathlib import Path

from dashboard import server


def test_phone_remote_static_assets_exist_in_source_runtime():
    assert (server.STATIC_DIR / "app.html").is_file()
    assert (server.STATIC_DIR / "login.html").is_file()
    assert (server.STATIC_DIR / "crypto-js.js").is_file()
    assert "CryptoJS" in server._read("crypto-js.js")
    assert server._read("app.html")
    assert server._read("login.html")


def test_frozen_runtime_resolves_assets_from_pyinstaller_bundle(tmp_path, monkeypatch):
    bundle_root = tmp_path / "bundle"
    app_root = tmp_path / "installed"
    static_dir = bundle_root / "dashboard" / "static"
    static_dir.mkdir(parents=True)
    app_root.mkdir()
    (static_dir / "app.html").write_text("<html>app</html>", encoding="utf-8")
    (static_dir / "login.html").write_text("<html>login</html>", encoding="utf-8")
    (static_dir / "crypto-js.js").write_text("var CryptoJS = {};", encoding="utf-8")

    monkeypatch.setattr(server.sys, "frozen", True, raising=False)
    monkeypatch.setattr(server.sys, "_MEIPASS", str(bundle_root), raising=False)
    monkeypatch.setattr(server.sys, "executable", str(app_root / "ORI.exe"), raising=False)

    assert server._application_root() == app_root
    assert server._resolve_static_dir() == static_dir


def test_frozen_runtime_falls_back_to_installed_dashboard_assets(tmp_path, monkeypatch):
    bundle_root = tmp_path / "bundle"
    app_root = tmp_path / "installed"
    static_dir = app_root / "dashboard" / "static"
    static_dir.mkdir(parents=True)
    app_root.mkdir(exist_ok=True)
    (static_dir / "app.html").write_text("<html>app</html>", encoding="utf-8")
    (static_dir / "login.html").write_text("<html>login</html>", encoding="utf-8")
    (static_dir / "crypto-js.js").write_text("var CryptoJS = {};", encoding="utf-8")

    monkeypatch.setattr(server.sys, "frozen", True, raising=False)
    monkeypatch.setattr(server.sys, "_MEIPASS", str(bundle_root), raising=False)
    monkeypatch.setattr(server.sys, "executable", str(app_root / "ORI.exe"), raising=False)

    assert server._resolve_static_dir() == static_dir


def test_phone_remote_html_missing_reports_actionable_path(tmp_path, monkeypatch):
    missing_dir = tmp_path / "missing"
    monkeypatch.setattr(server, "STATIC_DIR", missing_dir)

    try:
        server._read("app.html")
    except FileNotFoundError as exc:
        assert "app.html" in str(exc)
        assert str(missing_dir) in str(exc)
    else:
        raise AssertionError("Missing Phone Remote HTML should fail with a clear asset path")



def _dashboard_for_startup_test(monkeypatch):
    import asyncio

    monkeypatch.setattr(server, "_local_ip", lambda: "192.168.1.20")
    monkeypatch.setattr(
        server,
        "_find_available_port",
        lambda start=server.PORT, attempts=32, exclude=None: int(start),
    )
    monkeypatch.setattr(server, "_ensure_certs", lambda _ip: False)
    monkeypatch.setattr(server, "_ensure_network_access", lambda _port: None)
    dashboard = server.DashboardServer()
    status_updates = []
    dashboard.set_status_callback(
        lambda url, running, detail: status_updates.append((url, running, detail))
    )
    return dashboard, status_updates


def test_dashboard_config_error_is_reported_instead_of_staying_starting(monkeypatch):
    import asyncio

    dashboard, status_updates = _dashboard_for_startup_test(monkeypatch)

    def fail_config(*_args, **_kwargs):
        raise ValueError("simulated config failure")

    monkeypatch.setattr(server.uvicorn, "Config", fail_config)
    asyncio.run(dashboard.serve())

    assert "Uvicorn configuration" in dashboard._startup_error
    assert "simulated config failure" in dashboard._startup_error
    assert status_updates
    assert status_updates[-1][1] is False


def test_uvicorn_bind_error_is_reported_instead_of_staying_starting(monkeypatch):
    import asyncio

    dashboard, status_updates = _dashboard_for_startup_test(monkeypatch)
    monkeypatch.setattr(server.uvicorn, "Config", lambda *_args, **_kwargs: object())

    class BrokenServer:
        def __init__(self, _config):
            self.started = False
            self.should_exit = False

        async def serve(self):
            raise OSError("simulated port bind failure")

    monkeypatch.setattr(server.uvicorn, "Server", BrokenServer)
    asyncio.run(dashboard.serve())

    assert "Uvicorn socket binding" in dashboard._startup_error
    assert "simulated port bind failure" in dashboard._startup_error
    assert status_updates
    assert status_updates[-1][1] is False


def test_dashboard_diagnostic_log_is_written_under_local_app_data(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    server._write_dashboard_diagnostic("test startup diagnostic")

    log_file = tmp_path / "ORI" / "logs" / "phone_remote.log"
    assert log_file.is_file()
    assert "test startup diagnostic" in log_file.read_text(encoding="utf-8")
