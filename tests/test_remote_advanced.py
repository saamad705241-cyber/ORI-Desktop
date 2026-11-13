"""Tests for ORI 3.4 authenticated phone-control and screen-share paths."""
from unittest.mock import patch

from fastapi.testclient import TestClient

from dashboard.server import DashboardServer
from dashboard.remote_control import validate_phone_screen_frame


def _paired_server():
    server = DashboardServer()
    token = "test-paired-phone-token"
    server._tokens.add(token)
    server._token_keys[token] = "test-session-key"
    return server, token, {"Authorization": f"Bearer {token}"}


def test_dashboard_health_endpoint_reports_ori_version():
    server = DashboardServer()
    with TestClient(server.app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["app"] == "ORI"
    from ori_metadata import APP_VERSION
    assert response.json()["version"] == APP_VERSION


def test_remote_action_rejects_unpaired_phone():
    server = DashboardServer()
    with TestClient(server.app) as client:
        response = client.post("/api/remote/action", json={"action": "media", "name": "play_pause"})
    assert response.status_code == 401


def test_remote_action_delegates_only_after_pair_authentication():
    server, token, headers = _paired_server()
    with patch("dashboard.server.execute_pointer_action", return_value={"ok": True}) as execute:
        with TestClient(server.app) as client:
            response = client.post(
                "/api/remote/action",
                json={"action": "media", "name": "play_pause"},
                headers=headers,
            )
    assert response.status_code == 200
    assert response.json()["ok"] is True
    execute.assert_called_once_with({"action": "media", "name": "play_pause"})


def test_phone_screen_frame_is_auth_required_and_stays_in_memory():
    server, token, headers = _paired_server()
    frame = b"\xff\xd8\xff" + b"ori-test-frame"
    with TestClient(server.app) as client:
        denied = client.post("/api/phone-screen/frame", content=frame, headers={"Content-Type": "image/jpeg"})
        accepted = client.post(
            "/api/phone-screen/frame", content=frame,
            headers={**headers, "Content-Type": "image/jpeg"},
        )
        status = client.get("/api/phone-screen/status", headers=headers)
    assert denied.status_code == 401
    assert accepted.status_code == 200
    assert status.status_code == 200
    assert status.json()["shared"] is True
    assert server._phone_screen_latest["data"] == frame


def test_analyze_phone_screen_queues_latest_frame_for_gemini():
    server, token, headers = _paired_server()
    frame = b"\xff\xd8\xff" + b"frame"
    server._phone_screen_latest = {"data": frame, "mime_type": "image/jpeg", "captured_at": __import__("time").time()}
    with TestClient(server.app) as client:
        response = client.post(
            "/api/phone-screen/analyze",
            json={"prompt": "Read this screen"},
            headers=headers,
        )
    assert response.status_code == 200
    item = server._phone_screen_queue.get_nowait()
    assert item["data"] == frame
    assert item["prompt"] == "Read this screen"


def test_companion_code_is_one_time_and_returns_an_upload_token():
    server, token, headers = _paired_server()
    with TestClient(server.app) as client:
        created = client.post("/api/companion/create-code", headers=headers)
        assert created.status_code == 200
        code = created.json()["code"]
        paired = client.post("/api/companion/pair", json={"code": code})
        replay = client.post("/api/companion/pair", json={"code": code})
        companion_token = paired.json()["token"] if paired.status_code == 200 else ""
        uploaded = client.post(
            "/api/phone-screen/frame",
            content=b"\xff\xd8\xffcompanion-frame",
            headers={"Authorization": f"Bearer {companion_token}", "Content-Type": "image/jpeg"},
        ) if companion_token else None
    assert paired.status_code == 200
    assert paired.json()["ok"] is True
    assert paired.json()["token"] in server._tokens
    assert uploaded is not None and uploaded.status_code == 200
    assert replay.status_code == 401


def test_phone_screen_frame_validation_bounds_size_and_signature():
    assert validate_phone_screen_frame(b"\xff\xd8\xffjpeg") is True
    assert validate_phone_screen_frame(b"\x89PNG\r\n\x1a\nimage") is True
    assert validate_phone_screen_frame(b"not-image") is False
    assert validate_phone_screen_frame(b"\xff\xd8\xff" + b"x" * (2 * 1024 * 1024)) is False


def test_remote_web_contains_touchpad_screen_share_and_android_companion_paths():
    from pathlib import Path
    html = (Path(__file__).resolve().parents[1] / "dashboard" / "static" / "app.html").read_text(encoding="utf-8")
    for expected in (
        "id=\"touchpad\"", "/ws/desktop-screen", "/ws/control",
        "/ws/phone-screen", "/api/phone-screen/analyze", "/api/companion/create-code",
        "START LIVE VIEW", "PAIR ANDROID SCREEN COMPANION",
    ):
        assert expected in html


def test_dashboard_server_reports_ready_only_after_uvicorn_binds():
    import asyncio
    from unittest.mock import patch

    async def exercise():
        with patch("dashboard.server._local_ip", return_value="192.168.1.77"), \
             patch("dashboard.server._ensure_certs", return_value=False), \
             patch("dashboard.server._ensure_network_access", return_value=None):
            server = DashboardServer()
            notifications = []
            server.set_status_callback(lambda url, running, detail="": notifications.append((url, running, detail)))
            task = asyncio.create_task(server.serve())
            for _ in range(100):
                if server.is_running or task.done():
                    break
                await asyncio.sleep(0.05)
            assert server.is_running is True
            assert notifications[-1][1] is True
            assert server.get_url().startswith("http://192.168.1.77:")
            assert server._uvicorn_server is not None
            server._uvicorn_server.should_exit = True
            await asyncio.wait_for(task, timeout=5)
            assert server.is_running is False

    asyncio.run(exercise())


def test_touchpad_moves_are_clamped_before_pyautogui():
    import sys
    from types import SimpleNamespace
    from unittest.mock import patch
    from dashboard.remote_control import execute_pointer_action

    calls = []
    fake = SimpleNamespace(moveRel=lambda *args, **kwargs: calls.append((args, kwargs)))
    with patch.dict(sys.modules, {"pyautogui": fake}):
        result = execute_pointer_action({"action": "move", "dx": 9999, "dy": -9999})
    assert result["ok"] is True
    assert calls[0][0] == (160, -160)


def test_touchpad_rejects_non_allowlisted_hotkey():
    import sys
    from types import SimpleNamespace
    from unittest.mock import patch
    from dashboard.remote_control import execute_pointer_action

    calls = []
    fake = SimpleNamespace(hotkey=lambda *args, **kwargs: calls.append(args))
    with patch.dict(sys.modules, {"pyautogui": fake}):
        result = execute_pointer_action({"action": "hotkey", "keys": ["win", "r"]})
    assert result["ok"] is False
    assert not calls


def test_touchpad_websocket_executes_authenticated_input():
    server, token, headers = _paired_server()
    with patch("dashboard.server.execute_pointer_action", return_value={"ok": True}):
        with TestClient(server.app) as client:
            with client.websocket_connect(f"/ws/control?token={token}") as socket:
                socket.send_json({"action": "move", "dx": 12, "dy": -8})
                message = socket.receive_json()
    assert message["ok"] is True
    assert message["action"] == "move"


def test_pc_screen_websocket_streams_frames_only_to_paired_phone():
    server, token, headers = _paired_server()
    with patch("dashboard.server.capture_desktop_jpeg", return_value=b"\xff\xd8\xfffake-jpeg"):
        with TestClient(server.app) as client:
            with client.websocket_connect(f"/ws/desktop-screen?token={token}&fps=2") as socket:
                ready = socket.receive_json()
                frame = socket.receive_bytes()
    assert ready["type"] == "screen_ready"
    assert ready["fps"] == 2
    assert frame.startswith(b"\xff\xd8\xff")


def test_remote_type_text_uses_clipboard_and_restores_previous_content():
    import sys
    from types import SimpleNamespace
    from unittest.mock import patch
    from dashboard.remote_control import execute_pointer_action

    clipboard = {"value": "previous"}
    fake_clip = SimpleNamespace(
        paste=lambda: clipboard["value"],
        copy=lambda value: clipboard.__setitem__("value", value),
    )
    calls = []
    fake_auto = SimpleNamespace(hotkey=lambda *args, **kwargs: calls.append(args))
    with patch.dict(sys.modules, {"pyautogui": fake_auto, "pyperclip": fake_clip}):
        result = execute_pointer_action({"action": "type_text", "text": "Hello from ORI"})
    assert result["ok"] is True
    assert result["characters"] == len("Hello from ORI")
    assert calls == [("ctrl", "v")]
    assert clipboard["value"] == "previous"


def test_revoke_devices_invalidates_qr_access_tokens():
    import re
    server = DashboardServer()
    pairing_key = server.new_key()
    with TestClient(server.app) as client:
        page = client.get("/auto-login", params={"key": pairing_key})
        access_match = re.search(r"sessionStorage.setItem\('jarvis_token','([^']+)'", page.text)
        assert access_match
        access_token = access_match.group(1)
        assert access_token in server._tokens
        response = client.post("/api/revoke-devices", headers={"Authorization": f"Bearer {access_token}"})
    assert response.status_code == 200
    assert access_token not in server._tokens


def test_revoke_devices_invalidates_companion_access_token():
    server, token, headers = _paired_server()
    companion = "companion-access-token"
    server._tokens.add(companion)
    server._companion_access_tokens.add(companion)
    server._token_keys[companion] = "test-session-key"
    with TestClient(server.app) as client:
        response = client.post("/api/revoke-devices", headers=headers)
    assert response.status_code == 200
    assert companion not in server._tokens
    assert companion not in server._token_keys
    assert token in server._tokens  # The current dashboard session stays connected.
