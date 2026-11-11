"""Regression tests for ORI phone-remote startup and pairing links."""
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from cryptography import x509
from dashboard.server import DashboardServer, _ensure_certs, _find_available_port


class DashboardRemoteTests(unittest.TestCase):
    @patch("dashboard.server._local_ip", return_value="192.168.1.55")
    @patch("dashboard.server._ensure_certs", return_value=True)
    def test_https_transport_is_fixed_before_pairing_link_is_generated(self, _certs, _ip):
        # The cert files need not be visible to this test. The selected transport
        # must be the same one used by serve(), even while filesystem state differs.
        server = DashboardServer()
        self.assertTrue(server.port)
        self.assertEqual(server.get_url(), f"https://192.168.1.55:{server.port}")
        expected_manual_port = server.alias_port or server.port
        self.assertEqual(server.get_manual_url(), f"https://192.168.1.55:{expected_manual_port}")

    @patch("dashboard.server._local_ip", return_value="192.168.1.55")
    @patch("dashboard.server._ensure_certs", return_value=False)
    def test_http_fallback_uses_consistent_url(self, _certs, _ip):
        server = DashboardServer()
        self.assertTrue(server.port)
        self.assertEqual(server.get_url(), f"http://192.168.1.55:{server.port}")
        self.assertEqual(server.get_manual_url(), server.get_url())

    def test_certificate_is_regenerated_when_lan_ip_changes(self):
        # Simulate a laptop moving from one Wi-Fi network to another. A stale
        # certificate must not be reused for a QR URL with a different IP.
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("dashboard.server.BASE_DIR", Path(temp_dir)):
                self.assertTrue(_ensure_certs("192.168.1.55"))
                cert_path = Path(temp_dir) / "config" / "certs" / "jarvis.crt"
                first_cert_bytes = cert_path.read_bytes()

                self.assertTrue(_ensure_certs("192.168.1.99"))
                second_cert_bytes = cert_path.read_bytes()
                self.assertNotEqual(first_cert_bytes, second_cert_bytes)

                cert = x509.load_pem_x509_certificate(second_cert_bytes)
                san = cert.extensions.get_extension_for_class(
                    x509.SubjectAlternativeName
                ).value
                san_ips = {str(value) for value in san.get_values_for_type(x509.IPAddress)}
                self.assertIn("192.168.1.99", san_ips)

    @patch("dashboard.server._local_ip", return_value="192.168.1.55")
    @patch("dashboard.server._ensure_certs", return_value=False)
    def test_pairing_key_is_six_characters_and_registered(self, _certs, _ip):
        server = DashboardServer()
        key = server.new_key()
        self.assertEqual(len(key), 6)
        self.assertIn(key, server._pending_keys)

    @patch("dashboard.server._local_ip", return_value="192.168.1.55")
    @patch("dashboard.server._ensure_certs", return_value=False)
    def test_qr_auto_login_consumes_pairing_key(self, _certs, _ip):
        server = DashboardServer()
        key = server.new_key()
        with TestClient(server.app) as client:
            response = client.get("/auto-login", params={"key": key})
        self.assertEqual(response.status_code, 200)
        self.assertIn("jarvis_token", response.text)
        self.assertNotIn(key, server._pending_keys)


    def test_dynamic_port_skips_a_port_already_in_use(self):
        import socket
        reserved = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        reserved.bind(("127.0.0.1", 0))
        used_port = reserved.getsockname()[1]
        try:
            selected = _find_available_port(used_port, attempts=8)
            self.assertIsNotNone(selected)
            self.assertNotEqual(selected, used_port)
            probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                probe.bind(("127.0.0.1", selected))
            finally:
                probe.close()
        finally:
            reserved.close()

    def test_desktop_screenshot_requires_pairing_authentication(self):
        server = DashboardServer()
        with TestClient(server.app) as client:
            response = client.get("/api/desktop/screenshot")
        self.assertEqual(response.status_code, 401)

    def test_desktop_mic_control_requires_pairing_authentication(self):
        server = DashboardServer()
        with TestClient(server.app) as client:
            response = client.get("/api/desktop-mic")
        self.assertEqual(response.status_code, 401)

    def test_authenticated_phone_can_read_and_change_desktop_mic(self):
        server = DashboardServer()
        state = {"muted": False}

        def set_mic(value):
            if value is None:
                return state["muted"]
            state["muted"] = bool(value)
            return state["muted"]

        server.set_desktop_mute_callback(set_mic)
        token = "paired-device-token"
        server._tokens.add(token)
        headers = {"Authorization": f"Bearer {token}"}
        with TestClient(server.app) as client:
            before = client.get("/api/desktop-mic", headers=headers)
            after = client.post("/api/desktop-mic", json={"muted": True}, headers=headers)
        self.assertEqual(before.status_code, 200)
        self.assertFalse(before.json()["muted"])
        self.assertEqual(after.status_code, 200)
        self.assertTrue(after.json()["muted"])



if __name__ == "__main__":
    unittest.main()
