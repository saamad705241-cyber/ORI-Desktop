from pathlib import Path

from dashboard import server


def test_phone_remote_static_assets_exist_in_source_runtime():
    assert (server.STATIC_DIR / "app.html").is_file()
    assert (server.STATIC_DIR / "login.html").is_file()
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
