"""
dashboard/server.py — ORI Local HTTP Dashboard

Local phone dashboard on an available LAN port; transport is fixed before the QR link is shown.
Security at the application layer: AES-256-CBC with session-key-derived key.
CryptoJS is auto-downloaded once and served locally — no CDN needed after that.

Install deps:  pip install fastapi "uvicorn[standard]" cryptography
"""

import asyncio
import base64
import hashlib
import re
import secrets
import socket
import string
import sys
import time
from pathlib import Path

from .remote_control import capture_desktop_jpeg, execute_pointer_action, validate_phone_screen_frame

_DEPS_OK = False
try:
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
    from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, Response
    import uvicorn
    _DEPS_OK = True
except ImportError:
    pass

# python-multipart is required for file uploads — optional dependency
_UPLOAD_OK = False
try:
    from fastapi import UploadFile, File as FastAPIFile
    _UPLOAD_OK = True
except Exception:
    pass

def _application_root() -> Path:
    """Return the writable application directory in source and frozen builds."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _resolve_static_dir() -> Path:
    """Locate bundled Phone Remote HTML assets without relying on PYZ __file__."""
    module_static = Path(__file__).resolve().parent / "static"
    candidates = [module_static]
    if getattr(sys, "frozen", False):
        bundle_root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
        app_root = Path(sys.executable).resolve().parent
        candidates = [
            bundle_root / "dashboard" / "static",
            app_root / "dashboard" / "static",
            module_static,
        ]
    seen = set()
    for candidate in candidates:
        key = str(candidate.resolve())
        if key in seen:
            continue
        seen.add(key)
        if all((candidate / name).is_file() for name in ("app.html", "login.html", "crypto-js.js")):
            return candidate
    # Keep a deterministic path so _read() can report the precise missing file.
    return candidates[0]


BASE_DIR    = _application_root()
STATIC_DIR  = _resolve_static_dir()
_CRYPTOJS_FILE = STATIC_DIR / "crypto-js.js"
PORT        = 8000
MAX_UPLOAD_MB = 500


def _find_available_port(start: int = PORT, attempts: int = 32, exclude: set[int] | None = None) -> int | None:
    """Choose a free LAN port instead of failing when the default port is occupied."""
    blocked = set(exclude or ())
    for candidate in range(int(start), int(start) + max(1, int(attempts))):
        if candidate in blocked:
            continue
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            probe.bind(("0.0.0.0", candidate))
            return candidate
        except OSError:
            continue
        finally:
            probe.close()
    return None


def _make_uploads_dir() -> Path:
    """Return (and create) the cross-platform uploads folder."""
    for candidate in [
        Path.home() / "Downloads" / "ORI Uploads",
        Path.home() / "Documents" / "ORI Uploads",
        BASE_DIR / "uploads",
    ]:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            return candidate
        except Exception:
            pass
    return BASE_DIR / "uploads"


UPLOADS_DIR = _make_uploads_dir()

def _get_gemini_key() -> str | None:
    try:
        import json as _json
        with open(BASE_DIR / "config" / "api_keys.json", "r", encoding="utf-8") as f:
            return _json.load(f).get("gemini_api_key")
    except Exception:
        return None

_KEY_CHARS = [c for c in (string.ascii_uppercase + string.digits)
              if c not in ('O', 'I', 'L', '0', '1')]

# ── AES-256-CBC ───────────────────────────────────────────────────────────────
_AES_SALT = b'JARVIS-DASHBOARD-v1'


def _derive_key(session_key: str) -> bytes:
    """SHA-256(sessionKey‖salt) → 32-byte AES-256 key (microseconds, no PBKDF2 needed)."""
    return hashlib.sha256(session_key.encode('utf-8') + _AES_SALT).digest()


def _decrypt_cbc(aes_key: bytes, enc_b64: str) -> str:
    """Decrypt base64(IV[16] ‖ ciphertext) with AES-256-CBC + PKCS7."""
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.primitives import padding as sym_pad
    raw      = base64.b64decode(enc_b64)
    iv, ct   = raw[:16], raw[16:]
    dec      = Cipher(algorithms.AES(aes_key), modes.CBC(iv)).decryptor()
    padded   = dec.update(ct) + dec.finalize()
    unpadder = sym_pad.PKCS7(128).unpadder()
    return (unpadder.update(padded) + unpadder.finalize()).decode('utf-8')


# ── CryptoJS (auto-download once, served locally) ─────────────────────────────


def _ensure_network_access(port: int) -> None:
    """Offer a narrowly scoped Private-network firewall rule on Windows.

    ORI never changes a Wi-Fi/Ethernet profile from Public to Private. If the
    active network is Public, it leaves the profile untouched and explains
    that LAN pairing requires a trusted Private network or a manually approved
    firewall exception. On a Private network only, an optional one-time UAC
    prompt creates a TCP rule limited to the local subnet.
    """
    if sys.platform != "win32":
        return

    import ctypes
    import os
    import subprocess
    import tempfile

    def _run(command: list[str], timeout: float = 6.0):
        try:
            return subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception:
            return None

    # Do not silently convert a Public network to Private. That is a Windows
    # security setting and belongs to the user.
    profile = _run([
        "powershell", "-NoProfile", "-NonInteractive", "-Command",
        "$p=Get-NetConnectionProfile | Where-Object {$_.IPv4Connectivity -ne 'Disconnected' -or $_.IPv6Connectivity -ne 'Disconnected'}; "
        "if ($p) { ($p | ForEach-Object {$_.NetworkCategory.ToString()}) -join ',' }"
    ])
    categories = (profile.stdout.strip().lower() if profile else "")
    if "public" in categories:
        print(
            "[Dashboard] LAN remote is not opening a firewall rule on a Public network. "
            "Use a trusted Private Wi-Fi network and allow ORI on Private networks only."
        )
        return

    if "private" not in categories:
        print(
            "[Dashboard] Network profile could not be confirmed as Private. "
            "No firewall or network-profile changes were made."
        )
        return

    rule_name = f"ORI Dashboard Port {int(port)}"
    exists = _run([
        "netsh", "advfirewall", "firewall", "show", "rule", f"name={rule_name}"
    ])
    if exists and exists.returncode == 0 and "No rules match" not in (exists.stdout or ""):
        return

    bat_lines = [
        "@echo off",
        f'netsh advfirewall firewall add rule name="{rule_name}" protocol=TCP '
        f'dir=in localport={int(port)} action=allow profile=private remoteip=localsubnet',
    ]
    body = "\r\n".join(bat_lines) + "\r\n"
    fd, bat_path = tempfile.mkstemp(suffix=".bat", prefix="ori_lan_firewall_")
    try:
        os.write(fd, body.encode("mbcs"))
        os.close(fd)
    except Exception:
        try:
            os.close(fd)
        except Exception:
            pass
        return

    print(
        "[Dashboard] Windows may ask once to allow ORI on your Private local network. "
        "This does not change your network profile or create a Public-network rule."
    )
    try:
        result = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", bat_path, None, None, 0
        )
        if int(result) <= 32:
            print("[Dashboard] Firewall permission was not granted; LAN pairing may be blocked.")
    except Exception:
        print("[Dashboard] Firewall rule was not added; LAN pairing may be blocked.")
    finally:
        # The elevated process may still be executing. The temporary file is
        # intentionally left for Windows to consume and is cleaned on next boot.
        pass


# Do not download browser assets while importing the desktop application.
# A first-run network request here can block packaged ORI before the phone server
# is constructed. If the optional local asset is absent, /static/crypto.js
# redirects the phone browser to the pinned CDN URL on demand.


# ── helpers ───────────────────────────────────────────────────────────────────

def _local_ip() -> str:
    """Choose a LAN-facing IPv4 address, preferring the real Wi-Fi/Ethernet NIC."""
    # UDP route lookup does not send a packet; it asks Windows which interface
    # would carry normal internet traffic. This avoids selecting VPN/Hyper-V NICs.
    for probe in ("8.8.8.8", "1.1.1.1"):
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(0.5)
            sock.connect((probe, 80))
            ip = sock.getsockname()[0]
            if ip and not ip.startswith(("127.", "169.254.")):
                return ip
        except Exception:
            pass
        finally:
            if sock is not None:
                try:
                    sock.close()
                except Exception:
                    pass

    # Offline fallback: prefer named Wi-Fi/Ethernet adapters and ignore common
    # virtual/VPN interfaces. Hostname resolution is the final fallback only.
    try:
        import ipaddress
        import psutil

        stats = psutil.net_if_stats()
        preferred = ("wi-fi", "wifi", "wlan", "wireless", "ethernet", "eth")
        excluded = (
            "virtual", "vmware", "hyper-v", "vbox", "virtualbox", "wsl",
            "docker", "loopback", "bluetooth", "vpn", "tailscale",
            "wireguard", "tap", "tunnel", "host-only",
        )
        candidates = []
        for name, addresses in psutil.net_if_addrs().items():
            stat = stats.get(name)
            if not stat or not stat.isup:
                continue
            lname = name.lower()
            if any(word in lname for word in excluded):
                continue
            for address in addresses:
                if address.family != socket.AF_INET:
                    continue
                try:
                    parsed = ipaddress.ip_address(address.address)
                except ValueError:
                    continue
                if parsed.is_loopback or parsed.is_link_local or parsed.is_unspecified:
                    continue
                candidates.append((0 if any(word in lname for word in preferred) else 1,
                                   0 if parsed.is_private else 1, address.address))
        if candidates:
            candidates.sort()
            return candidates[0][2]
    except Exception:
        pass

    try:
        ip = socket.gethostbyname(socket.gethostname())
        if not ip.startswith(("127.", "169.254.")):
            return ip
    except Exception:
        pass
    return "127.0.0.1"


def _ensure_certs(lan_ip: str | None = None) -> bool:
    """
    Make sure config/certs holds a TLS key pair, generating a self-signed one the
    first time the dashboard runs.

    The pair is deliberately NOT shipped in the repository. A private key that
    every user downloads is the same as having no private key at all: anyone can
    present a certificate that matches it. Generating locally gives each install
    its own key, costs about a second, and happens exactly once.

    Returns True when a usable pair exists afterwards; False leaves the caller on
    plain HTTP, which still works — the QR code simply encodes http:// instead.
    """
    certs = BASE_DIR / "config" / "certs"
    key_p = certs / "jarvis.key"
    crt_p = certs / "jarvis.crt"

    try:
        import datetime
        import ipaddress
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID
    except ImportError:
        print("[Dashboard] cryptography not installed — serving over plain HTTP.")
        print("[Dashboard] For HTTPS run:  pip install cryptography")
        return False

    try:
        # A laptop's Wi-Fi address can change between launches. Reusing the
        # previous certificate would leave the QR URL pointing at an IP that is
        # missing from the certificate SAN, which some phone browsers reject.
        # Also reject a truncated/expired cert or a key that does not match it.
        current_ip = lan_ip or _local_ip()
        if key_p.exists() and crt_p.exists():
            try:
                existing_cert = x509.load_pem_x509_certificate(crt_p.read_bytes())
                existing_key = serialization.load_pem_private_key(
                    key_p.read_bytes(), password=None
                )
                cert_public = existing_cert.public_key().public_bytes(
                    serialization.Encoding.DER,
                    serialization.PublicFormat.SubjectPublicKeyInfo,
                )
                key_public = existing_key.public_key().public_bytes(
                    serialization.Encoding.DER,
                    serialization.PublicFormat.SubjectPublicKeyInfo,
                )
                valid_before = getattr(existing_cert, "not_valid_before_utc", None)
                valid_after = getattr(existing_cert, "not_valid_after_utc", None)
                if valid_before is None:
                    valid_before = existing_cert.not_valid_before.replace(
                        tzinfo=datetime.timezone.utc
                    )
                if valid_after is None:
                    valid_after = existing_cert.not_valid_after.replace(
                        tzinfo=datetime.timezone.utc
                    )
                san = existing_cert.extensions.get_extension_for_class(
                    x509.SubjectAlternativeName
                ).value
                san_ips = {str(value) for value in san.get_values_for_type(x509.IPAddress)}
                cert_is_valid = (
                    cert_public == key_public
                    and valid_before <= datetime.datetime.now(datetime.timezone.utc) <= valid_after
                    and "127.0.0.1" in san_ips
                    and (current_ip.startswith("127.") or current_ip in san_ips)
                    and "localhost" in san.get_values_for_type(x509.DNSName)
                )
                if cert_is_valid:
                    return True
                print("[Dashboard] Existing certificate is stale or invalid; regenerating it.")
            except Exception as exc:
                print(f"[Dashboard] Existing certificate could not be reused ({exc}); regenerating it.")

        certs.mkdir(parents=True, exist_ok=True)
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

        who = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, "ORI Dashboard"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "ORI"),
        ])

        # The SAN has to cover every address the phone might use: the LAN IP the
        # QR code encodes, plus localhost when testing on the machine itself.
        alt = [x509.DNSName("localhost"),
               x509.IPAddress(ipaddress.IPv4Address("127.0.0.1"))]
        try:
            lan = current_ip
            if not lan.startswith("127."):
                alt.append(x509.IPAddress(ipaddress.IPv4Address(lan)))
        except Exception:
            pass          # no LAN address resolvable — localhost entries still work

        # Timezone-aware UTC: datetime.utcnow() is deprecated from Python 3.12 on,
        # and the builder normalises aware values to UTC itself.
        now = datetime.datetime.now(datetime.timezone.utc)
        cert = (
            x509.CertificateBuilder()
            .subject_name(who)
            .issuer_name(who)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(days=1))
            .not_valid_after(now + datetime.timedelta(days=3650))
            .add_extension(x509.SubjectAlternativeName(alt), critical=False)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .sign(key, hashes.SHA256())
        )

        key_p.write_bytes(key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        ))
        crt_p.write_bytes(cert.public_bytes(serialization.Encoding.PEM))

        try:
            import os as _os
            _os.chmod(key_p, 0o600)   # best effort — largely a no-op on Windows
        except Exception:
            pass

        print(f"[Dashboard] Generated a self-signed certificate for this machine: {certs}")
        return True
    except Exception as e:
        print(f"[Dashboard] Certificate generation failed ({e}) — serving over plain HTTP.")
        return False


def _read(name: str) -> str:
    asset = STATIC_DIR / name
    if not asset.is_file():
        raise FileNotFoundError(
            f"Phone Remote asset '{name}' was not found in the packaged runtime: {asset}"
        )
    return asset.read_text(encoding="utf-8")


# ── DashboardServer ───────────────────────────────────────────────────────────

class DashboardServer:

    def __init__(self):
        self._ip                          = _local_ip()
        self.port                         = _find_available_port(PORT)
        if self.port is None:
            self._startup_error = f"No free local port found in {PORT}-{PORT + 31}."
            self.alias_port = None
        else:
            self.alias_port = _find_available_port(self.port + 1, exclude={self.port})
        # Resolve the transport before the UI can request a pairing link.  If the
        # QR link is generated while the certificate is still being created, it
        # can contain http:// even though serve() later binds HTTPS on that port.
        # DashboardServer is constructed on ORI's runtime thread, not the Qt UI
        # thread, so first-run certificate generation will not freeze the window.
        self._use_ssl                     = bool(_ensure_certs(self._ip)) if _DEPS_OK else False
        self._running                     = False
        self._uvicorn_server = None
        self._startup_error               = getattr(self, "_startup_error", "")
        self._status_callback             = None
        self._access_callback             = None
        self._tokens: set[str]            = set()
        self._token_keys: dict[str, str]  = {}   # auth_token → session_key
        self._aes_cache:  dict[str, bytes]= {}   # session_key → AES bytes
        self._clients: set[WebSocket]     = set()
        self._history: list[dict]         = []
        self._command_queue               = asyncio.Queue()
        self._wake_callback               = None
        self._connect_callback            = None
        self._interrupt_callback          = None
        self._desktop_mute_callback       = None
        self._pending_keys: dict[str, float] = {}
        self._device_sessions: dict[str, dict] = {}  # device_token → {session_key}
        self._phone_audio_queue: asyncio.Queue    = asyncio.Queue(maxsize=200)
        self._phone_screen_queue: asyncio.Queue   = asyncio.Queue(maxsize=1)
        self._phone_screen_latest: dict | None = None  # in-memory only; never written to disk
        self._remote_action_times: dict[str, list[float]] = {}
        self._companion_codes: dict[str, dict] = {}
        self._companion_access_tokens: set[str] = set()
        self._uploads_dir                 = UPLOADS_DIR
        self._login_html                  = _read("login.html")
        self._app_html                    = _read("app.html")
        self.app                          = self._build_app()

    # ── one-time key management ───────────────────────────────────────────

    def new_key(self, expiry_secs: int = 600) -> str:
        now = time.time()
        self._pending_keys = {k: v for k, v in self._pending_keys.items() if v > now}
        key = ''.join(secrets.choice(_KEY_CHARS) for _ in range(6))
        self._pending_keys[key] = now + expiry_secs
        return key

    @staticmethod
    def _ssl_enabled() -> bool:
        certs = BASE_DIR / "config" / "certs"
        return (certs / "jarvis.key").exists() and (certs / "jarvis.crt").exists()

    @property
    def is_running(self) -> bool:
        """Whether the primary dashboard server has completed startup."""
        return self._running

    def set_status_callback(self, fn) -> None:
        """Register a callback receiving (url, running) from the server thread."""
        self._status_callback = fn

    def set_access_callback(self, fn) -> None:
        """Register a thread-safe UI callback for active remote capabilities."""
        self._access_callback = fn

    def _notify_access(self, name: str, active: bool) -> None:
        callback = self._access_callback
        if callback is None:
            return
        try:
            callback(str(name), bool(active))
        except Exception as exc:
            print(f"[Dashboard] Access indicator update failed: {type(exc).__name__}")

    def _notify_status(self, running: bool) -> None:
        callback = self._status_callback
        if callback is None:
            return
        try:
            callback(self.get_url() if running else '', bool(running), self._startup_error)
        except TypeError:
            try:
                callback(self.get_url() if running else '', bool(running))
            except Exception as exc:
                print(f"[Dashboard] Could not update UI status: {exc}")
        except Exception as exc:
            print(f"[Dashboard] Could not update UI status: {exc}")

    def get_url(self) -> str:
        # Use the transport chosen during construction, not the file state at
        # the time a button happens to be clicked.
        proto = "https" if self._use_ssl else "http"
        return f"{proto}://{self._ip}:{self.port or PORT}"

    def get_manual_url(self) -> str:
        """Fully qualified URL for manual entry, matching the selected transport."""
        if self._use_ssl and self.alias_port:
            return f"https://{self._ip}:{self.alias_port}"
        return self.get_url()

    def _aes_key(self, session_key: str) -> bytes:
        if session_key not in self._aes_cache:
            self._aes_cache[session_key] = _derive_key(session_key)
        return self._aes_cache[session_key]

    def _decrypt(self, token: str, enc_b64: str) -> str | None:
        sk = self._token_keys.get(token)
        if not sk:
            return None
        try:
            return _decrypt_cbc(self._aes_key(sk), enc_b64)
        except Exception:
            return None

    def _rate_limit_remote_action(self, token: str, limit: int = 50) -> bool:
        """Per-device sliding one-second limit for high-frequency remote input."""
        now = time.monotonic()
        recent = [stamp for stamp in self._remote_action_times.get(token, []) if now - stamp < 1.0]
        if len(recent) >= limit:
            self._remote_action_times[token] = recent
            return False
        recent.append(now)
        self._remote_action_times[token] = recent
        return True

    def _queue_phone_screen_analysis(self, prompt: str = "Describe the shared phone screen and help with what is visible.") -> bool:
        """Queue the latest explicitly-shared phone frame for Gemini; keep only one."""
        item = self._phone_screen_latest
        if not item or (time.time() - float(item.get("captured_at", 0))) > 30:
            return False
        payload = {
            "data": item["data"],
            "mime_type": item.get("mime_type", "image/jpeg"),
            "prompt": str(prompt or "Describe the shared phone screen.")[:1200],
            "captured_at": item.get("captured_at", time.time()),
        }
        try:
            while self._phone_screen_queue.full():
                self._phone_screen_queue.get_nowait()
            self._phone_screen_queue.put_nowait(payload)
        except Exception:
            return False
        return True

    # ── callbacks ────────────────────────────────────────────────────────

    def set_wake_callback(self, fn) -> None:
        self._wake_callback = fn

    def set_connect_callback(self, fn) -> None:
        self._connect_callback = fn

    def set_interrupt_callback(self, fn) -> None:
        self._interrupt_callback = fn

    def set_desktop_mute_callback(self, fn) -> None:
        """Callback accepts True/False to set state or None to query current state."""
        self._desktop_mute_callback = fn

    # ── broadcast ────────────────────────────────────────────────────────

    async def broadcast(self, msg: dict, *, remember: bool = True) -> None:
        if remember:
            self._history.append(msg)
            if len(self._history) > 300:
                self._history = self._history[-300:]
        dead: set[WebSocket] = set()
        for ws in list(self._clients):
            try:
                await ws.send_json(msg)
            except Exception:
                dead.add(ws)
        self._clients -= dead

    # ── FastAPI app ───────────────────────────────────────────────────────

    def _build_app(self) -> "FastAPI":
        app = FastAPI(docs_url=None, redoc_url=None)

        def _auth(req: Request) -> bool:
            tok = req.headers.get("authorization", "").removeprefix("Bearer ").strip()
            return bool(tok) and tok in self._tokens

        # serve CryptoJS from local cache, fallback to CDN redirect
        @app.get("/static/crypto.js")
        async def serve_crypto():
            if _CRYPTOJS_FILE.is_file():
                return FileResponse(
                    str(_CRYPTOJS_FILE),
                    media_type="application/javascript",
                    headers={"Cache-Control": "public, max-age=31536000, immutable"},
                )
            return JSONResponse(
                {"ok": False, "error": "The bundled Phone Remote encryption asset is missing."},
                status_code=503,
            )

        @app.get("/login", response_class=HTMLResponse)
        async def login_page():
            return HTMLResponse(self._login_html)

        @app.get("/", response_class=HTMLResponse)
        async def index():
            # Auth is handled client-side via sessionStorage bearer token.
            # Server-side header auth can't work here because browser navigations
            # don't send custom headers (location.href doesn't carry Authorization).
            html = (self._app_html
                    .replace("__IP__", self._ip)
                    .replace("__PORT__", str(self.port or PORT)))
            return HTMLResponse(html)

        @app.get("/health")
        async def health():
            return JSONResponse({
                "ok": True,
                "app": "ORI",
                "version": "3.5.0",
                "dashboard": "ready",
                "https": bool(self._use_ssl),
                "port": int(self.port or 0),
            })

        @app.post("/login")
        async def login(req: Request):
            body    = await req.json()
            entered = str(body.get("pin", "")).strip().upper()
            now     = time.time()
            if entered in self._pending_keys and self._pending_keys[entered] > now:
                del self._pending_keys[entered]          # one-time use
                tok = secrets.token_urlsafe(32)
                self._tokens.add(tok)
                self._token_keys[tok] = entered
                self._aes_key(entered)                   # pre-derive & cache
                if self._connect_callback:
                    self._connect_callback()
                asyncio.create_task(self.broadcast(
                    {"type": "sys", "text": "Remote connection established."}
                ))
                # Bearer token in response body — no cookies needed (works on any browser/HTTP)
                return JSONResponse({"ok": True, "token": tok})
            return JSONResponse({"ok": False, "error": "Invalid or expired key"},
                                status_code=401)

        @app.get("/auto-login")
        async def auto_login(key: str = ""):
            """QR code target — validates one-time key, creates session, redirects phone."""
            now = time.time()
            if not key or key not in self._pending_keys or self._pending_keys[key] <= now:
                return HTMLResponse("""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width">
<style>
  body{background:#07090f;color:#dde3ed;font-family:sans-serif;
       display:flex;align-items:center;justify-content:center;height:100vh;margin:0;text-align:center}
  h2{color:#f87171;margin-bottom:12px}p{color:#5e6a7e;font-size:14px}
</style></head>
<body><div><h2>Link Expired</h2>
<p>Press <strong style="color:#dde3ed">Remote Control</strong> in ORI to get a new QR code.</p>
</div></body></html>""")

            del self._pending_keys[key]
            tok     = secrets.token_urlsafe(32)
            dev_tok = secrets.token_urlsafe(32)
            self._tokens.add(tok)
            self._token_keys[tok] = key
            self._aes_key(key)
            self._device_sessions[dev_tok] = {"session_key": key, "active_tokens": {tok}}

            if self._connect_callback:
                self._connect_callback()
            asyncio.create_task(self.broadcast(
                {"type": "sys", "text": "Remote connection established via QR code."}
            ))

            return HTMLResponse(f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width">
<style>
  body{{background:#07090f;color:#dde3ed;font-family:sans-serif;
       display:flex;align-items:center;justify-content:center;height:100vh;margin:0;text-align:center}}
  p{{color:#5e6a7e;font-size:14px}}
</style></head>
<body>
<script>
  sessionStorage.setItem('jarvis_token','{tok}');
  sessionStorage.setItem('jarvis_key','{key}');
  localStorage.setItem('jarvis_device_token','{dev_tok}');
  setTimeout(function(){{location.replace('/')}},400);
</script>
<p>Connecting to ORI…</p>
</body></html>""")

        @app.post("/api/device-login")
        async def device_login_ep(req: Request):
            """Return a fresh auth token for a previously paired device token."""
            try:
                body = await req.json()
            except Exception:
                return JSONResponse({"ok": False}, status_code=400)
            dev_tok = (body.get("device_token") or "").strip()
            if not dev_tok or dev_tok not in self._device_sessions:
                return JSONResponse({"ok": False}, status_code=401)
            session_key = self._device_sessions[dev_tok]["session_key"]
            tok = secrets.token_urlsafe(32)
            self._tokens.add(tok)
            self._token_keys[tok] = session_key
            self._device_sessions[dev_tok].setdefault("active_tokens", set()).add(tok)
            self._aes_key(session_key)
            if self._connect_callback:
                self._connect_callback()
            asyncio.create_task(self.broadcast(
                {"type": "sys", "text": "Known device reconnected automatically."}
            ))
            return JSONResponse({"ok": True, "token": tok, "key": session_key})

        @app.post("/api/revoke-devices")
        async def revoke_devices(req: Request):
            """Invalidate all persistent device tokens (admin action)."""
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            count = len(self._device_sessions) + len(self._companion_access_tokens)
            paired_access_tokens = set(self._companion_access_tokens)
            for device in self._device_sessions.values():
                paired_access_tokens.update(device.get("active_tokens", set()))
            self._tokens.difference_update(paired_access_tokens)
            for access_token in paired_access_tokens:
                self._token_keys.pop(access_token, None)
            self._device_sessions.clear()
            self._companion_access_tokens.clear()
            return JSONResponse({"ok": True, "revoked": count})

        @app.get("/api/desktop/screenshot")
        async def desktop_screenshot(req: Request):
            """Capture the desktop only after an authenticated, explicit phone request."""
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            try:
                import io
                import mss
                from PIL import Image
                with mss.mss() as capture:
                    monitor = capture.monitors[0]
                    shot = capture.grab(monitor)
                    image = Image.frombytes("RGB", shot.size, shot.rgb)
                image.thumbnail((1920, 1080))
                output = io.BytesIO()
                image.save(output, format="JPEG", quality=78, optimize=True)
                return Response(
                    content=output.getvalue(),
                    media_type="image/jpeg",
                    headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
                )
            except Exception as exc:
                return JSONResponse(
                    {"ok": False, "error": f"Screen capture unavailable: {type(exc).__name__}."},
                    status_code=503,
                )

        @app.post("/api/command")
        async def command(req: Request):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            body  = await req.json()
            token = req.headers.get("authorization", "").removeprefix("Bearer ").strip()
            enc   = body.get("enc", "")
            if enc:
                text = self._decrypt(token, enc)
                if text is None:
                    return JSONResponse({"error": "Decryption failed"}, status_code=400)
            else:
                text = (body.get("text") or "").strip()
            if text:
                await self._command_queue.put(text)
                if self._wake_callback:
                    self._wake_callback()
            return JSONResponse({"ok": True})

        @app.post("/api/wake")
        async def wake_ep(req: Request):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            if self._wake_callback:
                self._wake_callback()
            return JSONResponse({"ok": True})

        @app.post("/api/interrupt")
        async def interrupt_ep(req: Request):
            """Immediately stop the active assistant speech for an authenticated phone."""
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            if not self._interrupt_callback:
                return JSONResponse({"ok": False, "error": "Interrupt control is unavailable"}, status_code=503)
            try:
                self._interrupt_callback()
                asyncio.create_task(self.broadcast({"type": "sys", "text": "Speech interrupted from remote phone."}))
                return JSONResponse({"ok": True})
            except Exception as exc:
                return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)

        @app.get("/api/desktop-mic")
        async def get_desktop_mic(req: Request):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            if not self._desktop_mute_callback:
                return JSONResponse(
                    {"ok": False, "error": "Desktop microphone control is unavailable."},
                    status_code=503,
                )
            try:
                muted = bool(self._desktop_mute_callback(None))
                return JSONResponse({"ok": True, "muted": muted})
            except Exception as exc:
                return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)

        @app.post("/api/desktop-mic")
        async def set_desktop_mic(req: Request):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            if not self._desktop_mute_callback:
                return JSONResponse(
                    {"ok": False, "error": "Desktop microphone control is unavailable."},
                    status_code=503,
                )
            try:
                body = await req.json()
                if not isinstance(body.get("muted"), bool):
                    return JSONResponse(
                        {"ok": False, "error": "A boolean 'muted' value is required."},
                        status_code=400,
                    )
                muted = bool(self._desktop_mute_callback(body["muted"]))
                await self.broadcast({"type": "desktop_mic", "muted": muted})
                return JSONResponse({"ok": True, "muted": muted})
            except Exception as exc:
                return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)

        @app.post("/api/remote/action")
        async def remote_action(req: Request):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            token = req.headers.get("authorization", "").removeprefix("Bearer ").strip()
            if not self._rate_limit_remote_action(token, limit=35):
                return JSONResponse({"ok": False, "error": "Remote input rate limit reached."}, status_code=429)
            try:
                body = await req.json()
                result = await asyncio.to_thread(execute_pointer_action, body)
                return JSONResponse(result, status_code=200 if result.get("ok") else 400)
            except Exception as exc:
                return JSONResponse({"ok": False, "error": type(exc).__name__}, status_code=500)

        @app.post("/api/companion/create-code")
        async def create_companion_code(req: Request):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            token = req.headers.get("authorization", "").removeprefix("Bearer ").strip()
            session_key = self._token_keys.get(token)
            if not session_key:
                return JSONResponse({"ok": False, "error": "The paired session has expired."}, status_code=401)
            now = time.time()
            self._companion_codes = {key: item for key, item in self._companion_codes.items() if item.get("expires", 0) > now}
            code = "".join(secrets.choice("23456789ABCDEFGHJKLMNPQRSTUVWXYZ") for _ in range(8))
            self._companion_codes[code] = {"session_key": session_key, "expires": now + 300}
            return JSONResponse({"ok": True, "code": code, "expires_in": 300, "base_url": self.get_url()})

        @app.post("/api/companion/pair")
        async def pair_companion(req: Request):
            try:
                body = await req.json()
            except Exception:
                body = {}
            code = str(body.get("code", "")).strip().upper()
            item = self._companion_codes.pop(code, None)
            if not item or float(item.get("expires", 0)) <= time.time():
                return JSONResponse({"ok": False, "error": "Pairing code is invalid or expired."}, status_code=401)
            token = secrets.token_urlsafe(32)
            self._tokens.add(token)
            self._token_keys[token] = item["session_key"]
            self._companion_access_tokens.add(token)
            return JSONResponse({"ok": True, "token": token, "upload_endpoint": "/api/phone-screen/frame"})

        @app.post("/api/phone-screen/frame")
        async def phone_screen_frame(req: Request):
            """Accept a user-initiated screen-share frame; it stays in RAM only."""
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            data = await req.body()
            if not validate_phone_screen_frame(data):
                return JSONResponse({"ok": False, "error": "Invalid or oversized image frame."}, status_code=413)
            mime = req.headers.get("content-type", "image/jpeg").split(";", 1)[0].strip().lower()
            if mime not in {"image/jpeg", "image/png"}:
                mime = "image/jpeg" if data.startswith(b"\xff\xd8\xff") else "image/png"
            self._notify_access("phone", True)
            self._notify_access("screen", True)
            try:
                self._phone_screen_latest = {"data": data, "mime_type": mime, "captured_at": time.time()}
            finally:
                self._notify_access("screen", False)
                self._notify_access("phone", False)
            return JSONResponse({"ok": True, "bytes": len(data), "captured_at": self._phone_screen_latest["captured_at"]})

        @app.post("/api/phone-screen/analyze")
        async def analyze_phone_screen(req: Request):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            try:
                body = await req.json()
            except Exception:
                body = {}
            prompt = str(body.get("prompt") or "Describe the shared phone screen and help with what is visible.")
            if not self._queue_phone_screen_analysis(prompt):
                return JSONResponse({"ok": False, "error": "No recent phone screen frame. Start screen sharing first."}, status_code=409)
            if self._wake_callback:
                self._wake_callback()
            return JSONResponse({"ok": True, "queued": True})

        @app.get("/api/phone-screen/status")
        async def phone_screen_status(req: Request):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            item = self._phone_screen_latest
            age = (time.time() - item["captured_at"]) if item else None
            return JSONResponse({"shared": bool(item and age is not None and age <= 30), "age_seconds": round(age, 2) if age is not None else None})

        @app.websocket("/ws/control")
        async def control_ws(websocket: WebSocket, token: str = ""):
            tok = token.strip()
            if not tok or tok not in self._tokens:
                await websocket.close(code=4001)
                return
            await websocket.accept()
            try:
                while True:
                    payload = await websocket.receive_json()
                    if not self._rate_limit_remote_action(tok, limit=70):
                        await websocket.send_json({"ok": False, "error": "rate_limited"})
                        continue
                    action_name = str(payload.get("action", "")).lower()
                    key_actions = {"type", "type_text", "press_key", "hotkey", "key_down", "key_up"}
                    indicator = "keyboard" if action_name in key_actions else "mouse"
                    self._notify_access(indicator, True)
                    try:
                        result = await asyncio.to_thread(execute_pointer_action, payload)
                    finally:
                        self._notify_access(indicator, False)
                    await websocket.send_json({"ok": bool(result.get("ok")), "action": payload.get("action", ""), "error": result.get("error", "")})
            except WebSocketDisconnect:
                pass
            except Exception as exc:
                print(f"[Dashboard] Control socket ended: {type(exc).__name__}")
            finally:
                try:
                    await websocket.close()
                except Exception:
                    pass

        @app.websocket("/ws/desktop-screen")
        async def desktop_screen_ws(websocket: WebSocket, token: str = "", fps: int = 5):
            tok = token.strip()
            if not tok or tok not in self._tokens:
                await websocket.close(code=4001)
                return
            await websocket.accept()
            self._notify_access("screen", True)
            target_fps = max(1, min(8, int(fps or 5)))
            interval = 1.0 / target_fps
            try:
                await websocket.send_json({"type": "screen_ready", "fps": target_fps})
                while True:
                    started = time.monotonic()
                    frame = await asyncio.to_thread(capture_desktop_jpeg, 1440, 62)
                    await websocket.send_bytes(frame)
                    delay = interval - (time.monotonic() - started)
                    if delay > 0:
                        await asyncio.sleep(delay)
            except WebSocketDisconnect:
                pass
            except Exception as exc:
                try:
                    await websocket.send_json({"type": "screen_error", "message": f"Screen capture failed: {type(exc).__name__}."})
                except Exception:
                    pass
            finally:
                self._notify_access("screen", False)
                try:
                    await websocket.close()
                except Exception:
                    pass

        @app.websocket("/ws/phone-screen")
        async def phone_screen_ws(websocket: WebSocket, token: str = ""):
            """Receive screen frames from a browser/companion after explicit user consent."""
            tok = token.strip()
            if not tok or tok not in self._tokens:
                await websocket.close(code=4001)
                return
            await websocket.accept()
            self._notify_access("phone", True)
            self._notify_access("screen", True)
            try:
                await websocket.send_json({"type": "phone_screen_ready"})
                while True:
                    event = await websocket.receive()
                    data = event.get("bytes")
                    if data is not None:
                        if validate_phone_screen_frame(data):
                            self._phone_screen_latest = {
                                "data": data,
                                "mime_type": "image/jpeg" if data.startswith(b"\xff\xd8\xff") else "image/png",
                                "captured_at": time.time(),
                            }
                            await websocket.send_json({"type": "frame_received"})
                        else:
                            await websocket.send_json({"type": "frame_rejected", "message": "Invalid/oversized frame."})
                        continue
                    text = event.get("text")
                    if text:
                        try:
                            import json as _json
                            message = _json.loads(text)
                        except Exception:
                            message = {}
                        if message.get("type") == "analyze":
                            prompt = str(message.get("prompt") or "Describe the shared phone screen.")
                            ok = self._queue_phone_screen_analysis(prompt)
                            await websocket.send_json({"type": "analysis_queued" if ok else "analysis_unavailable"})
                            if ok and self._wake_callback:
                                self._wake_callback()
            except WebSocketDisconnect:
                pass
            except Exception as exc:
                print(f"[Dashboard] Phone screen socket ended: {type(exc).__name__}")
            finally:
                self._notify_access("screen", False)
                self._notify_access("phone", False)
                try:
                    await websocket.close()
                except Exception:
                    pass

        # ── Phone mic real-time audio → Gemini Live ──────────────────────────

        @app.websocket("/ws/phone-audio")
        async def phone_audio_ws(websocket: WebSocket, token: str = ""):
            tok = token.strip()
            if not tok or tok not in self._tokens:
                await websocket.close(code=4001)
                return
            await websocket.accept()
            self._notify_access("phone", True)
            asyncio.create_task(self.broadcast(
                {"type": "sys", "text": "Phone microphone live."}
            ))
            try:
                while True:
                    data = await websocket.receive_bytes()
                    try:
                        self._phone_audio_queue.put_nowait(
                            {"data": data, "mime_type": "audio/pcm"}
                        )
                    except asyncio.QueueFull:
                        pass  # drop frame rather than block
            except WebSocketDisconnect:
                pass
            finally:
                self._notify_access("phone", False)
                asyncio.create_task(self.broadcast(
                    {"type": "sys", "text": "Phone microphone stopped."}
                ))

        # ── File sharing ──────────────────────────────────────────────────────

        def _safe_filename(raw: str) -> str:
            name = Path(raw).name                          # strip path components
            name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name).strip(". ")
            return name or "upload"

        if _UPLOAD_OK:
            @app.post("/api/upload")
            async def upload_file(req: Request, file: UploadFile = FastAPIFile(...)):
                if not _auth(req):
                    return JSONResponse({"error": "Unauthorized"}, status_code=401)

                self._notify_access("files", True)
                safe = _safe_filename(file.filename or "upload")
                dest = self._uploads_dir / safe
                stem, suffix = Path(safe).stem, Path(safe).suffix
                counter = 1
                while dest.exists():
                    dest = self._uploads_dir / f"{stem}_{counter}{suffix}"
                    counter += 1

                size = 0
                max_bytes = MAX_UPLOAD_MB * 1024 * 1024
                try:
                    with open(dest, "wb") as fout:
                        while True:
                            chunk = await file.read(65536)
                            if not chunk:
                                break
                            size += len(chunk)
                            if size > max_bytes:
                                fout.close()
                                dest.unlink(missing_ok=True)
                                self._notify_access("files", False)
                                return JSONResponse(
                                    {"error": f"File too large (max {MAX_UPLOAD_MB} MB)"},
                                    status_code=413,
                                )
                            fout.write(chunk)
                except Exception as exc:
                    try:
                        dest.unlink(missing_ok=True)
                    except Exception:
                        pass
                    self._notify_access("files", False)
                    return JSONResponse({"error": str(exc)}, status_code=500)

                self._notify_access("files", False)
                asyncio.create_task(self.broadcast({
                    "type": "file_received",
                    "name": dest.name,
                    "size": size,
                    "saved_to": str(self._uploads_dir),
                }))
                return JSONResponse({"ok": True, "name": dest.name, "size": size})
        else:
            @app.post("/api/upload")
            async def upload_unavailable(req: Request):
                return JSONResponse(
                    {"error": "File uploads require: pip install python-multipart"},
                    status_code=503,
                )

        @app.get("/api/files")
        async def list_files(req: Request):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            files = []
            try:
                for f in sorted(
                    (p for p in self._uploads_dir.iterdir() if p.is_file()),
                    key=lambda p: p.stat().st_mtime,
                    reverse=True,
                ):
                    files.append({"name": f.name, "size": f.stat().st_size})
            except Exception:
                pass
            return JSONResponse({"files": files})

        @app.get("/uploads/{filename}")
        async def download_file(filename: str, token: str = ""):
            # Auth via query param — browser <a download> can't send custom headers
            tok = token.strip()
            if not tok or tok not in self._tokens:
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            safe = re.sub(r'[/\\]', '', filename)
            path = self._uploads_dir / safe
            if not path.exists() or not path.is_file():
                return JSONResponse({"error": "Not found"}, status_code=404)
            return FileResponse(str(path), filename=safe)

        @app.websocket("/ws")
        async def ws_ep(websocket: WebSocket, token: str = ""):
            tok = token.strip()
            if not tok or tok not in self._tokens:
                await websocket.close(code=4001)
                return
            await websocket.accept()
            self._clients.add(websocket)
            for entry in self._history[-50:]:
                try:
                    await websocket.send_json(entry)
                except Exception:
                    break
            try:
                while True:
                    data = await websocket.receive_json()
                    if data.get("type") == "command":
                        enc = data.get("enc", "")
                        t   = self._decrypt(tok, enc) if enc else (data.get("text") or "").strip()
                        if t:
                            await self._command_queue.put(t)
                            if self._wake_callback:
                                self._wake_callback()
            except WebSocketDisconnect:
                pass
            finally:
                self._clients.discard(websocket)

        return app

    # ── serve ─────────────────────────────────────────────────────────────

    async def _serve_alias(self) -> None:
        """Optional second HTTPS entry point sharing the same app and in-memory state.
        Chrome HTTPS-upgrades any bare IP:PORT the user types, so this port also needs TLS.
        Manual entry uses the selected alias port when HTTPS certificates are enabled."""
        ssl_key  = BASE_DIR / "config" / "certs" / "jarvis.key"
        ssl_cert = BASE_DIR / "config" / "certs" / "jarvis.crt"
        if not self.alias_port or self.alias_port == self.port:
            return
        asyncio.get_event_loop().run_in_executor(None, _ensure_network_access, self.alias_port)
        cfg = uvicorn.Config(
            self.app, host="0.0.0.0", port=self.alias_port, log_level="warning",
            ssl_keyfile=str(ssl_key), ssl_certfile=str(ssl_cert),
        )
        print(f"[Dashboard] Manual entry:  https://{self._ip}:{self.alias_port}  (review the local certificate warning if shown)")
        await uvicorn.Server(cfg).serve()

    async def serve(self) -> None:
        self._startup_error = "Starting the local phone dashboard…"
        self._notify_status(False)
        if not _DEPS_OK:
            message = "FastAPI or Uvicorn is not installed. Run setup.bat again."
            self._startup_error = message
            print(f"[Dashboard] {message}")
            self._notify_status(False)
            return
        if not self.port:
            self._startup_error = "No free local port is available for the phone dashboard."
            self._notify_status(False)
            return
        if self._ip in ("127.0.0.1", "0.0.0.0", ""):
            self._startup_error = "No LAN IPv4 address detected. Connect this PC to Wi-Fi or Ethernet."
            self._notify_status(False)
            return

        # Firewall setup runs in a thread — uvicorn starts immediately,
        # no waiting for UAC dialogs or subprocess timeouts.
        asyncio.get_event_loop().run_in_executor(None, _ensure_network_access, self.port)

        # Use the transport selected in __init__.  Re-checking the filesystem
        # here could otherwise disagree with a QR URL already handed to the UI.
        use_ssl  = self._use_ssl
        ssl_key  = BASE_DIR / "config" / "certs" / "jarvis.key"
        ssl_cert = BASE_DIR / "config" / "certs" / "jarvis.crt"

        if use_ssl and self.alias_port and self.alias_port != self.port:
            asyncio.create_task(self._serve_alias())

        cfg = uvicorn.Config(
            self.app, host="0.0.0.0", port=self.port, log_level="warning",
            **({"ssl_keyfile": str(ssl_key), "ssl_certfile": str(ssl_cert)} if use_ssl else {}),
        )

        proto = "https" if use_ssl else "http"
        print(f"[Dashboard] {proto}://{self._ip}:{self.port}")
        print("[Dashboard] Press 'Remote Control' in ORI UI to get the QR code.")
        server = uvicorn.Server(cfg)
        self._uvicorn_server = server
        server_task = asyncio.create_task(server.serve(), name="ori-dashboard-server")
        try:
            # Do not tell the UI the dashboard is available until Uvicorn has
            # successfully bound the socket. This also catches port conflicts.
            while not server.started and not server_task.done():
                await asyncio.sleep(0.05)

            if server.started:
                self._running = True
                self._startup_error = ''
                self._notify_status(True)
                await server_task
            else:
                error = ''
                if not server_task.cancelled():
                    try:
                        error = str(server_task.exception() or '')
                    except Exception:
                        error = ''
                self._startup_error = error or f"Could not bind {self._ip}:{self.port}"
                print(f"[Dashboard] Startup failed: {self._startup_error}")
                self._notify_status(False)
        except Exception as exc:
            self._startup_error = f"{type(exc).__name__}: {exc}"
            print(f"[Dashboard] Startup/runtime failure: {self._startup_error}")
            self._notify_status(False)
        finally:
            self._running = False
            self._uvicorn_server = None
            self._notify_status(False)
