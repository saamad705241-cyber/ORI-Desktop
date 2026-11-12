from __future__ import annotations

import json
import math
import os
import platform
import random
import subprocess
import sys
import threading
import time
from pathlib import Path

import psutil

if platform.system() == "Windows":
    _WIN_HIDE: dict = {"creationflags": subprocess.CREATE_NO_WINDOW}
else:
    _WIN_HIDE: dict = {}

# Qt's video backend prints the ffmpeg stream banner — codec, bitrate, the
# whole signed googlevideo URL — to the console for every stream it opens. That
# is two screenfuls per video, it looks like an error to anyone reading the log,
# and it puts a URL carrying the viewer's IP address into a terminal people
# paste into bug reports. Silenced here, before Qt initialises its logging.
# An explicit setting from the user is left alone.
os.environ.setdefault("QT_LOGGING_RULES", "qt.multimedia.*=false")

from PyQt6.QtCore import (
    QEasingCurve, QLineF, QMimeData, QObject, QParallelAnimationGroup, QPointF,
    QPoint, QPropertyAnimation, QRect, QRectF, QSize, QSizeF, Qt, QTimer,
    QUrl, pyqtSignal,
)
from PyQt6.QtGui import (
    QBrush, QColor, QConicalGradient, QDragEnterEvent, QDropEvent, QFont,
    QFontDatabase, QKeySequence, QLinearGradient, QPainter, QPainterPath,
    QPen, QPixmap, QRadialGradient, QShortcut, QIcon, QDesktopServices,
)
# Video playback for the HUD. Part of PyQt6, so it costs no new dependency —
# but the multimedia plugins are a separate piece of the Qt install and can be
# absent on a stripped-down system, so a failure here disables one feature
# rather than stopping ORI from starting.
try:
    from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
    from PyQt6.QtMultimediaWidgets import QGraphicsVideoItem
    HAVE_VIDEO = True
except Exception as _e:            # noqa: BLE001 - reported, never fatal
    QAudioOutput = QMediaPlayer = QGraphicsVideoItem = None
    HAVE_VIDEO = False
    print(f"[Video] playback unavailable ({_e}) — the HUD will not show video.")

from PyQt6.QtWidgets import (
    QApplication, QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QMainWindow, QPushButton, QScrollArea, QSizePolicy, QSplitter,
    QGraphicsScene, QGraphicsView,
    QStackedWidget, QTextEdit, QVBoxLayout, QWidget, QProgressBar, QCheckBox,
    QMessageBox,
)


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent

BASE_DIR   = _base_dir()
CONFIG_DIR = BASE_DIR / "config"
API_FILE   = CONFIG_DIR / "api_keys.json"


def _read_full_config() -> dict:
    """Read api_keys.json config dict. Returns {} on any error."""
    try:
        return json.loads(API_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


# Single source of truth for the release name — the window title, the header
# badge and the readme must never disagree again.
from ori_metadata import APP_VERSION
APP_PROTOCOL = APP_VERSION.split()[-1]

_DEFAULT_W, _DEFAULT_H = 1360, 820
_MIN_W,     _MIN_H     = 1000, 640
_LEFT_W  = 214
_RIGHT_W = 316

_OS = platform.system()  # "Windows" | "Darwin" | "Linux"


from ui_theme import C, UI_FONT, qcol          # palette + font live there now
from ui_glass import (Backdrop, GlassPanel, NavButton, TextStat, HomeCard)


# Keys tied to the accent colour — status colours (ACC, GREEN, RED…) stay fixed
_HUE_LINKED = (
    "BG", "PANEL", "PANEL2", "BORDER", "BORDER_B", "BORDER_A",
    "PRI", "PRI_DIM", "PRI_GHO", "TEXT", "TEXT_DIM", "TEXT_MED",
    "WHITE", "DARK", "BAR_BG",
)
_PALETTE_DEFAULTS: dict[str, str] = {k: getattr(C, k) for k in _HUE_LINKED}

DEFAULT_UI_COLOR = _PALETTE_DEFAULTS["PRI"]


def apply_ui_accent(accent_hex: str) -> bool:
    """
    Re-derives the whole teal-family palette from the chosen accent colour
    (hue shift — brightness/saturation ratios are preserved, design stays intact).
    Painted elements (HUD, waveform, metrics) pick up the new colour on the next
    frame; stylesheet-based panels pick it up when they are rebuilt.
    """
    import colorsys

    accent_hex = (accent_hex or "").strip().lower()
    if not (accent_hex.startswith("#") and len(accent_hex) == 7):
        return False
    try:
        int(accent_hex[1:], 16)
    except ValueError:
        return False

    def _hsv(h: str) -> tuple[float, float, float]:
        r = int(h[1:3], 16) / 255
        g = int(h[3:5], 16) / 255
        b = int(h[5:7], 16) / 255
        return colorsys.rgb_to_hsv(r, g, b)

    base_h            = _hsv(_PALETTE_DEFAULTS["PRI"])[0]
    acc_h, acc_s, _av = _hsv(accent_hex)
    dh   = acc_h - base_h
    grey = acc_s < 0.08   # near-grey accent → the whole theme is desaturated

    for key, hex0 in _PALETTE_DEFAULTS.items():
        h, s, v = _hsv(hex0)
        if grey:
            s *= 0.15
        r, g, b = colorsys.hsv_to_rgb((h + dh) % 1.0, s, v)
        setattr(C, key, "#{:02x}{:02x}{:02x}".format(
            int(r * 255 + 0.5), int(g * 255 + 0.5), int(b * 255 + 0.5)))
    return True


def current_palette() -> dict[str, str]:
    """A snapshot of the accent-linked colours currently on class C."""
    return {k: getattr(C, k) for k in _HUE_LINKED}


def retheme_all_widgets(old: dict[str, str], new: dict[str, str]) -> None:
    """
    LIVE full theme change. Replaces the old palette colours with the new ones
    in EVERY widget's stylesheet across the app and repaints them. This way the
    colour change applies INSTANTLY across the whole interface — panels, buttons,
    borders included — not just the painted elements. No restart needed.
    """
    mapping = {old[k].lower(): new[k].lower()
               for k in old if old[k].lower() != new.get(k, old[k]).lower()}
    if not mapping:
        return
    app = QApplication.instance()
    if app is None:
        return
    for w in app.allWidgets():
        try:
            ss = w.styleSheet()
            if ss:
                s2 = ss
                for o, n in mapping.items():
                    if o in s2:
                        s2 = s2.replace(o, n)
                if s2 != ss:
                    w.setStyleSheet(s2)
            w.update()
        except Exception:
            pass




# ── Windows GPU via NVML DLL (no subprocess, no console window) ──────────────
_nvml_lib: object = None   # cached ctypes DLL
_nvml_ok:  object = None   # None=untested, True=works, False=unavailable


def _nvml_gpu_windows() -> float:
    """Return NVIDIA GPU utilisation % using nvml.dll directly — zero subprocess."""
    global _nvml_lib, _nvml_ok
    if _nvml_ok is False:
        return -1.0
    try:
        import ctypes

        class _Util(ctypes.Structure):
            _fields_ = [("gpu", ctypes.c_uint), ("memory", ctypes.c_uint)]

        if _nvml_lib is None:
            for dll_name in ("nvml", r"C:\Windows\System32\nvml.dll"):
                try:
                    lib = ctypes.WinDLL(dll_name)
                    lib.nvmlInit_v2()
                    _nvml_lib = lib
                    break
                except Exception:
                    continue

        if _nvml_lib is None:
            import pynvml  # type: ignore
            pynvml.nvmlInit()
            h = pynvml.nvmlDeviceGetHandleByIndex(0)
            _nvml_ok = True
            return float(pynvml.nvmlDeviceGetUtilizationRates(h).gpu)

        dev = ctypes.c_void_p()
        _nvml_lib.nvmlDeviceGetHandleByIndex_v2(0, ctypes.byref(dev))
        util = _Util()
        _nvml_lib.nvmlDeviceGetUtilizationRates(dev, ctypes.byref(util))
        _nvml_ok = True
        return float(util.gpu)
    except Exception:
        _nvml_ok = False
        return -1.0


class _SysMetrics:
    def __init__(self):
        self.cpu  = 0.0
        self.mem  = 0.0
        self.net  = 0.0   
        self.gpu  = -1.0  
        self.tmp  = -1.0  
        self._lock = threading.Lock()
        self._last_net = psutil.net_io_counters()
        self._last_net_t = time.time()
        self._running = True
        # Probe caches — GPU (NVML) and temperature (WMI) are the expensive
        # queries; initialise their handles once and reuse them instead of
        # rebuilding a connection on every poll.
        self._slow_tick = 0            # gpu/temp refreshed every 3rd cycle
        self._pynvml    = None         # cached pynvml module + device handle
        self._pynvml_h  = None
        self._pynvml_ok = None         # None=untested, False=unavailable here
        self._nv_unix   = None         # cached (lib, dev) for Linux/macOS NVML
        self._wmi_conn  = None         # cached ACPI WMI connection
        self._wmi_ok    = None         # None=untested, False=unavailable here
        self._lhwmi_conn = None       # LibreHardwareMonitor WMI, if user runs it
        self._lhwmi_ok = None
        self._lhwmi_last_probe = 0.0
        t = threading.Thread(target=self._loop, daemon=True)
        t.start()

    def _loop(self):
        while self._running:
            try:
                self._update()
            except Exception:
                pass
            time.sleep(2.0)

    def _update(self):
        cpu = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory().percent

        nc  = psutil.net_io_counters()
        now = time.time()
        dt  = now - self._last_net_t
        if dt > 0:
            sent = (nc.bytes_sent - self._last_net.bytes_sent) / dt
            recv = (nc.bytes_recv - self._last_net.bytes_recv) / dt
            net  = (sent + recv) / (1024 * 1024)
        else:
            net = 0.0
        self._last_net   = nc
        self._last_net_t = now

        # GPU and temperature change slowly and are the most expensive probes
        # (NVML / WMI) — refresh them every 3rd cycle (~6 s) instead of every
        # cycle, reusing the previous reading in between.
        self._slow_tick = (self._slow_tick + 1) % 3
        if self._slow_tick == 1:
            gpu = self._get_gpu()
            tmp = self._get_temp()
        else:
            gpu = self.gpu
            tmp = self.tmp

        with self._lock:
            self.cpu = cpu
            self.mem = mem
            self.net = net
            self.gpu = gpu
            self.tmp = tmp

    def _get_gpu(self) -> float:
        # pynvml — subprocess-free; initialise once and reuse the handle.
        # Re-initialising NVML on every poll is slow, so cache it and stop
        # retrying pynvml entirely once it proves unavailable here.
        if self._pynvml_ok is not False:
            try:
                if self._pynvml_h is None:
                    import pynvml  # type: ignore
                    pynvml.nvmlInit()
                    self._pynvml    = pynvml
                    self._pynvml_h  = pynvml.nvmlDeviceGetHandleByIndex(0)
                    self._pynvml_ok = True
                return float(self._pynvml.nvmlDeviceGetUtilizationRates(self._pynvml_h).gpu)
            except Exception:
                self._pynvml_ok = False

        # Windows: nvml.dll via ctypes (already cached in _nvml_gpu_windows)
        if _OS == "Windows":
            return _nvml_gpu_windows()

        # Linux / macOS: libnvidia-ml shared lib via ctypes — init once, reuse
        try:
            import ctypes

            class _Util(ctypes.Structure):
                _fields_ = [("gpu", ctypes.c_uint), ("memory", ctypes.c_uint)]

            if self._nv_unix is None:
                _lib = "libnvidia-ml.so.1" if _OS == "Linux" else "libnvidia-ml.dylib"
                nv = ctypes.CDLL(_lib)
                nv.nvmlInit_v2()
                dev = ctypes.c_void_p()
                nv.nvmlDeviceGetHandleByIndex_v2(0, ctypes.byref(dev))
                self._nv_unix = (nv, dev)

            nv, dev = self._nv_unix
            u = _Util()
            nv.nvmlDeviceGetUtilizationRates(dev, ctypes.byref(u))
            return float(u.gpu)
        except Exception:
            pass

        return -1.0   # N/A — zero subprocess on all platforms

    def _get_temp(self) -> float:
        # Share the same sensor resolver used by hardware_inventory.
        try:
            from core.hardware_sensors import get_cpu_temperature
            reading = get_cpu_temperature()
            if reading and reading.get("temperature_c") is not None:
                self._cpu_temp_provider = str(reading.get("provider") or "hardware sensor")
                return float(reading["temperature_c"])
        except Exception:
            pass
        self._cpu_temp_provider = None
        return -1.0

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "cpu": self.cpu,
                "mem": self.mem,
                "net": self.net,
                "gpu": self.gpu,
                "tmp": self.tmp,
            }


_metrics = _SysMetrics()

class HudCanvas(QWidget):
    def __init__(self, assistant_name: str = "ORI", parent=None):
        super().__init__(parent)
        # Painted over the window backdrop: no opaque fill, so the scene shows through.
        self.setMinimumSize(300, 300)
        self.card_w = 0          # width the home card occupies at the left (0 = hidden)
        self.on_resize = None
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.muted    = False
        self.speaking = False
        self.state    = "INITIALISING"
        self._assistant_name = assistant_name

        # The HUD is only a frequency waveform. No face/avatar objects or assets.
        self.hud_style = "waveform"
        self._core_phase = 0.0
        self._step_t = time.monotonic()
        self._paint_tick = 0
        self._live_amp = 0.0
        self._amp_disp = 0.0
        self._spectrum_live = [0.0] * 64
        self._spectrum_disp = [0.0] * 64
        self._spectrum_source = "input"

        self._tmr = QTimer(self)
        self._tmr.timeout.connect(self._step)
        self._tmr.start(16)

    def glance(self, dx: float, dy: float, hold: float = 1.1) -> None:
        """Compatibility no-op; the waveform has no character to move."""
        return

    def set_audio_level(self, level: float) -> None:
        """Store the measured audio envelope; painting stays on the GUI thread."""
        try:
            value = max(0.0, min(1.0, float(level)))
        except (TypeError, ValueError):
            value = 0.0
        self._live_amp = 0.0 if value < 0.006 else value

    def set_audio_spectrum(self, bands, source: str = "input") -> None:
        """Accept normalized FFT bands computed from actual PCM, not synthetic animation."""
        try:
            values = [max(0.0, min(1.0, float(v))) for v in bands]
        except (TypeError, ValueError):
            values = []
        if not values:
            values = [0.0] * 64
        if len(values) < 64:
            values.extend([0.0] * (64 - len(values)))
        self._spectrum_live = values[:64]
        self._spectrum_source = "output" if str(source).lower() == "output" else "input"
        peak = max(self._spectrum_live, default=0.0)
        self._live_amp = max(self._live_amp, peak)

    def _step(self):
        now = time.monotonic()
        dt = max(0.0, min(0.10, now - self._step_t))
        self._step_t = now
        # Release is slower than attack: audio bars fall smoothly instead of snapping.
        self._live_amp *= 0.91
        self._amp_disp += (self._live_amp - self._amp_disp) * 0.30
        for i, value in enumerate(self._spectrum_live):
            self._spectrum_live[i] = value * 0.89
            self._spectrum_disp[i] += (self._spectrum_live[i] - self._spectrum_disp[i]) * 0.32
        self._core_phase = (self._core_phase + dt) % 10000.0
        self._paint_tick = (self._paint_tick + 1) % 4
        active = (self._amp_disp > 0.012 or max(self._spectrum_disp, default=0.0) > 0.012)
        if active or self._paint_tick == 0:
            if self._on_screen():
                self.update()

    def _on_screen(self) -> bool:
        """True only when this canvas can actually be seen by the user."""
        try:
            if not self.isVisible():
                return False
            win = self.window()
            return not (win.isMinimized() or win.isHidden())
        except Exception:
            return True      # never let a visibility check stop the HUD drawing

    def resizeEvent(self, e):
        super().resizeEvent(e)
        cb = self.on_resize
        if cb:
            cb()

    def paintEvent(self, _):
        """Cinematic terminal waveform, driven by live mic/output audio level.

        No face, orb, avatar mesh, radial reactor or logo is rendered here. The
        exact same waveform remains visible while listening, thinking and speaking.
        """
        p = QPainter(self)
        if not p.isActive():
            return
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        W, H = self.width(), self.height()
        if W < 8 or H < 8:
            p.end()
            return

        mid_y = H * 0.50
        span = min(W * 0.78, 1060.0)
        left = (W - span) * 0.5
        right = left + span
        amp = max(0.0, min(1.0, float(self._amp_disp)))
        spectrum_peak = max(self._spectrum_disp, default=0.0)
        state = str(self.state).upper()
        if self.muted:
            main = qcol(C.MUTED_C, 215)
            accent = qcol(C.MUTED_C, 110)
        elif state in ("THINKING", "PROCESSING", "SEARCHING", "READING FILE", "ANALYZING SCREEN", "EXECUTING"):
            main = qcol(C.ACC, 225)
            accent = qcol(C.PRI, 95)
        elif self.speaking or self._spectrum_source == "output":
            main = qcol(C.PRI, 245)
            accent = qcol(C.ACC, 170)
        else:
            main = qcol(C.PRI, 220)
            accent = qcol(C.PRI, 85)

        # Real audio drives the spectrum. At silence, keep a restrained living
        # signal: a sub-pixel breathing trace, not fabricated audio bars.
        datum = C.MUTED_C if self.muted else C.PRI
        quiet = max(amp, spectrum_peak) <= 0.012
        p.setPen(QPen(qcol(datum, 85 if quiet else 42), 1))
        p.drawLine(int(left), int(mid_y), int(right), int(mid_y))
        if quiet:
            if not self.muted and state in ("READY", "LISTENING", "IDLE", "INITIALISING"):
                # Ambient motion is an intentional idle-state signature, not fake
                # audio. Live mic/speaker PCM immediately takes over the 64-band view.
                breath = 2.2 + 1.4 * (0.5 + 0.5 * math.sin(self._core_phase * 0.34))
                for layer, alpha, factor, offset in ((0, 28, 1.0, 0.0), (1, 54, 0.62, 1.4)):
                    path = QPainterPath()
                    points = 128
                    for i in range(points):
                        u = i / max(1, points - 1)
                        x = left + u * span
                        edge = abs(2.0 * u - 1.0)
                        envelope = 0.20 + 0.80 * math.exp(-((edge * 1.55) ** 2))
                        carrier = math.sin(u * math.pi * 6.0 - self._core_phase * 0.38 + offset)
                        slow = 0.72 + 0.28 * math.sin(u * math.pi * 2.0 + self._core_phase * 0.16)
                        y = mid_y + carrier * breath * factor * envelope * slow
                        if i == 0:
                            path.moveTo(x, y)
                        else:
                            path.lineTo(x, y)
                    if layer == 0:
                        p.setPen(QPen(qcol(C.PRI, alpha), 3.4))
                        p.drawPath(path)
                    p.setPen(QPen(qcol(C.PRI, alpha + 18), 1.0))
                    p.drawPath(path)
                # A slow central pulse gives the idle screen a quiet heartbeat.
                pulse = 2.0 + 1.6 * (0.5 + 0.5 * math.sin(self._core_phase * 0.8))
                p.setPen(QPen(qcol(C.PRI, 78), 1.0))
                p.drawLine(QPointF(W * 0.5, mid_y - pulse), QPointF(W * 0.5, mid_y + pulse))
            p.end()
            return

        p.setPen(QPen(qcol(C.MUTED_C if self.muted else C.PRI, 95), 1))
        tick = 13
        p.drawLine(int(left), int(mid_y - tick), int(left), int(mid_y + tick))
        p.drawLine(int(right), int(mid_y - tick), int(right), int(mid_y + tick))

        # Each bar maps to a log-spaced band from actual PCM FFT data. Bass,
        # mids and treble can move independently; the phase is never fabricated.
        count = max(81, min(181, int(span / 6)))
        band_count = len(self._spectrum_disp) or 64
        for i in range(count):
            u = i / max(1, count - 1)
            x = left + u * span
            edge = abs((u * 2.0) - 1.0)
            envelope = 0.24 + 0.76 * math.exp(-((edge * 2.15) ** 2))
            band_idx = min(band_count - 1, int(u * (band_count - 1)))
            v0 = self._spectrum_disp[band_idx]
            v1 = self._spectrum_disp[min(band_count - 1, band_idx + 1)]
            energy = max(0.0, min(1.0, (v0 * 0.72 + v1 * 0.28)))
            height = 1.0 + energy * (H * 0.34) * envelope
            if i % 19 == 0:
                p.setPen(QPen(accent, 1.25))
            else:
                p.setPen(QPen(main, 1.25 if energy > 0.08 else 1.0))
            p.drawLine(int(x), int(mid_y - height), int(x), int(mid_y + height))
        p.end()


class MetricBar(QWidget):

    def __init__(self, label: str, color: str = C.PRI, parent=None):
        super().__init__(parent)
        self._label = label
        self._color = color
        self._value = 0.0       # 0–100
        self._text  = "--"
        self.setFixedHeight(38)
        self.setMinimumWidth(80)

    def set_value(self, pct: float, text: str):
        v = max(0.0, min(100.0, pct))
        if v == self._value and text == self._text:
            return          # unchanged — skip the repaint
        self._value = v
        self._text  = text
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        if not p.isActive():
            return
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()

        p.setBrush(QBrush(qcol(C.PANEL2)))
        p.setPen(QPen(qcol(C.BORDER_A), 1))
        p.drawRoundedRect(QRectF(1, 1, W - 2, H - 2), 4, 4)

        bar_h   = 4
        bar_y   = H - bar_h - 5
        bar_w   = W - 12
        bar_x   = 6
        fill_w  = int(bar_w * self._value / 100)

        p.setBrush(QBrush(qcol(C.BAR_BG)))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(QRectF(bar_x, bar_y, bar_w, bar_h), 2, 2)

        if self._value > 85:
            bar_col = qcol(C.RED)
        elif self._value > 65:
            bar_col = qcol(C.ACC)
        else:
            bar_col = qcol(self._color)

        if fill_w > 0:
            p.setBrush(QBrush(bar_col))
            p.drawRoundedRect(QRectF(bar_x, bar_y, fill_w, bar_h), 2, 2)

        p.setFont(QFont(UI_FONT, 7, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.TEXT_DIM), 1))
        p.drawText(QRectF(8, 5, 50, 14), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self._label)

        p.setFont(QFont(UI_FONT, 9, QFont.Weight.Bold))
        p.setPen(QPen(bar_col if self._text != "--" else qcol(C.TEXT_DIM), 1))
        p.drawText(QRectF(0, 4, W - 6, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, self._text)

        p.end()

class MetricChip(QWidget):
    """Small top-bar metric with optional live sparkline history."""

    def __init__(self, label: str, color: str = C.PRI, width: int = 72, parent=None):
        super().__init__(parent)
        self._label = str(label).upper()
        self._color = color
        self._value_text = "N/A"
        self._value: float | None = None
        self._history: list[float] = []
        self._mode = "both"
        self._max_value = 100.0
        self._warning = False
        self.setFixedSize(width, 30)
        self.setToolTip(f"{self._label} usage")

    def set_metric(
        self,
        value: float | None,
        value_text: str,
        mode: str = "both",
        tooltip: str = "",
        max_value: float = 100.0,
        warning: bool = False,
    ) -> None:
        mode = mode if mode in ("percentages", "graphs", "both") else "both"
        try:
            val = float(value) if value is not None else None
        except (TypeError, ValueError):
            val = None
        if val is not None and val >= 0:
            self._value = val
            self._history.append(val)
            self._history = self._history[-32:]
        else:
            self._value = None
            self._history.clear()
        self._value_text = str(value_text or "N/A")
        self._mode = mode
        self._max_value = max(1.0, float(max_value or 100.0))
        self._warning = bool(warning)
        if tooltip:
            self.setToolTip(tooltip)
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        if not p.isActive():
            return
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setBrush(QBrush(qcol(C.PANEL2, 220)))
        p.setPen(QPen(qcol(C.BORDER_A), 1))
        p.drawRoundedRect(r, 2, 2)

        color = C.RED if self._warning else self._color
        p.setFont(QFont(UI_FONT, 7, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.TEXT_DIM), 1))
        p.drawText(QRectF(5, 2, self.width() * 0.42, 13),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   self._label)
        if self._mode != "graphs":
            p.setFont(QFont(UI_FONT, 8, QFont.Weight.Bold))
            p.setPen(QPen(qcol(color if self._value is not None else C.TEXT_DIM), 1))
            p.drawText(QRectF(self.width() * 0.35, 2, self.width() * 0.60 - 4, 13),
                       Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       self._value_text)

        if self._mode in ("graphs", "both") and len(self._history) >= 2:
            left, right = 5.0, self.width() - 5.0
            top = 17.0 if self._mode == "both" else 15.0
            bottom = self.height() - 4.0
            h = max(2.0, bottom - top)
            points = self._history[-24:]
            path = QPainterPath()
            for i, sample in enumerate(points):
                x = left + (right - left) * i / max(1, len(points) - 1)
                normalized = max(0.0, min(1.0, sample / self._max_value))
                y = bottom - normalized * h
                if i == 0:
                    path.moveTo(x, y)
                else:
                    path.lineTo(x, y)
            p.setPen(QPen(qcol(color, 205), 1.35))
            p.drawPath(path)
        elif self._mode in ("graphs", "both"):
            p.setPen(QPen(qcol(C.BORDER_B), 1))
            p.drawLine(5, self.height() - 5, self.width() - 5, self.height() - 5)
        p.end()


class LogWidget(QTextEdit):
    _sig = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        # Cap scrollback so an hours-long session can't grow the document
        # without bound — keeps memory flat and every insert cheap. Oldest
        # lines drop off the top automatically.
        self.document().setMaximumBlockCount(600)
        self.setFont(QFont(UI_FONT, 9))
        self.setStyleSheet(f"""
            QTextEdit {{
                background: transparent;
                color: {C.TEXT};
                border: 1px solid {C.BORDER};
                border-radius: 10px;
                padding: 8px;
                selection-background-color: {C.PRI_GHO};
            }}
            QScrollBar:vertical {{
                background: {C.BG};
                width: 8px;
                border: none;
            }}
            QScrollBar::handle:vertical {{
                background: {C.BORDER_B};
                border-radius: 4px;
                min-height: 20px;
            }}
        """)
        self._queue: list[str] = []
        self._typing  = False
        self._text    = ""
        self._pos     = 0
        self._tag     = "sys"
        self._ai_name_lc = "ori"   # updated when assistant name changes
        self._tmr = QTimer(self)
        self._tmr.timeout.connect(self._step)
        self._sig.connect(self._enqueue)

    def append_log(self, text: str):
        self._sig.emit(text)

    def _enqueue(self, text: str):
        self._queue.append(text)
        if not self._typing:
            self._next()

    def _next(self):
        if not self._queue:
            self._typing = False
            return
        self._typing = True
        self._text   = self._queue.pop(0)
        self._pos    = 0
        tl = self._text.lower()
        _ai_pfx = f"{self._ai_name_lc}:"
        if   tl.startswith("you:"):                              self._tag = "you"
        elif tl.startswith(_ai_pfx) or tl.startswith("ori:") or tl.startswith("jarvis:"): self._tag = "ai"
        elif tl.startswith("file:"):                             self._tag = "file"
        elif "err" in tl:                                        self._tag = "err"
        else:                                                    self._tag = "sys"
        self._tmr.start(6)

    def _step(self):
        if self._pos < len(self._text):
            ch  = self._text[self._pos]
            cur = self.textCursor()
            fmt = cur.charFormat()
            col = {
                "you":  qcol(C.WHITE),
                "ai":   qcol(C.PRI),
                "err":  qcol(C.RED),
                "file": qcol(C.GREEN),
                # SYS lines are the bulk of the log. Amber fought the cyan HUD
                # and, being a fixed status colour rather than a hue-linked one,
                # stayed amber even after the accent picker retinted everything
                # else. TEXT_MED follows the theme and drops the contrast to a
                # level you can read past.
                "sys":  qcol(C.TEXT_MED),
            }.get(self._tag, qcol(C.TEXT))
            fmt.setForeground(QBrush(col))
            cur.movePosition(cur.MoveOperation.End)
            cur.insertText(ch, fmt)
            self.setTextCursor(cur)
            self.ensureCursorVisible()
            self._pos += 1
        else:
            self._tmr.stop()
            cur = self.textCursor()
            cur.movePosition(cur.MoveOperation.End)
            cur.insertText("\n")
            self.setTextCursor(cur)
            self.ensureCursorVisible()
            QTimer.singleShot(20, self._next)

_FILE_ICONS = {
    "image":   ("🖼", "#00d4ff"), "video":   ("🎬", "#ff6b00"),
    "audio":   ("🎵", "#cc44ff"), "pdf":     ("📄", "#ff4444"),
    "word":    ("📝", "#4488ff"), "excel":   ("📊", "#44bb44"),
    "code":    ("💻", "#ffcc00"), "archive": ("📦", "#ff8844"),
    "pptx":    ("📊", "#ff6622"), "text":    ("📃", "#aaaaaa"),
    "data":    ("🔧", "#88ddff"), "unknown": ("📎", "#888888"),
}
_EXT_TO_CAT = {
    **dict.fromkeys(["jpg","jpeg","png","gif","webp","bmp","tiff","svg","ico"], "image"),
    **dict.fromkeys(["mp4","avi","mov","mkv","wmv","flv","webm","m4v"],         "video"),
    **dict.fromkeys(["mp3","wav","ogg","m4a","aac","flac","wma","opus"],        "audio"),
    **dict.fromkeys(["pdf"],                                                     "pdf"),
    **dict.fromkeys(["doc","docx"],                                              "word"),
    **dict.fromkeys(["xls","xlsx","ods"],                                        "excel"),
    **dict.fromkeys(["ppt","pptx"],                                              "pptx"),
    **dict.fromkeys(["py","js","ts","jsx","tsx","html","css","java","c","cpp",
                     "cs","go","rs","rb","php","swift","kt","sh","sql","lua"],   "code"),
    **dict.fromkeys(["zip","rar","tar","gz","7z","bz2","xz"],                   "archive"),
    **dict.fromkeys(["txt","md","rst","log"],                                    "text"),
    **dict.fromkeys(["csv","tsv","json","xml"],                                  "data"),
}

def _file_category(path: Path) -> str:
    return _EXT_TO_CAT.get(path.suffix.lower().lstrip("."), "unknown")

def _fmt_size(size: int) -> str:
    if   size < 1024:    return f"{size} B"
    elif size < 1024**2: return f"{size/1024:.1f} KB"
    elif size < 1024**3: return f"{size/1024**2:.1f} MB"
    else:                return f"{size/1024**3:.1f} GB"


class FileDropZone(QWidget):
    file_selected = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(100)
        self._current_file: str | None = None
        self._hovering  = False
        self._drag_over = False
        self._dash_offset = 0.0
        self._anim_tmr = QTimer(self)
        self._anim_tmr.timeout.connect(self._animate)
        self._anim_tmr.start(40)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._canvas = _DropCanvas(self)
        layout.addWidget(self._canvas)

    def _animate(self):
        # The marching-ants dashed border is only meaningful while the user is
        # hovering or dragging a file over the zone. When idle, skip the repaint
        # entirely instead of redrawing the whole zone 25×/s forever — that idle
        # repaint held the GIL and stole time from the audio/response threads.
        if not (self._hovering or self._drag_over):
            return
        self._dash_offset = (self._dash_offset + 0.8) % 20
        self._canvas.update()

    def dragEnterEvent(self, e: QDragEnterEvent):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self._drag_over = True; self._canvas.update()

    def dragLeaveEvent(self, e):
        self._drag_over = False; self._canvas.update()

    def dropEvent(self, e: QDropEvent):
        self._drag_over = False
        urls = e.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            if Path(path).is_file():
                self._set_file(path)
        self._canvas.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._browse()

    def enterEvent(self, e):
        self._hovering = True; self._canvas.update()

    def leaveEvent(self, e):
        self._hovering = False; self._canvas.update()

    def current_file(self) -> str | None:
        return self._current_file

    def clear_file(self):
        self._current_file = None; self._canvas.update()

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select a file for ORI", str(Path.home()),
            "All Files (*.*);;"
            "Images (*.jpg *.jpeg *.png *.gif *.webp *.bmp *.svg);;"
            "Documents (*.pdf *.docx *.txt *.md *.pptx);;"
            "Data (*.csv *.xlsx *.json *.xml);;"
            "Code (*.py *.js *.ts *.html *.css *.java *.cpp *.go);;"
            "Audio (*.mp3 *.wav *.ogg *.m4a *.aac *.flac);;"
            "Video (*.mp4 *.avi *.mov *.mkv *.wmv *.webm);;"
            "Archives (*.zip *.rar *.tar *.gz *.7z)",
        )
        if path:
            self._set_file(path)

    def _set_file(self, path: str):
        self._current_file = path
        self._canvas.update()
        self.file_selected.emit(path)


class _DropCanvas(QWidget):
    def __init__(self, zone: FileDropZone):
        super().__init__(zone)
        self._z = zone

    def paintEvent(self, _):
        p = QPainter(self)
        if not p.isActive():
            return
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        z    = self._z
        W, H = self.width(), self.height()
        pad  = 6
        rect = QRectF(pad, pad, W - pad * 2, H - pad * 2)

        bg_col = qcol("#001a24" if z._drag_over else ("#001218" if z._hovering else C.PANEL))
        p.setBrush(QBrush(bg_col)); p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(rect, 6, 6)

        if z._current_file:   border_col = qcol(C.GREEN, 200)
        elif z._drag_over:    border_col = qcol(C.PRI, 230)
        elif z._hovering:     border_col = qcol(C.BORDER_B, 200)
        else:                 border_col = qcol(C.BORDER, 160)

        pen = QPen(border_col, 1.5, Qt.PenStyle.DashLine)
        pen.setDashOffset(z._dash_offset)
        p.setPen(pen); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(rect, 6, 6)

        if z._current_file:   self._paint_file(p, W, H)
        elif z._drag_over:    self._paint_drag_over(p, W, H)
        else:                 self._paint_idle(p, W, H, z._hovering)

        p.end()

    def _paint_idle(self, p, W, H, hover):
        cx, cy = W / 2, H / 2
        col = qcol(C.PRI_DIM if not hover else C.PRI)
        p.setPen(QPen(col, 2)); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawLine(QPointF(cx, cy - 14), QPointF(cx, cy + 4))
        p.drawLine(QPointF(cx - 8, cy - 6), QPointF(cx, cy - 14))
        p.drawLine(QPointF(cx + 8, cy - 6), QPointF(cx, cy - 14))
        p.drawLine(QPointF(cx - 14, cy + 4), QPointF(cx + 14, cy + 4))
        p.setFont(QFont(UI_FONT, 8))
        p.setPen(QPen(qcol(C.PRI_DIM if not hover else C.TEXT), 1))
        p.drawText(QRectF(0, cy + 8, W, 16), Qt.AlignmentFlag.AlignCenter,
                   "Drop file here  or  Click to Browse")
        p.setFont(QFont(UI_FONT, 7))
        p.setPen(QPen(qcol("#1a4a5a"), 1))
        p.drawText(QRectF(0, cy + 24, W, 14), Qt.AlignmentFlag.AlignCenter,
                   "Images · Video · Audio · PDF · Docs · Code · Data")

    def _paint_drag_over(self, p, W, H):
        cx, cy = W / 2, H / 2
        p.setFont(QFont(UI_FONT, 20))
        p.setPen(QPen(qcol(C.PRI), 1))
        p.drawText(QRectF(0, cy - 24, W, 32), Qt.AlignmentFlag.AlignCenter, "⬇")
        p.setFont(QFont(UI_FONT, 8, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.PRI), 1))
        p.drawText(QRectF(0, cy + 12, W, 16), Qt.AlignmentFlag.AlignCenter, "Release to load")

    def _paint_file(self, p, W, H):
        path = Path(self._z._current_file)
        cat  = _file_category(path)
        icon, icon_col = _FILE_ICONS.get(cat, _FILE_ICONS["unknown"])
        size_str = _fmt_size(path.stat().st_size)
        ext_str  = path.suffix.upper().lstrip(".") or "FILE"

        block_x, block_w = 10, 60
        p.setFont(QFont("Segoe UI Emoji", 22) if _OS == "Windows" else QFont("Arial", 22))
        p.setPen(QPen(qcol(icon_col), 1))
        p.drawText(QRectF(block_x, 0, block_w, H), Qt.AlignmentFlag.AlignCenter, icon)

        tx = block_x + block_w + 6
        tw = W - tx - 38

        p.setFont(QFont(UI_FONT, 8, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.WHITE), 1))
        name = path.name if len(path.name) <= 34 else path.name[:31] + "..."
        p.drawText(QRectF(tx, H * 0.18, tw, 16),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, name)

        p.setFont(QFont(UI_FONT, 7))
        p.setPen(QPen(qcol(C.TEXT_DIM), 1))
        p.drawText(QRectF(tx, H * 0.18 + 18, tw, 14),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   f"{ext_str}  ·  {size_str}")

        p.setFont(QFont(UI_FONT, 6))
        p.setPen(QPen(qcol("#1e5c6a"), 1))
        par = str(path.parent)
        if len(par) > 42: par = "…" + par[-41:]
        p.drawText(QRectF(tx, H * 0.18 + 34, tw, 12),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, par)

        p.setFont(QFont(UI_FONT, 9, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.RED, 180), 1))
        p.drawText(QRectF(W - 34, 0, 28, H), Qt.AlignmentFlag.AlignCenter, "✕")

    def mousePressEvent(self, e):
        z = self._z
        if z._current_file and e.pos().x() > self.width() - 34:
            z.clear_file()
        else:
            z.mousePressEvent(e)


class _CameraPreview(QWidget):
    """Floating overlay that briefly shows what the camera captured."""

    _W, _H = 244, 188

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            _CameraPreview {{
                background: rgba(6, 16, 42, 238);
                border: 1px solid {C.PRI};
                border-radius: 6px;
            }}
        """)
        self.setFixedWidth(self._W)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 5, 6, 6)
        lay.setSpacing(4)

        hdr = QHBoxLayout()
        title = QLabel("◈  VISUAL INPUT")
        title.setFont(QFont(UI_FONT, 7, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        hdr.addWidget(title)
        hdr.addStretch()
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(16, 16)
        close_btn.setFont(QFont(UI_FONT, 8))
        close_btn.setStyleSheet(
            f"color: {C.TEXT_DIM}; background: transparent; border: none;"
        )
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(self.hide)
        hdr.addWidget(close_btn)
        lay.addLayout(hdr)

        self._img_lbl = QLabel()
        self._img_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._img_lbl.setStyleSheet("background: transparent;")
        lay.addWidget(self._img_lbl)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)

        self.hide()

    def show_frame(self, img_bytes: bytes) -> None:
        px = QPixmap()
        px.loadFromData(img_bytes)
        if not px.isNull():
            max_w = self._W - 12
            scaled = px.scaled(
                max_w, 160,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._img_lbl.setPixmap(scaled)
            self._img_lbl.setFixedSize(scaled.width(), scaled.height())
            self.adjustSize()
        self.show()
        self.raise_()
        self._timer.start(6_000)   # auto-dismiss after 6 s


class SetupOverlay(QWidget):
    done = pyqtSignal(str, str, object)
    _validation_done = pyqtSignal(bool, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            SetupOverlay {{
                background: rgba(1, 6, 3, 248);
                border: 1px solid {C.BORDER_B};
                border-radius: 2px;
            }}
        """)
        detected = {"darwin": "mac", "windows": "windows"}.get(_OS.lower(), "linux")
        self._sel_os = detected
        self._checking = False
        self._profile = {}
        try:
            self._saved_cfg = _read_full_config()
        except Exception:
            self._saved_cfg = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 22, 28, 22)
        layout.setSpacing(10)

        self._stack = QStackedWidget(self)
        layout.addWidget(self._stack, stretch=1)
        self._validation_done.connect(self._on_validation_result)

        self._stack.addWidget(self._build_welcome_page())
        self._stack.addWidget(self._build_guest_page())
        self._stack.addWidget(self._build_key_page())
        self._stack.setCurrentIndex(0)

    def _label(self, text: str, size: int = 9, bold: bool = False,
               color: str | None = None, align=Qt.AlignmentFlag.AlignCenter):
        label = QLabel(text)
        label.setAlignment(align)
        label.setWordWrap(True)
        label.setFont(QFont(UI_FONT, size, QFont.Weight.Bold if bold else QFont.Weight.Normal))
        label.setStyleSheet(f"color: {color or C.PRI}; background: transparent;")
        return label

    def _button(self, text: str, primary: bool = False):
        button = QPushButton(text)
        button.setFont(QFont(UI_FONT, 9, QFont.Weight.Bold))
        button.setFixedHeight(38)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        if primary:
            button.setStyleSheet(f"""
                QPushButton {{ color: {C.BG}; background: {C.PRI};
                    border: 1px solid {C.PRI}; border-radius: 2px; padding: 0 14px; }}
                QPushButton:hover {{ background: {C.WHITE}; }}
            """)
        else:
            button.setStyleSheet(f"""
                QPushButton {{ color: {C.PRI}; background: transparent;
                    border: 1px solid {C.BORDER_B}; border-radius: 2px; padding: 0 14px; }}
                QPushButton:hover {{ background: {C.PRI_GHO}; border-color: {C.PRI}; }}
            """)
        return button

    def _build_welcome_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(10)
        layout.addStretch(1)
        layout.addWidget(self._label("ORI / WELCOME", 17, True, C.PRI))
        layout.addWidget(self._label(
            "A personal voice assistant for your desktop.",
            9, color=C.PRI_DIM,
        ))
        layout.addSpacing(10)

        google_row = QHBoxLayout()
        google_mark = QLabel(
            '<span style="color:#4285F4">G</span>'
        )
        google_mark.setFont(QFont("Arial", 21, QFont.Weight.Bold))
        google_mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        google_mark.setFixedWidth(34)
        google_mark.setStyleSheet("background: transparent;")
        google_btn = self._button("CONTINUE WITH GOOGLE")
        google_btn.setMinimumHeight(42)
        google_btn.clicked.connect(lambda: self._show_auth_coming_soon("Google sign-in"))
        google_row.addWidget(google_mark)
        google_row.addWidget(google_btn, 1)
        layout.addLayout(google_row)

        divider = QLabel("OR USE EMAIL")
        divider.setAlignment(Qt.AlignmentFlag.AlignCenter)
        divider.setFont(QFont(UI_FONT, 7, QFont.Weight.Bold))
        divider.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent; letter-spacing: 1px;")
        layout.addWidget(divider)

        self._email_input = QLineEdit()
        self._email_input.setPlaceholderText("Enter your email address")
        self._email_input.setMinimumHeight(38)
        self._email_input.setFont(QFont(UI_FONT, 9))
        self._email_input.setStyleSheet(f"""
            QLineEdit {{ color: {C.TEXT}; background: rgba(0, 5, 2, 220);
                border: 1px solid {C.BORDER}; border-radius: 2px; padding: 6px 9px; }}
            QLineEdit:focus {{ border-color: {C.PRI}; }}
        """)
        layout.addWidget(self._email_input)
        otp_btn = self._button("SEND EMAIL CODE")
        otp_btn.setMinimumHeight(38)
        otp_btn.clicked.connect(self._request_email_otp_preview)
        layout.addWidget(otp_btn)

        self._welcome_status = self._label(
            "Google sign-in and email OTP are not enabled yet. Guest access is available now.",
            8, color=C.TEXT_DIM,
        )
        layout.addWidget(self._welcome_status)

        guest = self._button("CONTINUE AS A GUEST", primary=True)
        guest.setMinimumHeight(42)
        guest.clicked.connect(lambda: self._stack.setCurrentIndex(1))
        layout.addWidget(guest)
        layout.addStretch(1)
        return page

    def _show_auth_coming_soon(self, provider: str) -> None:
        if hasattr(self, "_welcome_status"):
            self._welcome_status.setText(
                f"{provider} is coming soon. Continue as a guest to use ORI today."
            )
            self._welcome_status.setStyleSheet(f"color: {C.ACC}; background: transparent;")

    def _request_email_otp_preview(self) -> None:
        email = str(getattr(self, "_email_input", QLineEdit()).text() or "").strip()
        if email and ("@" not in email or "." not in email.rsplit("@", 1)[-1]):
            self._welcome_status.setText("Please enter a valid email address.")
            self._welcome_status.setStyleSheet(f"color: {C.RED}; background: transparent;")
            return
        self._welcome_status.setText(
            "Email OTP sign-in is coming soon. No code has been sent. Continue as a guest for now."
        )
        self._welcome_status.setStyleSheet(f"color: {C.ACC}; background: transparent;")

    def _build_guest_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(10)
        layout.addWidget(self._label("◈  GUEST PROFILE", 15, True, C.PRI))
        layout.addWidget(self._label(
            "A few preferences help ORI speak naturally. You can change these later in Settings.",
            8, color=C.PRI_DIM,
        ))
        layout.addSpacing(6)

        self._name_input = QLineEdit(str(self._saved_cfg.get("user_name") or ""))
        self._name_input.setPlaceholderText("What should ORI call you?")
        self._name_input.setMaxLength(64)
        self._name_input.setMinimumHeight(36)
        self._name_input.setFont(QFont(UI_FONT, 10))
        self._name_input.setStyleSheet(f"""
            QLineEdit {{ color: {C.TEXT}; background: rgba(0, 5, 2, 220);
                border: 1px solid {C.BORDER}; border-radius: 2px; padding: 6px 9px; }}
            QLineEdit:focus {{ border-color: {C.PRI}; }}
        """)
        layout.addWidget(self._label("YOUR NAME", 8, True, C.TEXT_DIM, Qt.AlignmentFlag.AlignLeft))
        layout.addWidget(self._name_input)

        self._language_combo = QComboBox()
        for item in ("Auto detect", "Hinglish", "Hindi", "English"):
            self._language_combo.addItem(item, item)
        current_language = str(self._saved_cfg.get("preferred_language", "Auto detect"))
        idx = self._language_combo.findData(current_language)
        self._language_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._style_combo = QComboBox()
        for item in ("Natural & friendly", "Concise", "Detailed", "Professional"):
            self._style_combo.addItem(item, item)
        current_style = str(self._saved_cfg.get("conversation_style", "Natural & friendly"))
        idx = self._style_combo.findData(current_style)
        self._style_combo.setCurrentIndex(idx if idx >= 0 else 0)
        for combo in (self._language_combo, self._style_combo):
            combo.setMinimumHeight(36)
            combo.setFont(QFont(UI_FONT, 9))
            combo.setStyleSheet(f"""
                QComboBox {{ color: {C.TEXT}; background: rgba(0, 5, 2, 220);
                    border: 1px solid {C.BORDER}; border-radius: 2px; padding: 5px 9px; }}
                QComboBox QAbstractItemView {{ color: {C.TEXT}; background: #020805;
                    selection-background-color: {C.PRI_GHO}; border: 1px solid {C.BORDER}; }}
            """)
        layout.addWidget(self._label("PREFERRED LANGUAGE", 8, True, C.TEXT_DIM, Qt.AlignmentFlag.AlignLeft))
        layout.addWidget(self._language_combo)
        layout.addWidget(self._label("CONVERSATION STYLE", 8, True, C.TEXT_DIM, Qt.AlignmentFlag.AlignLeft))
        layout.addWidget(self._style_combo)
        self._profile_error = self._label("", 8, color=C.RED, align=Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self._profile_error)

        actions = QHBoxLayout()
        back = self._button("BACK")
        back.clicked.connect(lambda: self._stack.setCurrentIndex(0))
        skip_btn = self._button("SKIP")
        skip_btn.clicked.connect(lambda: self._continue_to_key(skip=True))
        next_btn = self._button("CONTINUE", primary=True)
        next_btn.clicked.connect(self._continue_to_key)
        actions.addWidget(back)
        actions.addWidget(skip_btn)
        actions.addStretch(1)
        actions.addWidget(next_btn)
        layout.addLayout(actions)
        return page

    def _build_key_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(10)
        layout.addWidget(self._label("◈  CONNECT GEMINI", 15, True, C.PRI))
        layout.addWidget(self._label(
            "Paste one Google AI Studio API key. ORI selects a compatible Gemini model automatically; "
            "there is no model list to configure.",
            8, color=C.PRI_DIM,
        ))
        layout.addSpacing(8)
        layout.addWidget(self._label("GOOGLE AI STUDIO API KEY", 8, True, C.TEXT_DIM,
                                     Qt.AlignmentFlag.AlignLeft))
        self._key_input = QLineEdit()
        self._key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._key_input.setPlaceholderText("Paste your Google AI Studio key…")
        saved_key = str(self._saved_cfg.get("gemini_api_key") or "").strip()
        if saved_key:
            self._key_input.setText(saved_key)
        self._key_input.setMinimumHeight(38)
        self._key_input.setFont(QFont(UI_FONT, 10))
        self._key_input.setStyleSheet(f"""
            QLineEdit {{ color: {C.TEXT}; background: rgba(0, 5, 2, 220);
                border: 1px solid {C.BORDER}; border-radius: 2px; padding: 6px 9px; }}
            QLineEdit:focus {{ border-color: {C.PRI}; }}
        """)
        layout.addWidget(self._key_input)
        key_help = QPushButton("GET A GOOGLE AI STUDIO KEY ↗")
        key_help.setCursor(Qt.CursorShape.PointingHandCursor)
        key_help.setFont(QFont(UI_FONT, 8, QFont.Weight.Bold))
        key_help.setStyleSheet(f"color: {C.PRI}; background: transparent; border: none; text-align: left;")
        key_help.clicked.connect(lambda: __import__("webbrowser").open("https://aistudio.google.com/app/apikey"))
        layout.addWidget(key_help)
        layout.addStretch(1)

        self._key_status = self._label("", 8, color=C.TEXT_DIM, align=Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self._key_status)
        actions = QHBoxLayout()
        back = self._button("BACK")
        back.clicked.connect(lambda: self._stack.setCurrentIndex(1))
        self._connect_btn = self._button("VERIFY KEY & START ORI", primary=True)
        self._connect_btn.clicked.connect(self._submit)
        actions.addWidget(back)
        actions.addStretch(1)
        actions.addWidget(self._connect_btn)
        layout.addLayout(actions)
        return page

    def _continue_to_key(self, skip: bool = False):
        name = self._name_input.text().strip()
        if not name and not skip:
            self._profile_error.setText("Enter a name, or choose Skip.")
            self._name_input.setFocus()
            return
        if skip:
            name = "Guest"
        self._profile = {
            "user_name": name[:64],
            "preferred_language": (self._language_combo.currentData() or "Auto detect") if not skip else "Auto detect",
            "conversation_style": (self._style_combo.currentData() or "Natural & friendly") if not skip else "Natural & friendly",
            "guest_mode": True,
            "onboarding_completed": True,
        }
        self._profile_error.setText("")
        self._stack.setCurrentIndex(2)

    def _submit(self):
        key = self._key_input.text().strip()
        if not key or len(key) < 20:
            self._key_status.setText("Enter a valid-looking Google AI Studio key.")
            self._key_status.setStyleSheet(f"color: {C.RED}; background: transparent;")
            return
        if self._checking:
            return
        self._checking = True
        self._connect_btn.setEnabled(False)
        self._key_input.setEnabled(False)
        self._connect_btn.setText("VERIFYING WITH GOOGLE…")
        self._key_status.setText("Checking the key with Google AI Studio. This can take a few seconds.")
        self._key_status.setStyleSheet(f"color: {C.ACC}; background: transparent;")

        def work():
            try:
                from core.key_validation import validate_google_api_key
                ok, message = validate_google_api_key(key, timeout=8.0)
            except Exception as exc:
                ok, message = False, f"Key verification failed: {type(exc).__name__}."
            self._validation_done.emit(bool(ok), str(message))

        threading.Thread(target=work, daemon=True, name="ori-key-validation").start()

    def _on_validation_result(self, ok: bool, message: str):
        self._checking = False
        self._connect_btn.setEnabled(True)
        self._key_input.setEnabled(True)
        self._connect_btn.setText("VERIFY KEY & START ORI")
        self._key_status.setText(message)
        self._key_status.setStyleSheet(
            f"color: {C.GREEN if ok else C.RED}; background: transparent;"
        )
        if not ok:
            return
        os_name = {"Windows": "windows", "Darwin": "mac", "Linux": "linux"}.get(
            platform.system(), "linux"
        )
        self.done.emit(
            self._key_input.text().strip(),
            os_name,
            dict(self._profile),
        )
class HueWheel(QWidget):
    """
    Circular colour picker. The user drags the handle (small white circle)
    around the wheel to choose from ALL hues. The filled circle in the centre
    is a live preview of the selected colour.
    """

    hue_picked    = pyqtSignal(str)   # while dragging (live)
    hue_committed = pyqtSignal(str)   # when the handle is released

    _RING = 16   # ring thickness (px)

    def __init__(self, initial_hex: str = DEFAULT_UI_COLOR, parent=None):
        super().__init__(parent)
        self.setFixedSize(148, 148)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hue  = 0.53
        self._drag = False
        self.set_color(initial_hex)

    # ── API ──────────────────────────────────────────────────────────────────
    def color(self) -> str:
        return QColor.fromHsvF(self._hue, 1.0, 1.0).name()

    def set_color(self, hex_str: str):
        c = QColor((hex_str or "").strip())
        if c.isValid() and c.hsvHueF() >= 0:
            self._hue = c.hsvHueF()
            self.update()

    # ── geometry helpers ─────────────────────────────────────────────────────
    def _ring_rect(self) -> QRectF:
        m = self._RING / 2 + 3
        return QRectF(self.rect()).adjusted(m, m, -m, -m)

    def _hue_from_pos(self, pos: QPointF) -> float:
        c  = QRectF(self.rect()).center()
        dx = pos.x() - c.x()
        dy = c.y() - pos.y()          # screen y goes down — flip to math axis
        ang = math.atan2(dy, dx)      # [-π, π], counter-clockwise
        return (ang / (2 * math.pi)) % 1.0

    # ── drawing ──────────────────────────────────────────────────────────────
    def paintEvent(self, _):
        p = QPainter(self)
        if not p.isActive():
            return
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect   = self._ring_rect()
        center = rect.center()

        grad = QConicalGradient(center, 0)
        for i in range(0, 361, 20):
            grad.setColorAt(i / 360.0, QColor.fromHsvF((i % 360) / 360.0, 1.0, 1.0))
        p.setPen(QPen(QBrush(grad), self._RING))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(rect)

        # centre preview circle
        preview = QColor.fromHsvF(self._hue, 1.0, 1.0)
        inner   = rect.adjusted(30, 30, -30, -30)
        p.setPen(QPen(qcol(C.BORDER_B), 1))
        p.setBrush(QBrush(preview))
        p.drawEllipse(inner)

        # draggable handle
        r   = rect.width() / 2
        ang = self._hue * 2 * math.pi
        hx  = center.x() + r * math.cos(ang)
        hy  = center.y() - r * math.sin(ang)
        p.setPen(QPen(QColor("#00060a"), 2))
        p.setBrush(QBrush(QColor("#ffffff")))
        p.drawEllipse(QPointF(hx, hy), 7.5, 7.5)
        p.end()

    # ── fare ─────────────────────────────────────────────────────────────────
    def mousePressEvent(self, e):
        self._drag = True
        self._hue  = self._hue_from_pos(e.position())
        self.update()
        self.hue_picked.emit(self.color())

    def mouseMoveEvent(self, e):
        if self._drag:
            self._hue = self._hue_from_pos(e.position())
            self.update()
            self.hue_picked.emit(self.color())

    def mouseReleaseEvent(self, e):
        if self._drag:
            self._drag = False
            self.hue_committed.emit(self.color())


class CustomizeOverlay(QWidget):
    """Floating overlay — change assistant name, user name, UI colour and voice."""

    saved = pyqtSignal(str, str, str, str)   # assistant_name, user_name, ui_color, voice
    _OW, _OH = 400, 588

    def __init__(self, assistant_name="ORI", user_name="",
                 ui_color=DEFAULT_UI_COLOR, voice="", parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            CustomizeOverlay {{
                background: rgba(1, 6, 3, 248);
                border: 1px solid {C.BORDER_B};
                border-radius: 2px;
            }}
        """)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 18, 24, 18)
        lay.setSpacing(8)

        def _lbl(txt, fs=9, bold=False, color=C.PRI, align=Qt.AlignmentFlag.AlignCenter):
            w = QLabel(txt); w.setAlignment(align)
            w.setFont(QFont(UI_FONT, fs,
                            QFont.Weight.Bold if bold else QFont.Weight.Normal))
            w.setStyleSheet(f"color: {color}; background: transparent;")
            return w

        _fs = (f"QLineEdit {{ background: #050f2a; color: {C.TEXT}; "
               f"border: 1px solid {C.BORDER}; border-radius: 3px; padding: 4px 8px; }}"
               f"QLineEdit:focus {{ border: 1px solid {C.PRI}; }}")

        lay.addWidget(_lbl("⚙  CUSTOMISE ASSISTANT", 12, True))
        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER}; margin: 2px 0;")
        lay.addWidget(sep)

        lay.addWidget(_lbl("PRODUCT IDENTITY · DEVELOPER LOCKED", 8, color=C.TEXT_DIM,
                            align=Qt.AlignmentFlag.AlignLeft))
        self._name_input = QLineEdit("ORI")
        self._name_input.setReadOnly(True)
        self._name_input.setToolTip("ORI's canonical product identity is developer-controlled.")
        self._name_input.setFont(QFont(UI_FONT, 10))
        self._name_input.setFixedHeight(32)
        self._name_input.setStyleSheet(_fs)
        lay.addWidget(self._name_input)

        lay.addSpacing(4)
        lay.addWidget(_lbl("YOUR NAME  (leave blank for default sir / efendim)", 8,
                            color=C.TEXT_DIM, align=Qt.AlignmentFlag.AlignLeft))
        self._user_input = QLineEdit(user_name)
        self._user_input.setPlaceholderText("e.g.  Tony   (leave blank for auto)")
        self._user_input.setFont(QFont(UI_FONT, 10))
        self._user_input.setFixedHeight(32)
        self._user_input.setStyleSheet(_fs)
        lay.addWidget(self._user_input)

        # ── Assistant voice — Gemini prebuilt voices ─────────────────────────
        # Names are language-neutral proper nouns, so the row reads the same in
        # every locale. Selecting one and applying rebuilds the Live session.
        from memory.config_manager import AVAILABLE_VOICES, DEFAULT_VOICE
        lay.addSpacing(4)
        lay.addWidget(_lbl("ASSISTANT VOICE", 8, color=C.TEXT_DIM,
                            align=Qt.AlignmentFlag.AlignLeft))
        self._sel_voice   = (voice or DEFAULT_VOICE)
        if self._sel_voice not in AVAILABLE_VOICES:
            self._sel_voice = DEFAULT_VOICE
        self._voice_btns: dict[str, QPushButton] = {}
        voice_row = QHBoxLayout(); voice_row.setSpacing(4)
        for _v in AVAILABLE_VOICES:
            b = QPushButton(_v)
            b.setCheckable(True)
            b.setFixedHeight(28)
            b.setFont(QFont(UI_FONT, 8, QFont.Weight.Bold))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, name=_v: self._on_voice_pick(name))
            self._voice_btns[_v] = b
            voice_row.addWidget(b)
        lay.addLayout(voice_row)
        self._refresh_voice_btns()

        # ── UI colour — colour wheel ─────────────────────────────────────────
        lay.addSpacing(4)
        clr_hdr = QHBoxLayout()
        clr_hdr.addWidget(_lbl("UI COLOUR  —  drag the handle", 8,
                               color=C.TEXT_DIM, align=Qt.AlignmentFlag.AlignLeft))
        clr_hdr.addStretch()
        df_btn = QPushButton("DEFAULT")
        df_btn.setFixedSize(64, 20)
        df_btn.setFont(QFont(UI_FONT, 7, QFont.Weight.Bold))
        df_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        df_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 3px;
            }}
            QPushButton:hover {{ color: {C.TEXT}; border-color: {C.BORDER_B}; }}
        """)
        df_btn.clicked.connect(lambda: self._set_color(DEFAULT_UI_COLOR))
        clr_hdr.addWidget(df_btn)
        lay.addLayout(clr_hdr)

        self._initial_color = (ui_color or DEFAULT_UI_COLOR).strip().lower()
        self._sel_color     = self._initial_color
        self.on_preview     = None   # callable(hex) — live preview; MainWindow wires it

        self._wheel = HueWheel(self._sel_color)
        wheel_row = QHBoxLayout()
        wheel_row.addStretch(); wheel_row.addWidget(self._wheel); wheel_row.addStretch()
        lay.addLayout(wheel_row)
        self._wheel.hue_picked.connect(self._on_wheel_pick)
        self._wheel.hue_committed.connect(self._on_wheel_commit)

        self._hex_input = QLineEdit(self._sel_color)
        self._hex_input.setPlaceholderText("#00d4ff   (custom hex colour)")
        self._hex_input.setFont(QFont(UI_FONT, 10))
        self._hex_input.setFixedHeight(28)
        self._hex_input.setStyleSheet(_fs)
        self._hex_input.textEdited.connect(self._on_hex_edited)
        lay.addWidget(self._hex_input)

        lay.addSpacing(6)
        btn_row = QHBoxLayout(); btn_row.setSpacing(8)

        save_btn = QPushButton("▸  APPLY CHANGES")
        save_btn.setFixedHeight(34)
        save_btn.setFont(QFont(UI_FONT, 9, QFont.Weight.Bold))
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.PRI};
                border: 1px solid {C.PRI_DIM}; border-radius: 3px;
            }}
            QPushButton:hover {{ background: {C.PRI_GHO}; border: 1px solid {C.PRI}; }}
        """)
        save_btn.clicked.connect(self._save)
        btn_row.addWidget(save_btn)

        cancel_btn = QPushButton("CANCEL")
        cancel_btn.setFixedHeight(34)
        cancel_btn.setFont(QFont(UI_FONT, 9))
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 3px;
            }}
            QPushButton:hover {{ color: {C.TEXT}; border-color: {C.BORDER_B}; }}
        """)
        cancel_btn.clicked.connect(self._cancel)
        btn_row.addWidget(cancel_btn)
        lay.addLayout(btn_row)

    # ── voice selection ──────────────────────────────────────────────────────
    def _on_voice_pick(self, name: str):
        self._sel_voice = name
        self._refresh_voice_btns()

    def _refresh_voice_btns(self):
        """Highlight the selected voice pill; dim the rest."""
        for name, b in self._voice_btns.items():
            on = (name == self._sel_voice)
            b.setChecked(on)
            if on:
                b.setStyleSheet(f"""
                    QPushButton {{ background: {C.PRI_GHO}; color: {C.PRI};
                        border: 1px solid {C.PRI}; border-radius: 3px; }}
                """)
            else:
                b.setStyleSheet(f"""
                    QPushButton {{ background: transparent; color: {C.TEXT_MED};
                        border: 1px solid {C.BORDER}; border-radius: 3px; }}
                    QPushButton:hover {{ color: {C.TEXT}; border-color: {C.BORDER_B}; }}
                """)

    # ── colour flow ──────────────────────────────────────────────────────────
    def _set_color(self, hx: str, update_wheel: bool = True, preview: bool = True):
        """Updates the selected colour; hex box + wheel stay in sync, theme is live-previewed."""
        self._sel_color = hx.strip().lower()
        self._hex_input.blockSignals(True)
        self._hex_input.setText(self._sel_color)
        self._hex_input.blockSignals(False)
        if update_wheel:
            self._wheel.set_color(self._sel_color)
        if preview and self.on_preview:
            self.on_preview(self._sel_color)

    def _on_wheel_pick(self, hx: str):
        # While dragging: update the hex box, don't apply the theme yet
        self._sel_color = hx
        self._hex_input.blockSignals(True)
        self._hex_input.setText(hx)
        self._hex_input.blockSignals(False)

    def _on_wheel_commit(self, hx: str):
        # Handle released → live-preview the whole interface
        self._set_color(hx, update_wheel=False)

    def _on_hex_edited(self, text: str):
        t = text.strip().lower()
        if t.startswith("#") and len(t) == 7:
            try:
                int(t[1:], 16)
            except ValueError:
                return
            self._set_color(t, update_wheel=True, preview=True)

    def _cancel(self):
        # If a preview was applied, revert to the colour from launch
        if self.on_preview and self._sel_color != self._initial_color:
            self.on_preview(self._initial_color)
        self.hide()

    def _save(self):
        name = self._name_input.text().strip() or "ORI"
        user = self._user_input.text().strip()
        self.saved.emit(name, user, self._sel_color or DEFAULT_UI_COLOR, self._sel_voice)
        self.hide()


class PluginManagerOverlay(QWidget):
    """Floating overlay — lists discovered plugins with per-plugin ON/OFF toggles."""

    _OW = 420

    def __init__(self, plugins: list[dict], parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            PluginManagerOverlay {{
                background: rgba(1, 6, 3, 248);
                border: 1px solid {C.BORDER_B};
                border-radius: 2px;
            }}
        """)
        self.setFixedWidth(self._OW)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(6)

        hdr = QLabel("🧩  PLUGIN MANAGER")
        hdr.setFont(QFont(UI_FONT, 12, QFont.Weight.Bold))
        hdr.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        lay.addWidget(hdr)
        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER}; margin: 2px 0;")
        lay.addWidget(sep)

        if not plugins:
            empty = QLabel("No plugins found in /plugins.")
            empty.setFont(QFont(UI_FONT, 8))
            empty.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
            lay.addWidget(empty)

        for p in plugins:
            lay.addLayout(self._build_row(p))

        lay.addSpacing(4)
        close_btn = QPushButton("CLOSE")
        close_btn.setFixedHeight(30)
        close_btn.setFont(QFont(UI_FONT, 9))
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 3px;
            }}
            QPushButton:hover {{ color: {C.TEXT}; border-color: {C.BORDER_B}; }}
        """)
        close_btn.clicked.connect(self.hide)
        lay.addWidget(close_btn)
        self.adjustSize()

    def _build_row(self, p: dict) -> QHBoxLayout:
        row = QHBoxLayout(); row.setSpacing(6)

        label_text = p["name"] if p["valid"] else f"{p['name']}  (⚠ {p['file']})"
        lbl = QLabel(label_text)
        lbl.setFont(QFont(UI_FONT, 8))
        lbl.setStyleSheet(f"color: {C.TEXT if p['valid'] else C.TEXT_DIM}; background: transparent;")
        lbl.setToolTip(p["description"] if p["valid"] else p["error"])
        lbl.setWordWrap(False)
        row.addWidget(lbl, stretch=1)

        btn = QPushButton()
        btn.setFixedSize(72, 24)
        btn.setFont(QFont(UI_FONT, 7, QFont.Weight.Bold))
        if not p["valid"]:
            btn.setText("BROKEN")
            btn.setEnabled(False)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; color: {C.TEXT_DIM};
                    border: 1px solid {C.BORDER}; border-radius: 3px;
                }}
            """)
        else:
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self._style_toggle(btn, p["enabled"])
            btn.clicked.connect(lambda _, name=p["name"], b=btn: self._toggle(name, b))
        row.addWidget(btn)
        return row

    def _style_toggle(self, btn: QPushButton, enabled: bool):
        if enabled:
            btn.setText("ON")
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: #001a08; color: {C.GREEN};
                    border: 1px solid {C.GREEN_D}; border-radius: 3px;
                }}
                QPushButton:hover {{ background: #002010; }}
            """)
        else:
            btn.setText("OFF")
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; color: {C.TEXT_DIM};
                    border: 1px solid {C.BORDER}; border-radius: 3px;
                }}
                QPushButton:hover {{ color: {C.TEXT}; border-color: {C.BORDER_B}; }}
            """)

    def _toggle(self, name: str, btn: QPushButton):
        from memory.config_manager import get_plugin_enabled, save_plugin_enabled
        new_val = not get_plugin_enabled(name)
        save_plugin_enabled(name, new_val)
        self._style_toggle(btn, new_val)


class _HudOverlay(QWidget):
    """Base for the floating panels placed by hand over the HUD.

    They are children of the central widget but sit in no layout, so Qt never
    invalidates the region they occupy when they hide or shrink: the HUD keeps
    painting around them and their last frame stays on screen as a ghost. Any
    overlay positioned with _centre_overlay needs this."""

    def hideEvent(self, e):
        p = self.parentWidget()
        if p is not None:
            # Repaint exactly what we were covering, before we stop covering it.
            p.update(self.geometry())
        super().hideEvent(e)

    def closeEvent(self, e):
        p = self.parentWidget()
        if p is not None:
            p.update(self.geometry())
        super().closeEvent(e)


class ConfirmBanner(_HudOverlay):
    """The gate in front of an action that cannot be taken back.

    The old confirmation was a tool parameter the model filled in itself, which
    means it confirmed its own shutdown requests. This is the interface asking,
    and the answer travels from a human finger to core/confirm.py without the
    model in the loop. Nothing blocks while it is up: the assistant keeps
    talking, so this costs no latency — unlike the old gate, which spent two
    tool round trips on every power command."""

    answered = pyqtSignal(bool)
    _OW = 430

    def __init__(self, title: str, detail: str, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            ConfirmBanner {{
                background: rgba(14, 3, 0, 250);
                border: 1px solid {C.ACC};
                border-radius: 6px;
            }}
        """)
        self.setFixedWidth(self._OW)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(8)

        hdr = QLabel("⚠  CONFIRM")
        hdr.setFont(QFont(UI_FONT, 11, QFont.Weight.Bold))
        hdr.setStyleSheet(f"color: {C.ACC}; background: transparent;")
        lay.addWidget(hdr)

        ttl = QLabel(title)
        ttl.setWordWrap(True)
        ttl.setFont(QFont(UI_FONT, 10, QFont.Weight.Bold))
        ttl.setStyleSheet(f"color: {C.TEXT}; background: transparent;")
        lay.addWidget(ttl)

        if detail:
            dtl = QLabel(detail)
            dtl.setWordWrap(True)
            dtl.setFont(QFont(UI_FONT, 8))
            dtl.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
            lay.addWidget(dtl)

        row = QHBoxLayout(); row.setSpacing(8)

        yes = QPushButton("▸  CONFIRM")
        yes.setFixedHeight(32)
        yes.setFont(QFont(UI_FONT, 9, QFont.Weight.Bold))
        yes.setCursor(Qt.CursorShape.PointingHandCursor)
        yes.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {C.ACC};
                border: 1px solid {C.ACC}; border-radius: 3px; }}
            QPushButton:hover {{ background: rgba(255,107,0,40); }}
        """)
        yes.clicked.connect(lambda: self.answered.emit(True))
        row.addWidget(yes)

        no = QPushButton("CANCEL")
        no.setFixedHeight(32)
        no.setFont(QFont(UI_FONT, 9))
        no.setCursor(Qt.CursorShape.PointingHandCursor)
        no.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 3px; }}
            QPushButton:hover {{ color: {C.TEXT}; border-color: {C.BORDER_B}; }}
        """)
        no.clicked.connect(lambda: self.answered.emit(False))
        row.addWidget(no)
        lay.addLayout(row)

        # Default focus on CANCEL: if someone hits Enter without reading, the
        # safe answer wins.
        no.setDefault(True)
        no.setFocus()


class AudioDeviceOverlay(_HudOverlay):
    """Choose which microphone ORI listens to and which speakers it uses.

    Both audio streams used to open with no `device=` at all, so they always
    took the OS default — which on Windows moves by itself the moment a headset
    is plugged in. 'ORI can't hear me' is usually 'ORI is listening to the
    webcam'."""

    picked = pyqtSignal()      # emitted after Apply, when something changed
    _OW = 460

    def __init__(self, parent=None):
        super().__init__(parent)
        from core.audio_devices import list_devices, DEFAULT_LABEL
        from memory.config_manager import get_input_device, get_output_device

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            AudioDeviceOverlay {{
                background: rgba(1, 6, 3, 248);
                border: 1px solid {C.BORDER_B};
                border-radius: 2px;
            }}
        """)
        self.setFixedWidth(self._OW)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(6)

        hdr = QLabel("🎧  AUDIO DEVICES")
        hdr.setFont(QFont(UI_FONT, 12, QFont.Weight.Bold))
        hdr.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        lay.addWidget(hdr)

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER}; margin: 2px 0;")
        lay.addWidget(sep)

        _combo_css = (
            f"QComboBox {{ background: #050f2a; color: {C.TEXT}; "
            f"border: 1px solid {C.BORDER}; border-radius: 3px; padding: 4px 8px; }}"
            f"QComboBox:hover {{ border-color: {C.BORDER_B}; }}"
            f"QComboBox QAbstractItemView {{ background: #050f2a; color: {C.TEXT}; "
            f"selection-background-color: {C.PRI_GHO}; border: 1px solid {C.BORDER}; }}"
        )

        def _row(label: str, kind: str, current: str) -> QComboBox:
            cap = QLabel(label)
            cap.setFont(QFont(UI_FONT, 8))
            cap.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
            lay.addWidget(cap)

            box = QComboBox()
            box.setFont(QFont(UI_FONT, 9))
            box.setFixedHeight(30)
            box.setStyleSheet(_combo_css)
            # The list is served from a cache warmed on a background thread at
            # startup, so opening this panel never blocks the Qt thread on the
            # host audio API.
            box.addItem(DEFAULT_LABEL, "")
            for name in list_devices(kind):
                box.addItem(name, name)
            idx = box.findData(current) if current else 0
            box.setCurrentIndex(idx if idx >= 0 else 0)
            if current and idx < 0:
                # Saved device is not plugged in right now. Show it rather than
                # silently resetting the user's choice to default.
                box.addItem(f"{current}  (not connected)", current)
                box.setCurrentIndex(box.count() - 1)
            lay.addWidget(box)
            return box

        self._in_box  = _row("MICROPHONE — what ORI hears you with",
                             "input", get_input_device())
        lay.addSpacing(4)
        self._out_box = _row("SPEAKERS — what ORI talks through",
                             "output", get_output_device())

        note = QLabel("Applying reconnects the session. Your conversation is kept.")
        note.setWordWrap(True)
        note.setFont(QFont(UI_FONT, 7))
        note.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        lay.addSpacing(6)
        lay.addWidget(note)

        row = QHBoxLayout(); row.setSpacing(8)
        ok = QPushButton("▸  APPLY")
        ok.setFixedHeight(32)
        ok.setFont(QFont(UI_FONT, 9, QFont.Weight.Bold))
        ok.setCursor(Qt.CursorShape.PointingHandCursor)
        ok.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {C.PRI};
                border: 1px solid {C.PRI_DIM}; border-radius: 3px; }}
            QPushButton:hover {{ background: {C.PRI_GHO}; border-color: {C.PRI}; }}
        """)
        ok.clicked.connect(self._apply)
        row.addWidget(ok)

        cancel = QPushButton("CLOSE")
        cancel.setFixedHeight(32)
        cancel.setFont(QFont(UI_FONT, 9))
        cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 3px; }}
            QPushButton:hover {{ color: {C.TEXT}; border-color: {C.BORDER_B}; }}
        """)
        cancel.clicked.connect(self.hide)
        row.addWidget(cancel)
        lay.addLayout(row)

    def _apply(self):
        from memory.config_manager import (
            get_input_device, get_output_device,
            save_input_device, save_output_device,
        )
        new_in  = self._in_box.currentData()  or ""
        new_out = self._out_box.currentData() or ""
        changed = (new_in != get_input_device()) or (new_out != get_output_device())
        save_input_device(new_in)
        save_output_device(new_out)
        self.hide()
        # Only rebuild the session if something actually moved — a no-op Apply
        # should not cost a reconnect.
        if changed:
            self.picked.emit()


class MemoryOverlay(_HudOverlay):
    """Everything ORI has stored about you, and when it learned it.

    Memory used to be a 2200-character store that deleted its oldest entries
    when full and mentioned it only on stdout. The cap is gone; this panel is
    the other half of that change — a memory you cannot inspect is a memory you
    cannot trust, and 'delete' has to be something the person can do."""

    _OW = 520

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            MemoryOverlay {{
                background: rgba(1, 6, 3, 248);
                border: 1px solid {C.BORDER_B};
                border-radius: 2px;
            }}
        """)
        self.setFixedWidth(self._OW)

        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(20, 16, 20, 16)
        self._lay.setSpacing(5)
        self._rebuild()

    def _clear_layout(self):
        """Take every item out of the layout and detach it from the widget tree
        in this call.

        deleteLater() on its own is not enough: it queues destruction for the
        next event-loop pass, and until then the old rows are still children of
        this widget and still paint — which is what drew half of the previous
        panel over the new one. setParent(None) removes them from the tree now;
        deleteLater() then frees them safely."""
        while self._lay.count():
            item = self._lay.takeAt(0)
            w = item.widget()
            if w is not None:
                # hide() stops it painting in this frame; deleteLater() frees it
                # safely afterwards. setParent(None) would also stop the paint,
                # but it turns the widget into a top-level window for the moment
                # between the two calls, which is not something to leave lying
                # around inside a click handler.
                w.hide()
                w.deleteLater()
                continue
            sub = item.layout()
            if sub is not None:
                while sub.count():
                    si = sub.takeAt(0)
                    sw = si.widget()
                    if sw is not None:
                        sw.hide()
                        sw.deleteLater()
                sub.deleteLater()

    def _settle(self, before):
        """Size the panel to its content, re-centre it, and repaint what the old
        size covered.

        The re-size has to happen here rather than at the end of _rebuild
        because Qt has not polished the freshly-created children at that point,
        so the size hint it would read is the empty-layout one. Measured: a
        first adjustSize() returned 32 px for a panel whose content needed 155,
        and a second call — after the same widgets had been through the event
        loop — returned 155. So this runs twice: once now, once on the next
        turn, from _rebuild.

        The re-centre and the repaint are needed because the overlay is placed
        by hand and is in no layout: shrinking it leaves it off-centre and
        leaves its former pixels on screen, since nothing tells the parent that
        region changed. The repaint has to cover the union of the old and new
        rectangles."""
        self._lay.invalidate()
        self._lay.activate()
        self.updateGeometry()
        self.adjustSize()

        p = self.parentWidget()
        if p is None:
            self.update()
            return
        self.move(max(0, (p.width()  - self.width())  // 2),
                  max(0, (p.height() - self.height()) // 2))
        p.update(before.united(self.geometry()))
        self.update()

    def _rebuild(self):
        before = self.geometry()
        self._clear_layout()

        from memory.memory_manager import all_entries_for_ui

        hdr = QLabel("🧠  WHAT ORI REMEMBERS")
        hdr.setFont(QFont(UI_FONT, 12, QFont.Weight.Bold))
        hdr.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        self._lay.addWidget(hdr)

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER}; margin: 2px 0;")
        self._lay.addWidget(sep)

        rows = all_entries_for_ui()

        cap = QLabel(f"{len(rows)} stored facts — newest first. "
                     f"Nothing here is sent anywhere; it lives in "
                     f"memory/long_term.json on this machine.")
        cap.setWordWrap(True)
        cap.setFont(QFont(UI_FONT, 7))
        cap.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        self._lay.addWidget(cap)

        if not rows:
            empty = QLabel("Nothing stored yet.")
            empty.setFont(QFont(UI_FONT, 9))
            empty.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
            self._lay.addWidget(empty)
        else:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFixedHeight(min(420, 34 * len(rows) + 10))
            scroll.setStyleSheet(
                f"QScrollArea {{ border: 1px solid {C.BORDER}; border-radius: 3px; "
                f"background: transparent; }}"
            )
            inner = QWidget()
            ilay  = QVBoxLayout(inner)
            ilay.setContentsMargins(6, 6, 6, 6)
            ilay.setSpacing(3)

            for r in rows:
                line = QHBoxLayout(); line.setSpacing(6)
                txt = QLabel(f"<b>{r['key'].replace('_', ' ')}</b> "
                             f"<span style='color:{C.TEXT_MED}'>— {r['value']}</span>")
                txt.setWordWrap(True)
                txt.setFont(QFont(UI_FONT, 8))
                txt.setStyleSheet(f"color: {C.TEXT}; background: transparent;")
                line.addWidget(txt, 1)

                meta = QLabel(f"{r['category'][:4]} · {r['updated'] or '—'}")
                meta.setFont(QFont(UI_FONT, 7))
                meta.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
                line.addWidget(meta)

                rm = QPushButton("✕")
                rm.setFixedSize(20, 20)
                rm.setFont(QFont(UI_FONT, 8, QFont.Weight.Bold))
                rm.setCursor(Qt.CursorShape.PointingHandCursor)
                rm.setToolTip("Forget this")
                rm.setStyleSheet(f"""
                    QPushButton {{ background: transparent; color: {C.TEXT_DIM};
                        border: 1px solid {C.BORDER}; border-radius: 3px; }}
                    QPushButton:hover {{ color: {C.RED}; border-color: {C.RED}; }}
                """)
                rm.clicked.connect(
                    lambda _=False, c=r["category"], k=r["key"]: self._forget(c, k))
                line.addWidget(rm)

                holder = QWidget()
                holder.setLayout(line)
                ilay.addWidget(holder)

            ilay.addStretch()
            scroll.setWidget(inner)
            self._lay.addWidget(scroll)

        close = QPushButton("CLOSE")
        close.setFixedHeight(30)
        close.setFont(QFont(UI_FONT, 9))
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 3px; }}
            QPushButton:hover {{ color: {C.TEXT}; border-color: {C.BORDER_B}; }}
        """)
        close.clicked.connect(self.hide)
        self._lay.addWidget(close)

        self._settle(before)
        # …and again once Qt has polished the new children, because the size
        # hint is not final until then. Harmless when the first pass already
        # got it right: _settle is idempotent.
        QTimer.singleShot(0, lambda g=before: self._settle(g))

    def _forget(self, category: str, key: str):
        from memory.memory_manager import forget
        forget(key, category)
        # Rebuild on the NEXT event-loop turn, not inside this click handler.
        # The rebuild destroys the very ✕ button that emitted this signal, and
        # Qt is entitled to touch the sender after a slot returns; tearing it
        # down mid-emission is how a widget ends up half-alive on screen.
        QTimer.singleShot(0, self._rebuild)


class ClipboardPanel(QWidget):
    """Floating panel shown when text is copied — offers quick ORI actions."""

    action_requested = pyqtSignal(str)
    _W, _H = 326, 112

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            ClipboardPanel {{
                background: rgba(1, 6, 3, 248);
                border: 1px solid {C.BORDER_B};
                border-radius: 2px;
            }}
        """)
        self.setFixedWidth(self._W)
        self._clip_text = ""

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 7)
        lay.setSpacing(4)

        hdr = QHBoxLayout(); hdr.setSpacing(4)
        icon_lbl = QLabel("◈  CLIPBOARD DETECTED")
        icon_lbl.setFont(QFont(UI_FONT, 7, QFont.Weight.Bold))
        icon_lbl.setStyleSheet(f"color: {C.ACC2}; background: transparent;")
        hdr.addWidget(icon_lbl); hdr.addStretch()
        x_btn = QPushButton("✕")
        x_btn.setFixedSize(16, 16)
        x_btn.setFont(QFont(UI_FONT, 8))
        x_btn.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent; border: none;")
        x_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        x_btn.clicked.connect(self.hide)
        hdr.addWidget(x_btn)
        lay.addLayout(hdr)

        self._preview = QLabel()
        self._preview.setFont(QFont(UI_FONT, 8))
        self._preview.setStyleSheet(f"""
            color: {C.TEXT}; background: {C.PANEL2};
            border: 1px solid {C.BORDER}; border-radius: 3px; padding: 4px 6px;
        """)
        self._preview.setWordWrap(False)
        self._preview.setFixedHeight(28)
        lay.addWidget(self._preview)

        btn_row = QHBoxLayout(); btn_row.setSpacing(4)
        _bs = (f"QPushButton {{ background: {C.PANEL2}; color: {C.TEXT_MED}; "
               f"border: 1px solid {C.BORDER}; border-radius: 2px; }}"
               f"QPushButton:hover {{ color: {C.PRI}; border-color: {C.BORDER_B}; }}")
        for label, cmd_fmt in [
            ("TRANSLATE", "Translate this text to English: {text}"),
            ("SUMMARISE", "Summarise this: {text}"),
            ("EXPLAIN",   "Explain this: {text}"),
            ("FIX",       "Fix grammar and spelling: {text}"),
        ]:
            b = QPushButton(label)
            b.setFixedHeight(22)
            b.setFont(QFont(UI_FONT, 7, QFont.Weight.Bold))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(_bs)
            b.clicked.connect(lambda _, c=cmd_fmt: self._trigger(c))
            btn_row.addWidget(b)
        lay.addLayout(btn_row)

        self._dismiss_timer = QTimer(self)
        self._dismiss_timer.setSingleShot(True)
        self._dismiss_timer.timeout.connect(self.hide)
        self.hide()

    def _trigger(self, cmd_fmt: str):
        if self._clip_text:
            self.action_requested.emit(cmd_fmt.format(text=self._clip_text[:800]))
        self.hide()

    def show_clipboard(self, text: str):
        self._clip_text = text
        preview = text[:58].replace('\n', ' ')
        if len(text) > 58:
            preview += "…"
        self._preview.setText(f'"{preview}"')
        self.show(); self.raise_()
        self._dismiss_timer.start(8000)


class PluginSettingsOverlay(QWidget):
    """Floating overlay — renders per-plugin settings forms.

    Fully generic: it iterates the settings schemas a plugin declared via its
    PLUGIN_SETTINGS constant (delivered by PluginRegistry.settings_schemas) and
    builds a form for each. It knows NOTHING about any specific plugin, so the
    core stays clean and plugins remain pure drop-in — install a plugin that
    declares fields (e.g. the 3D-printer suite) and its section appears here;
    install none and this panel simply says there's nothing to configure.
    """

    _test_done = pyqtSignal(str, bool, str)   # namespace, ok, message
    _OW = 460

    def __init__(self, sections: list[dict], parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            PluginSettingsOverlay {{
                background: rgba(1, 6, 3, 248);
                border: 1px solid {C.BORDER_B};
                border-radius: 2px;
            }}
        """)
        self._sections = sections or []
        self._widgets: dict[tuple, object] = {}    # (namespace, key) -> input widget
        self._types:   dict[tuple, str]    = {}     # (namespace, key) -> field type
        self._status_labels: dict[str, QLabel] = {} # namespace -> status QLabel
        self._test_done.connect(self._on_test_done)

        self._fs = (f"QLineEdit {{ background: #050f2a; color: {C.TEXT}; "
                    f"border: 1px solid {C.BORDER}; border-radius: 3px; padding: 4px 8px; }}"
                    f"QLineEdit:focus {{ border: 1px solid {C.PRI}; }}")

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 16, 22, 16)
        root.setSpacing(8)

        root.addWidget(self._lbl("⚙  PLUGIN SETTINGS", 12, True))
        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER}; margin: 2px 0;")
        root.addWidget(sep)

        if not self._sections:
            root.addWidget(self._lbl(
                "No configurable plugins are installed.\nDrop a plugin that needs "
                "settings (like the 3D-printer suite) into the plugins folder and "
                "it will show up here.", 9, color=C.TEXT_DIM))
        else:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.Shape.NoFrame)
            scroll.setStyleSheet("QScrollArea { background: transparent; }")
            inner = QWidget()
            inner.setStyleSheet("background: transparent;")
            form = QVBoxLayout(inner)
            form.setContentsMargins(0, 0, 6, 0)
            form.setSpacing(6)
            for sec in self._sections:
                self._build_section(form, sec)
            form.addStretch(1)
            scroll.setWidget(inner)
            root.addWidget(scroll, 1)

        # ── bottom buttons ───────────────────────────────────────────────────
        btn_row = QHBoxLayout(); btn_row.setSpacing(8)
        if self._sections:
            save_btn = QPushButton("▸  SAVE")
            save_btn.setFixedHeight(34)
            save_btn.setFont(QFont(UI_FONT, 9, QFont.Weight.Bold))
            save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            save_btn.setStyleSheet(f"""
                QPushButton {{ background: transparent; color: {C.PRI};
                    border: 1px solid {C.PRI_DIM}; border-radius: 3px; }}
                QPushButton:hover {{ background: {C.PRI_GHO}; border: 1px solid {C.PRI}; }}
            """)
            save_btn.clicked.connect(self._save_all)
            btn_row.addWidget(save_btn)

        close_btn = QPushButton("CLOSE")
        close_btn.setFixedHeight(34)
        close_btn.setFont(QFont(UI_FONT, 9))
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 3px; }}
            QPushButton:hover {{ color: {C.TEXT}; border-color: {C.BORDER_B}; }}
        """)
        close_btn.clicked.connect(self.hide)
        btn_row.addWidget(close_btn)
        root.addLayout(btn_row)

    # ── helpers ───────────────────────────────────────────────────────────────
    def _lbl(self, txt, fs=9, bold=False, color=C.PRI,
             align=Qt.AlignmentFlag.AlignLeft):
        w = QLabel(txt); w.setAlignment(align); w.setWordWrap(True)
        w.setFont(QFont(UI_FONT, fs,
                        QFont.Weight.Bold if bold else QFont.Weight.Normal))
        w.setStyleSheet(f"color: {color}; background: transparent;")
        return w

    def _build_section(self, form: QVBoxLayout, sec: dict):
        ns     = sec.get("namespace") or sec.get("plugin") or "plugin"
        title  = sec.get("title") or ns
        fields = sec.get("fields") or []
        values = sec.get("values") or {}

        form.addSpacing(4)
        form.addWidget(self._lbl(title, 10, True, C.PRI))

        for field in fields:
            if not isinstance(field, dict) or not field.get("key"):
                continue
            key   = field["key"]
            ftype = (field.get("type") or "text").lower()
            label = field.get("label") or key
            default = field.get("default")
            stored  = values.get(key, default)

            form.addWidget(self._lbl(label.upper(), 8, color=C.TEXT_DIM))

            if ftype == "choice":
                w = QComboBox()
                w.addItems([str(o) for o in field.get("options", [])])
                w.setFont(QFont(UI_FONT, 9))
                w.setFixedHeight(30)
                w.setStyleSheet(
                    f"QComboBox {{ background: #050f2a; color: {C.TEXT}; "
                    f"border: 1px solid {C.BORDER}; border-radius: 3px; padding: 2px 8px; }}"
                    f"QComboBox QAbstractItemView {{ background: #050f2a; color: {C.TEXT}; "
                    f"selection-background-color: {C.PRI_GHO}; }}")
                if stored is not None:
                    w.setCurrentText(str(stored))
            elif ftype == "toggle":
                w = QPushButton()
                w.setCheckable(True)
                w.setChecked(bool(stored))
                w.setFixedHeight(28)
                w.setFont(QFont(UI_FONT, 8, QFont.Weight.Bold))
                w.setCursor(Qt.CursorShape.PointingHandCursor)
                self._style_toggle(w)
                w.toggled.connect(lambda _=False, b=w: self._style_toggle(b))
            else:  # text / password
                w = QLineEdit("" if stored is None else str(stored))
                w.setFont(QFont(UI_FONT, 10))
                w.setFixedHeight(30)
                w.setStyleSheet(self._fs)
                if field.get("placeholder"):
                    w.setPlaceholderText(str(field["placeholder"]))
                if ftype == "password":
                    w.setEchoMode(QLineEdit.EchoMode.Password)

            self._widgets[(ns, key)] = w
            self._types[(ns, key)]   = ftype
            form.addWidget(w)

        # optional test/connect action button + status line
        action = sec.get("action")
        if isinstance(action, dict) and callable(action.get("run")):
            form.addSpacing(2)
            ab = QPushButton(str(action.get("label") or "TEST"))
            ab.setFixedHeight(30)
            ab.setFont(QFont(UI_FONT, 8, QFont.Weight.Bold))
            ab.setCursor(Qt.CursorShape.PointingHandCursor)
            ab.setStyleSheet(f"""
                QPushButton {{ background: #07163a; color: {C.PRI};
                    border: 1px solid {C.PRI_DIM}; border-radius: 3px; }}
                QPushButton:hover {{ background: {C.PRI_GHO}; border-color: {C.PRI}; }}
            """)
            ab.clicked.connect(lambda _=False, n=ns: self._run_action(n))
            form.addWidget(ab)

        status = self._lbl("", 8, color=C.TEXT_DIM)
        self._status_labels[ns] = status
        form.addWidget(status)

        line = QFrame(); line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet(f"color: {C.BORDER}; margin: 4px 0;")
        form.addWidget(line)

    def _style_toggle(self, btn: QPushButton):
        on = btn.isChecked()
        btn.setText("ON" if on else "OFF")
        if on:
            btn.setStyleSheet(f"QPushButton {{ background: {C.PRI_GHO}; color: {C.PRI}; "
                              f"border: 1px solid {C.PRI}; border-radius: 3px; }}")
        else:
            btn.setStyleSheet(f"QPushButton {{ background: transparent; color: {C.TEXT_MED}; "
                              f"border: 1px solid {C.BORDER}; border-radius: 3px; }}")

    # ── data ──────────────────────────────────────────────────────────────────
    def _gather(self, ns: str) -> dict:
        out = {}
        for (n, key), w in self._widgets.items():
            if n != ns:
                continue
            t = self._types.get((n, key), "text")
            if t == "choice":
                out[key] = w.currentText()
            elif t == "toggle":
                out[key] = w.isChecked()
            else:
                out[key] = w.text().strip()
        return out

    def _save_ns(self, ns: str):
        from memory.config_manager import save_plugin_config
        save_plugin_config(ns, self._gather(ns))

    def _save_all(self):
        for sec in self._sections:
            ns = sec.get("namespace") or sec.get("plugin")
            if ns:
                self._save_ns(ns)
                lbl = self._status_labels.get(ns)
                if lbl:
                    lbl.setText("Saved ✓")
                    lbl.setStyleSheet(f"color: {C.PRI}; background: transparent;")

    def _run_action(self, ns: str):
        sec = next((s for s in self._sections
                    if (s.get("namespace") or s.get("plugin")) == ns), None)
        if not sec:
            return
        run_fn = (sec.get("action") or {}).get("run")
        if not callable(run_fn):
            return
        self._save_ns(ns)                 # persist what the user typed before testing
        values = self._gather(ns)
        lbl = self._status_labels.get(ns)
        if lbl:
            lbl.setText("Testing…")
            lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")

        def worker():
            try:
                res = run_fn(values)
                if isinstance(res, tuple) and len(res) == 2:
                    ok, msg = bool(res[0]), str(res[1])
                else:
                    ok, msg = bool(res), str(res)
            except Exception as e:
                ok, msg = False, str(e)
            self._test_done.emit(ns, ok, msg)

        threading.Thread(target=worker, daemon=True).start()

    def _on_test_done(self, ns: str, ok: bool, msg: str):
        lbl = self._status_labels.get(ns)
        if not lbl:
            return
        lbl.setText(msg)
        color = C.PRI if ok else "#ff6b6b"
        lbl.setStyleSheet(f"color: {color}; background: transparent;")


class RemoteKeyOverlay(QWidget):
    """Floating overlay — QR code for instant phone pairing + manual key fallback."""

    closed = pyqtSignal()

    _OW, _OH = 400, 465

    def __init__(self, url: str, key: str, auto_login_url: str = "",
                 manual_url: str = "", expiry_secs: int = 600, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            RemoteKeyOverlay {{
                background: rgba(1, 6, 3, 248);
                border: 1px solid {C.BORDER_B};
                border-radius: 2px;
            }}
        """)
        self._expiry          = time.time() + expiry_secs
        self._on_new_key      = None
        self._auto_login_url  = auto_login_url
        self._manual_url      = manual_url or url

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 16, 24, 16)
        lay.setSpacing(5)

        def _lbl(txt, fs=9, bold=False, color=C.PRI,
                 align=Qt.AlignmentFlag.AlignCenter):
            w = QLabel(txt)
            w.setAlignment(align)
            w.setFont(QFont(UI_FONT, fs,
                            QFont.Weight.Bold if bold else QFont.Weight.Normal))
            w.setStyleSheet(f"color: {color}; background: transparent;")
            w.setWordWrap(True)
            return w

        lay.addWidget(_lbl("◈  REMOTE ACCESS", 12, True))
        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER}; margin: 1px 0;")
        lay.addWidget(sep)

        # ── QR code ───────────────────────────────────────────────────────────
        self._qr_label = QLabel()
        self._qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._qr_label.setFixedSize(176, 176)
        self._qr_label.setStyleSheet(
            "background: white; border-radius: 10px; padding: 4px;"
        )
        qr_row = QHBoxLayout()
        qr_row.addStretch()
        qr_row.addWidget(self._qr_label)
        qr_row.addStretch()
        lay.addLayout(qr_row)

        self._update_qr(auto_login_url)

        lay.addWidget(_lbl("Scan with phone camera to connect instantly", 8, color=C.TEXT_DIM))

        sep2 = QFrame(); sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet(f"color: {C.BORDER}; margin: 1px 0;")
        lay.addWidget(sep2)

        lay.addWidget(_lbl("Or enter manually:", 7, color=C.TEXT_DIM,
                           align=Qt.AlignmentFlag.AlignLeft))

        self._url_lbl = QLabel(self._manual_url)
        self._url_lbl.setFont(QFont(UI_FONT, 8))
        self._url_lbl.setStyleSheet(f"color: {C.PRI_DIM}; background: transparent;")
        self._url_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._url_lbl.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(self._url_lbl)

        self._key_lbl = QLabel(key)
        self._key_lbl.setFont(QFont(UI_FONT, 28, QFont.Weight.Bold))
        self._key_lbl.setStyleSheet(f"""
            color: {C.ACC};
            background: {C.PANEL2};
            border: 1px solid {C.BORDER_B};
            border-radius: 8px;
            padding: 6px 4px;
            letter-spacing: 10px;
        """)
        self._key_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self._key_lbl)

        self._timer_lbl = QLabel()
        self._timer_lbl.setFont(QFont(UI_FONT, 8))
        self._timer_lbl.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
        self._timer_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self._timer_lbl)

        btn_row = QHBoxLayout(); btn_row.setSpacing(8)
        new_btn = QPushButton("NEW KEY")
        new_btn.setFixedHeight(32)
        new_btn.setFont(QFont(UI_FONT, 8, QFont.Weight.Bold))
        new_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        new_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C.PANEL}; color: {C.PRI};
                border: 1px solid {C.PRI_DIM}; border-radius: 5px;
            }}
            QPushButton:hover {{ background: {C.PRI_GHO}; border: 1px solid {C.PRI}; }}
        """)
        new_btn.clicked.connect(self._refresh_key)
        btn_row.addWidget(new_btn)

        close_btn = QPushButton("DISMISS")
        close_btn.setFixedHeight(32)
        close_btn.setFont(QFont(UI_FONT, 8, QFont.Weight.Bold))
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 5px;
            }}
            QPushButton:hover {{ color: {C.TEXT}; border: 1px solid {C.BORDER_B}; }}
        """)
        close_btn.clicked.connect(self._do_close)
        btn_row.addWidget(close_btn)
        lay.addLayout(btn_row)

        self._ctimer = QTimer(self)
        self._ctimer.timeout.connect(self._tick)
        self._ctimer.start(1000)
        self._tick()

    def set_new_key_callback(self, fn) -> None:
        self._on_new_key = fn

    def _update_qr(self, url: str) -> None:
        if not url:
            self._qr_label.setText("—")
            return
        try:
            import qrcode as _qrmod
            from io import BytesIO
            qr = _qrmod.QRCode(
                box_size=5, border=2,
                error_correction=_qrmod.constants.ERROR_CORRECT_M,
            )
            qr.add_data(url)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            buf = BytesIO()
            img.save(buf, format="PNG")
            px = QPixmap()
            px.loadFromData(buf.getvalue())
            self._qr_label.setPixmap(
                px.scaled(170, 170,
                          Qt.AspectRatioMode.KeepAspectRatio,
                          Qt.TransformationMode.SmoothTransformation)
            )
        except ImportError:
            self._qr_label.setText("pip install\nqrcode[pil]")
            self._qr_label.setFont(QFont(UI_FONT, 8))
            self._qr_label.setStyleSheet(
                "color: #888; background: white; border-radius: 10px; padding: 4px;"
            )
        except Exception:
            self._qr_label.setText(url[:28])
            self._qr_label.setFont(QFont(UI_FONT, 7))
            self._qr_label.setStyleSheet(
                f"color: {C.PRI}; background: white; border-radius: 10px; padding: 4px;"
            )

    def _tick(self):
        remaining = max(0, int(self._expiry - time.time()))
        m, s = divmod(remaining, 60)
        self._timer_lbl.setText(f"Key expires in  {m:02d}:{s:02d}")
        if remaining == 0:
            self._do_close()

    def mark_connected(self) -> None:
        """Call from any thread when a phone successfully connects."""
        self._ctimer.stop()
        self._key_lbl.setText("CONNECTED")
        self._key_lbl.setStyleSheet(f"""
            color: {C.GREEN};
            background: rgba(34,197,94,0.08);
            border: 2px solid rgba(34,197,94,0.4);
            border-radius: 8px;
            padding: 6px 4px;
            letter-spacing: 4px;
        """)
        self._qr_label.setText("✓")
        self._qr_label.setFont(QFont(UI_FONT, 54, QFont.Weight.Bold))
        self._qr_label.setStyleSheet(
            "color: #00ff88; background: #001a0d; border-radius: 10px;"
        )
        self._timer_lbl.setText("Phone connected — ORI ready")
        self._timer_lbl.setStyleSheet(f"color: {C.GREEN}; background: transparent;")

    def _refresh_key(self):
        if self._on_new_key:
            result = self._on_new_key()
            if result:
                url    = result[0]
                key    = result[1]
                auto   = result[2] if len(result) >= 3 else ""
                manual = result[3] if len(result) >= 4 else url
                self._manual_url     = manual or url
                self._url_lbl.setText(self._manual_url)
                self._key_lbl.setText(key)
                self._auto_login_url = auto
                self._update_qr(auto or url)
                self._expiry = time.time() + 600
                self._key_lbl.setStyleSheet(f"""
                    color: {C.ACC};
                    background: {C.PANEL2};
                    border: 1px solid {C.BORDER_B};
                    border-radius: 8px;
                    padding: 6px 4px;
                    letter-spacing: 10px;
                """)
                self._timer_lbl.setStyleSheet(
                    f"color: {C.TEXT_MED}; background: transparent;"
                )
                self._ctimer.start(1000)
                self._tick()

    def _do_close(self):
        self._ctimer.stop()
        self.hide()
        self.closed.emit()


class MainWindow(QMainWindow):
    _log_sig        = pyqtSignal(str)
    _state_sig      = pyqtSignal(str)
    _content_sig    = pyqtSignal(str, str)   # (title, text) — thread-safe content display
    _reconfig_sig   = pyqtSignal()           # trigger setup overlay from any thread
    _camera_sig     = pyqtSignal(bytes)      # show camera frame preview (small overlay)
    _cam_stream_sig = pyqtSignal(bool)       # True=start live stream, False=stop
    _cam_frame_sig  = pyqtSignal(bytes)      # live camera frame → HUD area
    _video_open_sig  = pyqtSignal(str, str, bool, str)  # video, title, muted, audio
    _wake_btns_sig   = pyqtSignal()          # wake state resolved off-thread
    _video_close_sig = pyqtSignal()
    _video_mute_sig  = pyqtSignal(bool)
    _clipboard_sig  = pyqtSignal(str)        # clipboard text changed (thread-safe)
    _confirm_sig    = pyqtSignal(str, str)   # (title, detail) — irreversible-action gate
    _confirm_hide_sig = pyqtSignal()
    _wake_dl_sig    = pyqtSignal(bool, str)  # wake-word install finished (ok, message)
    _quiz_sig       = pyqtSignal(str, object, object)  # (topic, questions, grader)
    _quiz_hide_sig  = pyqtSignal()
    _review_sig     = pyqtSignal(str, str, object, object)  # document review payload
    _local_mode_sig = pyqtSignal()              # legacy local text-mode presentation
    _audio_choices_sig = pyqtSignal(object, object)
    _plugin_test_done_sig = pyqtSignal(str, bool, str)
    _gemini_key_test_sig = pyqtSignal(str, bool, str)
    _weather_result_sig = pyqtSignal(object)  # thread-safe weather/location result
    _location_access_sig = pyqtSignal(object)  # WinRT callback marshalled to Qt UI thread
    _location_weather_sig = pyqtSignal(object)  # reverse-geocode/weather worker result
    _remote_status_sig = pyqtSignal(str, bool, str)  # dashboard state + startup detail
    _remote_connected_sig = pyqtSignal()         # phone pairing from runtime thread
    _remote_mute_sig = pyqtSignal(bool)           # phone-controlled PC microphone mute
    _access_sig = pyqtSignal(str, bool)            # live microphone/screen/keyboard/speaker access
    _app_update_check_sig = pyqtSignal(object)
    _app_update_download_sig = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self._local_mode_sig.connect(self._apply_local_mode)
        self._remote_status_sig.connect(self._apply_remote_settings_status)
        self._remote_connected_sig.connect(self._apply_phone_connected)
        self._remote_mute_sig.connect(self._set_muted)
        self._access_sig.connect(self._apply_access_indicator)
        self._app_update_check_sig.connect(self._apply_app_update_check)
        self._app_update_download_sig.connect(self._apply_app_update_download)
        self._access_labels: dict[str, QLabel] = {}
        self._access_active: set[str] = set()
        self._access_blink_phase = True
        self._access_blink_timer = QTimer(self)
        self._access_blink_timer.timeout.connect(self._tick_access_indicators)
        self._access_blink_timer.start(420)

        # Load customization from config
        _cfg = _read_full_config()
        # Canonical product identity is code-controlled; stale preference values are ignored.
        self._assistant_name: str = "ORI"
        _display = self._assistant_name.upper()

        # Apply the saved UI colour BEFORE panels/stylesheets are built
        _ui_color = (_cfg.get("ui_color") or "").strip()
        _allowed_accents = {"#43ff91", "#ffc35a", "#b6ffd0"}
        if _ui_color.lower() in _allowed_accents and _ui_color.lower() != DEFAULT_UI_COLOR:
            apply_ui_accent(_ui_color)

        self.setWindowTitle(f"{_display} — {APP_VERSION}")
        self.setMinimumSize(_MIN_W, _MIN_H)
        self.resize(_DEFAULT_W, _DEFAULT_H)

        screen = QApplication.primaryScreen().availableGeometry()
        self.move(
            (screen.width()  - _DEFAULT_W) // 2,
            (screen.height() - _DEFAULT_H) // 2,
        )

        self.on_text_command   = None
        self.on_remote_clicked = None   # callable: () -> (url, key) | None
        self.on_interrupt      = None   # callable: () -> None — stop ORI mid-speech
        self.on_voice_change   = None   # callable: () -> None — rebuild session with new voice
        self.on_audio_device_change = None  # callable: () -> None — reopen audio streams
        self.on_api_key_change = None       # callable: reconnect Gemini Live after key update
        self._confirm_overlay  = None   # live ConfirmBanner, if one is on screen
        self.get_plugins       = None   # callable: () -> list[dict], set by JarvisLive
        self.get_plugin_settings = None # callable: () -> list[dict] settings schemas, set by JarvisLive
        self.on_wake_toggle    = None   # callable: (enable: bool) -> str, set by JarvisLive
        self.on_wake_manual    = None   # callable: () -> None — manual sleep/wake
        self.on_push_to_talk   = None   # callable: (enable: bool) -> str scope
        self.ptt_hold          = None   # callable: (held: bool) -> None — windowed chord
        self.wake_get_state    = None   # callable: () -> dict {enabled, awake, ready}
        self._muted            = False
        self._current_file: str | None = None
        self._remote_overlay: RemoteKeyOverlay | None = None
        self._customize_overlay: CustomizeOverlay | None = None
        self._remote_status_detail = "Dashboard is starting…"
        self._remote_dashboard_running = False

        central = Backdrop()
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self._build_header()      # legacy drawer handles remain hidden for compatibility
        root.addWidget(self._build_top_bar())

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        self._left_panel = self._build_left_panel()
        self._left_panel.hide()  # navigation consolidated to the single Settings button

        # Center column: HUD + resizable content panel via QSplitter
        self.hud = HudCanvas(_display)
        self.hud.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._build_home_card()
        self._content_panel = self._build_content_panel()
        self._quiz_panel = self._build_quiz_panel()

        # Live camera container — replaces HUD when camera stream is active
        _cam_cont = QWidget()
        _cam_cont.setStyleSheet("background: #000308;")
        _cam_v = QVBoxLayout(_cam_cont)
        _cam_v.setContentsMargins(0, 0, 0, 0)
        _cam_v.setSpacing(0)
        _cam_hdr = QHBoxLayout()
        _cam_hdr.setContentsMargins(8, 5, 8, 5)
        _cam_title = QLabel("◈  CAMERA FEED")
        _cam_title.setFont(QFont(UI_FONT, 8, QFont.Weight.Bold))
        _cam_title.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        _cam_hdr.addWidget(_cam_title)
        _cam_hdr.addStretch()
        _cam_x = QPushButton("✕  CLOSE")
        _cam_x.setFont(QFont(UI_FONT, 8, QFont.Weight.Bold))
        _cam_x.setCursor(Qt.CursorShape.PointingHandCursor)
        _cam_x.setStyleSheet(f"""
            QPushButton {{
                color: {C.TEXT_DIM}; background: transparent;
                border: none; padding: 2px 6px;
            }}
            QPushButton:hover {{ color: {C.PRI}; }}
        """)
        _cam_x.clicked.connect(self.stop_camera_stream)
        _cam_hdr.addWidget(_cam_x)
        _cam_v.addLayout(_cam_hdr)
        self._cam_live_lbl = QLabel()
        self._cam_live_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._cam_live_lbl.setStyleSheet("background: transparent;")
        self._cam_live_lbl.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        _cam_v.addWidget(self._cam_live_lbl, stretch=1)

        # Video surface shares the same central stack as the waveform and camera.
        self._video_split = False        # is the sound a separate stream?
        self._video_auto_muted = False   # did ORI close the mic, or the user?
        # A plain flag rather than reading the widget. video_is_playing() is
        # called from plugin threads, and reading a widget's state from one is
        # not something to rely on; an attribute is.
        self._video_on = False
        self._video_cont = QWidget()
        self._video_cont.setStyleSheet(f"background: {C.BG};")
        _vid_v = QVBoxLayout(self._video_cont)
        _vid_v.setContentsMargins(8, 6, 8, 8)
        _vid_v.setSpacing(4)

        _vid_hdr = QHBoxLayout()
        self._video_title = QLabel("▶  VIDEO")
        self._video_title.setFont(QFont(UI_FONT, 9, QFont.Weight.Bold))
        self._video_title.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        _vid_hdr.addWidget(self._video_title)
        _vid_hdr.addStretch()

        def _vid_btn(text: str) -> QPushButton:
            b = QPushButton(text)
            b.setFont(QFont(UI_FONT, 8, QFont.Weight.Bold))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(f"""
                QPushButton {{
                    color: {C.TEXT_DIM}; background: transparent;
                    border: none; padding: 2px 6px;
                }}
                QPushButton:hover {{ color: {C.PRI}; }}
            """)
            return b

        # Muted is the default and the button says so, because a soundtrack
        # talking over ORI is the one way this feature could make the
        # assistant worse rather than better.
        self._video_mute_btn = _vid_btn("🔇  SOUND OFF")
        self._video_mute_btn.clicked.connect(self._toggle_video_mute)
        _vid_hdr.addWidget(self._video_mute_btn)

        _vid_x = _vid_btn("✕  CLOSE")
        _vid_x.clicked.connect(self.stop_video)
        _vid_hdr.addWidget(_vid_x)
        _vid_v.addLayout(_vid_hdr)

        if HAVE_VIDEO:
            # A GRAPHICS ITEM, NOT A QVideoWidget.
            #
            # QVideoWidget gets a native window of its own, and a native window
            # is painted by the compositor above every ordinary widget that
            # shares the screen with it — so the settings drawer opened
            # *underneath* the video and raise_() could not help, because the
            # two are not in the same painting order at all. A video item drawn
            # into a QGraphicsView goes through Qt's own painter like any other
            # widget, and anything laid over it stays over it.
            self._video_scene = QGraphicsScene(self)
            self._video_item = QGraphicsVideoItem()
            self._video_scene.addItem(self._video_item)
            self._video_widget = QGraphicsView(self._video_scene)
            self._video_widget.setStyleSheet("background: #000; border: none;")
            self._video_widget.setFrameShape(QGraphicsView.Shape.NoFrame)
            self._video_widget.setHorizontalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self._video_widget.setVerticalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self._video_widget.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
            )
            _vid_v.addWidget(self._video_widget, stretch=1)

            self._video_audio = QAudioOutput()
            self._video_audio.setMuted(True)
            self._video_player = QMediaPlayer()
            self._video_player.setVideoOutput(self._video_item)
            # Keep the picture filling the view as the window is resized.
            self._video_item.nativeSizeChanged.connect(self._fit_video)
            self._video_player.setAudioOutput(self._video_audio)
            self._video_player.errorOccurred.connect(self._on_video_error)

            # A SECOND player, for sound that arrives separately.
            #
            # YouTube no longer serves a single stream carrying both picture and
            # sound — not for new uploads and not for old ones; checked against
            # three videos including the oldest on the site, and every one of
            # them offered zero combined formats. Picture and sound are two
            # URLs, so they are two players, started together and nudged back
            # into line by the timer below.
            #
            # A local file or a direct video URL still uses the first player
            # alone: one stream, one player, nothing to synchronise.
            self._video_sound = QMediaPlayer()
            self._video_sound_out = QAudioOutput()
            self._video_sound_out.setMuted(True)
            self._video_sound.setAudioOutput(self._video_sound_out)
            self._video_sound.errorOccurred.connect(self._on_video_error)

            self._video_sync = QTimer(self)
            self._video_sync.setInterval(1000)
            self._video_sync.timeout.connect(self._sync_video_sound)
        else:
            self._video_scene = None
            self._video_item = None
            self._video_widget = None
            self._video_player = None
            self._video_audio = None
            self._video_sound = None
            self._video_sound_out = None
            self._video_sync = None
            _miss = QLabel("Video playback is not available in this Qt install.")
            _miss.setAlignment(Qt.AlignmentFlag.AlignCenter)
            _miss.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
            _vid_v.addWidget(_miss, stretch=1)

        # Stack: 0 = waveform, 1 = live camera, 2 = video
        self._hud_cam_stack = QStackedWidget()
        self._hud_cam_stack.addWidget(self.hud)
        self._hud_cam_stack.addWidget(_cam_cont)
        self._hud_cam_stack.addWidget(self._video_cont)

        self._center_split = QSplitter(Qt.Orientation.Vertical)
        self._center_split.setStyleSheet(f"""
            QSplitter::handle {{
                background: {C.BORDER};
                height: 4px;
            }}
            QSplitter::handle:hover {{
                background: {C.PRI_DIM};
            }}
        """)
        self._center_split.addWidget(self._hud_cam_stack)
        self._center_split.addWidget(self._content_panel)
        self._center_split.addWidget(self._quiz_panel)
        self._center_split.setStretchFactor(0, 3)
        self._center_split.setStretchFactor(1, 1)
        self._center_split.setCollapsible(0, False)
        _center_col = QWidget()
        _cc = QVBoxLayout(_center_col)
        _cc.setContentsMargins(0, 0, 0, 0)
        _cc.setSpacing(0)
        _cc.addWidget(self._center_split, stretch=1)
        body.addWidget(_center_col, stretch=1)

        self._right_panel = self._build_right_panel()
        self._right_panel.hide()  # file picker/activity log no longer crowd the HUD

        self._home_page = QWidget()
        home_layout = QVBoxLayout(self._home_page)
        home_layout.setContentsMargins(0, 0, 0, 0)
        home_layout.setSpacing(0)
        home_layout.addLayout(body, stretch=1)
        home_layout.addWidget(self._build_input_bar())
        home_layout.addWidget(self._build_footer())

        self._page_stack = QStackedWidget()
        self._page_stack.addWidget(self._home_page)
        self._settings_page = self._build_settings_page()
        self._page_stack.addWidget(self._settings_page)
        self._page_stack.setCurrentWidget(self._home_page)
        root.addWidget(self._page_stack, stretch=1)

        # Quick-access drawer (floating overlay, built after central widget layout is done)
        self._quick_drawer = self._build_quick_drawer()
        self._ctrl_drawer = self._build_controls_drawer()
        self._warm_wake_state()
        self._update_autostart_btn(self._check_autostart())
        from memory.config_manager import get_brief_enabled as _gbe
        self._update_brief_btn(_gbe())

        self._clock_tmr = QTimer(self)
        self._clock_tmr.timeout.connect(self._tick_clock)
        self._clock_tmr.start(1000)
        self._tick_clock()

        # Metric update timer
        self._metric_tmr = QTimer(self)
        self._metric_tmr.timeout.connect(self._update_metrics)
        self._metric_tmr.start(2000)
        self._update_metrics()

        self._log_sig.connect(self._log.append_log)
        self._state_sig.connect(self._apply_state)
        self._content_sig.connect(self._show_content)
        self._reconfig_sig.connect(self._show_setup)
        self._camera_sig.connect(self._show_camera_frame)
        self._confirm_sig.connect(self._show_confirm_banner)
        self._confirm_hide_sig.connect(self._hide_confirm_banner)
        self._cam_stream_sig.connect(self._on_cam_stream)
        self._cam_frame_sig.connect(self._on_cam_frame)
        self._wake_btns_sig.connect(self._refresh_wake_btns)
        self._video_open_sig.connect(self._on_video_open)
        self._video_close_sig.connect(self._on_video_close)
        self._video_mute_sig.connect(self._on_video_mute)
        self._clipboard_sig.connect(self._show_clipboard_panel)
        self._wake_dl_sig.connect(self._on_wake_install_done)
        self._quiz_sig.connect(self._show_quiz)
        self._quiz_hide_sig.connect(self._hide_quiz)
        self._review_sig.connect(self._show_review)
        self._audio_choices_sig.connect(self._populate_audio_choices)
        self._plugin_test_done_sig.connect(self._on_plugin_test_done)
        self._gemini_key_test_sig.connect(self._on_gemini_key_test_done)
        self._weather_result_sig.connect(self._on_weather_result)
        self._location_access_sig.connect(self._on_device_location_result)
        self._location_weather_sig.connect(self._on_location_weather_result)
        self._location_request_inflight = False
        self._location_generation = 0
        self._weather_busy = False
        self._weather_generation = 0
        self._cam_stop = threading.Event()

        # Camera preview overlay (child of central widget, positioned in resizeEvent)
        self._cam_preview = _CameraPreview(self.centralWidget())

        # Clipboard panel (child of central widget, bottom-center)
        self._clipboard_panel = ClipboardPanel(self.centralWidget())
        self._clipboard_panel.action_requested.connect(self._on_clipboard_action)
        QApplication.clipboard().dataChanged.connect(self._on_clipboard_changed)

        self._overlay: SetupOverlay | None = None
        self._ready = self._check_config()
        if not self._ready:
            self._show_setup()

        QTimer.singleShot(0, self._apply_win_chrome)

        sc_mute = QShortcut(QKeySequence("F4"), self)
        sc_mute.activated.connect(self._toggle_mute)
        sc_full = QShortcut(QKeySequence("F11"), self)
        sc_full.activated.connect(self._toggle_fullscreen)
        sc_intr = QShortcut(QKeySequence("Escape"), self)
        sc_intr.activated.connect(self._do_interrupt)
        sc_settings = QShortcut(QKeySequence("Ctrl+,"), self)
        sc_settings.activated.connect(self._toggle_settings_page)

        # Weather is explicitly opt-in. If a user previously enabled it, reuse
        # the saved coarse/manual area and refresh weather without resolving IP
        # location again on each launch.
        self._weather_refresh_timer = QTimer(self)
        self._weather_refresh_timer.timeout.connect(self._refresh_saved_weather)
        self._weather_refresh_timer.start(15 * 60 * 1000)
        QTimer.singleShot(1400, self._refresh_weather_if_enabled)
        QTimer.singleShot(2400, self._maybe_prompt_startup_location)

    def _show_camera_frame(self, img_bytes: bytes):
        """Slot — display camera preview overlay (main thread)."""
        self._cam_preview.show_frame(img_bytes)
        cw = self.centralWidget()
        pw = _CameraPreview._W
        ph = self._cam_preview.height()
        self._cam_preview.setGeometry(
            cw.width() - _RIGHT_W - pw - 12,
            cw.height() - ph - 28,
            pw, ph,
        )

    # --- Live camera stream in HUD area ------------------------------------
    def _on_cam_stream(self, start: bool) -> None:
        if start:
            self._hud_cam_stack.setCurrentIndex(1)
        else:
            self._hud_cam_stack.setCurrentIndex(0)
            self._cam_live_lbl.clear()

    def _on_cam_frame(self, data: bytes) -> None:
        px = QPixmap()
        px.loadFromData(data)
        if not px.isNull():
            w, h = self._cam_live_lbl.width(), self._cam_live_lbl.height()
            if w > 1 and h > 1:
                self._cam_live_lbl.setPixmap(
                    px.scaled(w, h,
                              Qt.AspectRatioMode.KeepAspectRatio,
                              Qt.TransformationMode.SmoothTransformation)
                )

    def start_camera_stream(self) -> None:
        self._cam_stop.clear()
        self._cam_stream_sig.emit(True)
        t = threading.Thread(target=self._cam_loop, daemon=True, name="cam-stream")
        t.start()

    def _cam_loop(self) -> None:
        try:
            import cv2
            # Reuse camera index detected by screen_processor (cached in api_keys.json)
            cam_idx = 0
            try:
                import json as _j
                cfg = _j.loads((CONFIG_DIR / "api_keys.json").read_text())
                cam_idx = int(cfg.get("camera_index", 0))
            except Exception:
                pass
            try:
                backend = cv2.CAP_DSHOW if _OS == "Windows" else cv2.CAP_ANY
            except AttributeError:
                backend = 0
            cap = cv2.VideoCapture(cam_idx, backend)
            if not cap.isOpened():
                cap = cv2.VideoCapture(0)
            if not cap.isOpened():
                return
            # warm-up frames
            for _ in range(5):
                cap.read()
            while not self._cam_stop.wait(0.033) and cap.isOpened():
                ret, frame = cap.read()
                if ret and frame is not None:
                    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 65])
                    self._cam_frame_sig.emit(buf.tobytes())
            cap.release()
        except Exception as e:
            print(f"[Camera] Stream error: {e}")
        finally:
            self._cam_stream_sig.emit(False)

    def stop_camera_stream(self) -> None:
        self._cam_stop.set()

    # --- Video in the HUD area ---------------------------------------------
    #
    # Everything below runs on the Qt thread. Plugins and the assistant reach it
    # through the signals above, the same way every other panel is driven, so a
    # background thread never touches a widget.
    def _reset_video_players(self) -> None:
        """Stop and clear both media players before reusing them.

        Back-to-back songs were reusing the same Qt media objects without first
        clearing the previous transport. That is a reliable way to accumulate
        stale state across one or two tracks, especially when the picture and
        soundtrack are separate streams, and it matches the reported crash shape.
        """
        if self._video_sync:
            self._video_sync.stop()
        for p in (self._video_player, self._video_sound):
            if p:
                try:
                    p.stop()
                except Exception:
                    pass
                try:
                    p.setSource(QUrl())
                except Exception:
                    pass

    def _on_video_open(self, source: str, title: str, muted: bool,
                       audio_source: str = "") -> None:
        if not HAVE_VIDEO or not self._video_player:
            self.write_log("SYS: Video playback is not available in this Qt "
                           "install.")
            return
        # A video and the live camera cannot share the centre of the HUD.
        self._cam_stop.set()
        self._reset_video_players()

        self._video_title.setText(f"▶  {(title or 'VIDEO')[:44].upper()}")
        self._video_split = bool(audio_source)
        self._set_video_muted(bool(muted))

        url = (QUrl.fromLocalFile(source) if Path(source).exists()
               else QUrl(source))
        self._video_player.setSource(url)
        if self._video_split:
            self._video_sound.setSource(QUrl(audio_source))
        else:
            self._video_sound.setSource(QUrl())
        self._hud_cam_stack.setCurrentIndex(2)
        self._video_on = True
        # Re-run now that the video counts as playing: _set_video_muted ran
        # before this line and saw no video, so its mic check was a no-op.
        self._sync_mic_for_video()
        self._video_player.play()
        if self._video_split:
            self._video_sound.play()
            self._video_sync.start()

    def _fit_video(self, *_a) -> None:
        """Size the picture to the panel, keeping its shape."""
        if not (self._video_item and self._video_widget):
            return
        try:
            native = self._video_item.nativeSize()
            if native.isEmpty():
                return
            view = self._video_widget.viewport().size()
            scale = min(view.width() / native.width(),
                        view.height() / native.height())
            w, h = native.width() * scale, native.height() * scale
            self._video_item.setSize(QSizeF(w, h))
            self._video_scene.setSceneRect(0, 0, w, h)
            self._video_widget.centerOn(self._video_item)
        except Exception:
            pass

    def _on_video_close(self) -> None:
        self._reset_video_players()
        self._video_split = False
        self._video_on = False
        self._hud_cam_stack.setCurrentIndex(0)
        self._sync_mic_for_video()      # gives the microphone back

    def _set_video_muted(self, muted: bool) -> None:
        """Silence whichever output is carrying the sound for this video."""
        muted = bool(muted)
        if self._video_audio:
            # When the sound is a separate stream this player has none, but
            # muting it too costs nothing and keeps the two paths identical.
            self._video_audio.setMuted(muted)
        if self._video_sound_out:
            self._video_sound_out.setMuted(muted)
        self._sync_video_mute_btn()
        self._sync_mic_for_video()

    def _on_video_mute(self, muted: bool) -> None:
        self._set_video_muted(muted)

    def _sync_mic_for_video(self) -> None:
        """Close the microphone while the video is making sound.

        ORI subtracts its OWN output from the microphone — that is what
        core/echo.py does — but a video plays through a different output
        entirely, so the guard has never heard of it and the assistant answers
        the film. There is no arrangement in which an open microphone and a
        loudspeaker in the same room do not do that.

        So the microphone closes for exactly as long as the sound is on, and
        opens again by itself the moment it goes off or the video is closed.
        Only if ORI closed it: a microphone the user muted themselves stays
        muted, and pressing the mute key during a video hands the decision back
        to them for good.
        """
        sound_on = bool(self._video_on and self._video_sound_out
                        and not self._video_sound_out.isMuted())
        if sound_on and not self._muted:
            self._video_auto_muted = True
            self._set_muted(True, "The video's sound is on — silence it, close "
                                  "it, or press F4 to talk. Typing still works.")
        elif not sound_on and self._video_auto_muted:
            self._video_auto_muted = False
            self._set_muted(False, "The video is quiet again.")

    def _sync_video_sound(self) -> None:
        """Keep the separate soundtrack in step with the picture.

        Two players started at the same moment do not stay together: they buffer
        independently, and measured on a real stream they were about half a
        second apart after nine seconds. So the sound is nudged back to the
        picture whenever it drifts far enough to hear — and only then, because
        correcting a smaller gap is itself audible.
        """
        if not (self._video_split and self._video_sound and self._video_player):
            return
        try:
            if self._video_player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
                return
            drift = self._video_sound.position() - self._video_player.position()
            if abs(drift) > 300:
                self._video_sound.setPosition(self._video_player.position())
        except Exception:
            pass

    def _sync_video_mute_btn(self) -> None:
        out = self._video_sound_out if self._video_split else self._video_audio
        muted = bool(out and out.isMuted())
        self._video_mute_btn.setText("🔇  SOUND OFF" if muted else "🔊  SOUND ON")

    def _toggle_video_mute(self) -> None:
        out = self._video_sound_out if self._video_split else self._video_audio
        if out:
            self._set_video_muted(not out.isMuted())

    def _on_video_error(self, *_a) -> None:
        err = ""
        try:
            errs = []
            if self._video_player:
                e = self._video_player.errorString()
                if e:
                    errs.append(e)
            if self._video_sound:
                e = self._video_sound.errorString()
                if e and e not in errs:
                    errs.append(e)
            err = " | ".join(errs)
        except Exception:
            pass
        self.write_log(f"SYS: The video could not be played{(' — ' + err) if err else ''}.")
        self._on_video_close()

    def stop_video(self) -> None:
        self._video_close_sig.emit()

    def video_is_playing(self) -> bool:
        return bool(self._video_on)

    # ------------------------------------------------------------------
    # Icon generation — terminal waveform style, rendered with Pillow
    # ------------------------------------------------------------------
    @staticmethod
    def _build_ori_icon(out_path: Path) -> bool:
        """Render a crisp multi-resolution ORI waveform icon without an orb/face."""
        try:
            import PIL.Image
            import PIL.ImageDraw
            import PIL.ImageFilter
        except ImportError:
            return False

        GREEN = (67, 255, 145)
        DARK = (4, 10, 8)
        EDGE = (39, 107, 75)

        def _render(sz: int) -> PIL.Image.Image:
            S = sz * 4
            img = PIL.Image.new("RGBA", (S, S), (0, 0, 0, 0))
            d = PIL.ImageDraw.Draw(img)
            margin = int(S * 0.055)
            radius = int(S * 0.16)
            d.rounded_rectangle(
                [margin, margin, S - margin, S - margin],
                radius=radius, fill=(*DARK, 255), outline=(*EDGE, 240), width=max(1, S // 90),
            )

            cx, cy = S // 2, S // 2
            left, right = int(S * 0.19), int(S * 0.81)
            d.line([left, cy, right, cy], fill=(*GREEN, 75), width=max(1, S // 120))
            # A deliberate fixed waveform silhouette, not a live/random animation.
            heights = [0.10, 0.15, 0.22, 0.12, 0.27, 0.40, 0.24, 0.15,
                       0.32, 0.50, 0.72, 0.38, 0.25, 0.44, 0.30, 0.18,
                       0.12, 0.28, 0.44, 0.24, 0.15, 0.34, 0.56, 0.30,
                       0.18, 0.26, 0.14, 0.22, 0.12]
            xspan = right - left
            bar_w = max(2, int(S * 0.014))
            max_h = int(S * 0.25)
            points = []
            for i, val in enumerate(heights):
                x = left + int(i * xspan / (len(heights) - 1))
                h = max(2, int(val * max_h))
                points.append((x, cy - h, x, cy + h))
            glow = PIL.Image.new("RGBA", (S, S), (0, 0, 0, 0))
            gd = PIL.ImageDraw.Draw(glow)
            for x1, y1, x2, y2 in points:
                gd.rounded_rectangle(
                    [x1 - bar_w, y1, x2 + bar_w, y2], radius=bar_w,
                    fill=(*GREEN, 105),
                )
            glow = glow.filter(PIL.ImageFilter.GaussianBlur(max(1, S // 70)))
            img = PIL.Image.alpha_composite(img, glow)
            d = PIL.ImageDraw.Draw(img)
            for x1, y1, x2, y2 in points:
                d.rounded_rectangle(
                    [x1 - bar_w // 2, y1, x2 + bar_w // 2, y2], radius=max(1, bar_w // 2),
                    fill=(*GREEN, 255),
                )
            return img.resize((sz, sz), PIL.Image.Resampling.LANCZOS)

        try:
            sizes = [256, 128, 64, 48, 32, 16]
            frames = [_render(size) for size in sizes]
            frames[0].save(
                out_path, format="ICO", append_images=frames[1:],
                sizes=[(size, size) for size in sizes],
            )
            return True
        except Exception as exc:
            print(f"[Shortcut] Icon generation failed: {type(exc).__name__}: {exc}")
            return False

    @staticmethod
    def _create_lnk_windows(lnk: str, target: str, args: str,
                             work_dir: str, icon_loc: str) -> None:
        """
        Create a Windows .lnk shortcut WITHOUT launching PowerShell or cmd.
        Tries win32com (pywin32) first; falls back to wscript.exe + VBScript.
        wscript.exe is a GUI-mode host — it never opens a console window.
        """
        # ── Option 1: pywin32 (pure Python COM, zero subprocess) ──────────
        try:
            from win32com.client import Dispatch   # type: ignore
            sh = Dispatch("WScript.Shell")
            sc = sh.CreateShortCut(lnk)
            sc.TargetPath       = target
            sc.Arguments        = f'"{args}"'
            sc.WorkingDirectory = work_dir
            sc.Description      = "ORI AI Assistant"
            sc.IconLocation     = icon_loc
            sc.save()
            return
        except ImportError:
            pass

        # ── Option 2: wscript.exe + VBScript (always available on Windows,
        #    GUI-mode executable — never opens a console window) ────────────
        vbs = "\n".join([
            'Set ws = CreateObject("WScript.Shell")',
            f'Set sc = ws.CreateShortcut("{lnk}")',
            f'sc.TargetPath = "{target}"',
            f'sc.Arguments = Chr(34) & "{args}" & Chr(34)',
            f'sc.WorkingDirectory = "{work_dir}"',
            'sc.Description = "ORI AI Assistant"',
            f'sc.IconLocation = "{icon_loc}"',
            'sc.Save',
        ])
        import tempfile
        fd, tmp = tempfile.mkstemp(suffix=".vbs")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(vbs)
            proc = subprocess.Popen(
                ["wscript.exe", "/nologo", tmp],
                creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW,
            )
            proc.wait(timeout=10)
        finally:
            try:
                os.unlink(tmp)
            except Exception:
                pass

    @staticmethod
    def _get_desktop_dir() -> Path:
        """
        Resolve the user's REAL desktop directory instead of assuming
        ~/Desktop, which breaks when:
          • OneDrive "Known Folder Move" relocates the desktop
            (C:/Users/x/OneDrive/Desktop) — very common on Win 10/11;
          • the XDG desktop is localized on Linux (~/Masaüstü,
            ~/Schreibtisch, ~/Bureau, …).
        Falls back to ~/Desktop only as a last resort.
        """
        home = Path.home()
        _os = platform.system()

        if _os == "Windows":
            # ── 1) SHGetKnownFolderPath(FOLDERID_Desktop) — the canonical
            #       answer; follows OneDrive redirection. No dependencies. ──
            try:
                import ctypes
                from ctypes import wintypes

                class _GUID(ctypes.Structure):
                    _fields_ = [("Data1", wintypes.DWORD),
                                ("Data2", wintypes.WORD),
                                ("Data3", wintypes.WORD),
                                ("Data4", ctypes.c_ubyte * 8)]

                # FOLDERID_Desktop {B4BFCC3A-DB2C-424C-B029-7FE99A87C641}
                fid = _GUID(0xB4BFCC3A, 0xDB2C, 0x424C,
                            (ctypes.c_ubyte * 8)(0xB0, 0x29, 0x7F, 0xE9,
                                                 0x9A, 0x87, 0xC6, 0x41))
                buf = ctypes.c_wchar_p()
                if ctypes.windll.shell32.SHGetKnownFolderPath(
                        ctypes.byref(fid), 0, None, ctypes.byref(buf)) == 0:
                    p = Path(buf.value)
                    ctypes.windll.ole32.CoTaskMemFree(buf)
                    if p.is_dir():
                        return p
            except Exception:
                pass

            # ── 2) Registry: User Shell Folders (may contain %VARS%) ──────
            try:
                import winreg
                with winreg.OpenKey(
                        winreg.HKEY_CURRENT_USER,
                        r"Software\Microsoft\Windows\CurrentVersion"
                        r"\Explorer\User Shell Folders") as key:
                    val, _t = winreg.QueryValueEx(key, "Desktop")
                p = Path(os.path.expandvars(val))
                if p.is_dir():
                    return p
            except Exception:
                pass

        elif _os == "Linux":
            # ── xdg-user-dir honours localized names (~/Masaüstü, …) ──────
            try:
                out = subprocess.run(["xdg-user-dir", "DESKTOP"],
                                     capture_output=True, text=True, timeout=5)
                p = Path(out.stdout.strip())
                if out.stdout.strip() and p != home and p.is_dir():
                    return p
            except Exception:
                pass
            try:
                cfg = home / ".config" / "user-dirs.dirs"
                for line in cfg.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line.startswith("XDG_DESKTOP_DIR"):
                        val = line.split("=", 1)[1].strip().strip('"')
                        p = Path(val.replace("$HOME", str(home)))
                        if p != home and p.is_dir():
                            return p
            except Exception:
                pass

        # macOS: ~/Desktop is always the real path (localization is
        # display-only). Everything else lands here as a last resort.
        return home / "Desktop"

    def _create_desktop_shortcut(self):
        """
        Create a desktop shortcut on Windows / macOS / Linux.
        Never opens a terminal, console, or PowerShell window on any platform.
        """
        import stat as _stat
        script  = Path(__file__).resolve().parent / "main.py"
        python  = Path(sys.executable)
        desktop = self._get_desktop_dir()

        # Terminal-waveform icon (.ico)
        ico_path = Path(__file__).resolve().parent / "config" / "ori.ico"
        if not ico_path.exists():
            self._build_ori_icon(ico_path)

        try:
            _os = platform.system()

            # ── Windows ───────────────────────────────────────────────────────
            if _os == "Windows":
                pythonw  = python.parent / "pythonw.exe"
                target   = str(pythonw if pythonw.exists() else python)
                lnk      = str(desktop / "ORI.lnk")
                icon_loc = str(ico_path) if ico_path.exists() else f"{target},0"
                self._create_lnk_windows(lnk, target, str(script),
                                         str(script.parent), icon_loc)

            # ── macOS — proper .app bundle (no Terminal window) ───────────────
            elif _os == "Darwin":
                app     = desktop / "ORI.app"
                mac_dir = app / "Contents" / "MacOS"
                res_dir = app / "Contents" / "Resources"
                mac_dir.mkdir(parents=True, exist_ok=True)
                res_dir.mkdir(exist_ok=True)

                # Launcher executable (bash — runs as background process,
                # macOS does NOT open Terminal for executables inside .app bundles)
                launcher = mac_dir / "ORI"
                launcher.write_text(
                    "#!/usr/bin/env bash\n"
                    f'cd "{script.parent}"\n'
                    f'exec "{python}" "{script}"\n'
                )
                launcher.chmod(launcher.stat().st_mode
                               | _stat.S_IEXEC | _stat.S_IXGRP | _stat.S_IXOTH)

                # Minimal Info.plist (required for .app recognition)
                (app / "Contents" / "Info.plist").write_text(
                    '<?xml version="1.0" encoding="UTF-8"?>\n'
                    '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
                    '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
                    '<plist version="1.0"><dict>\n'
                    '  <key>CFBundleExecutable</key><string>ORI</string>\n'
                    '  <key>CFBundleIdentifier</key>'
                    '<string>com.jarvis.assistant</string>\n'
                    '  <key>CFBundleName</key><string>ORI</string>\n'
                    '  <key>CFBundlePackageType</key><string>APPL</string>\n'
                    '  <key>CFBundleVersion</key><string>1.0</string>\n'
                    '</dict></plist>\n'
                )

                # Optional: copy icon as .icns (skip silently if Pillow is missing)
                try:
                    import PIL.Image
                    icns = res_dir / "AppIcon.icns"
                    PIL.Image.open(ico_path).save(icns, format="ICNS")
                    # Inject icon reference into plist
                    plist = app / "Contents" / "Info.plist"
                    txt = plist.read_text()
                    plist.write_text(
                        txt.replace(
                            '</dict></plist>',
                            '  <key>CFBundleIconFile</key>'
                            '<string>AppIcon</string>\n</dict></plist>\n',
                        )
                    )
                except Exception:
                    pass  # icon is optional

            # ── Linux — .desktop file (Terminal=false, no console) ────────────
            else:
                # Export .ico → .png for better desktop integration
                png_path = ico_path.with_suffix(".png")
                if not png_path.exists() and ico_path.exists():
                    try:
                        import PIL.Image
                        PIL.Image.open(ico_path).resize(
                            (256, 256), PIL.Image.LANCZOS
                        ).save(png_path, format="PNG")
                    except Exception:
                        png_path = ico_path  # fallback to .ico

                icon_line = f"Icon={png_path}\n" if png_path.exists() else ""
                desk = desktop / "ORI.desktop"
                desk.write_text(
                    "[Desktop Entry]\n"
                    "Name=ORI\n"
                    f"Exec={python} {script}\n"
                    f"Path={script.parent}\n"
                    "Type=Application\n"
                    "Terminal=false\n"
                    "Categories=Utility;\n"
                    + icon_line
                )
                desk.chmod(desk.stat().st_mode | 0o755)

            self._log.append_log("SYS: Desktop shortcut created.")
        except Exception as e:
            self._log.append_log(f"ERR: Shortcut failed — {e}")

    def _toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cw = self.centralWidget()
        if self._overlay and self._overlay.isVisible():
            ow, oh = 560, 470
            self._overlay.setGeometry(
                (cw.width()  - ow) // 2,
                (cw.height() - oh) // 2,
                ow, oh,
            )
        if self._remote_overlay and self._remote_overlay.isVisible():
            ow, oh = RemoteKeyOverlay._OW, RemoteKeyOverlay._OH
            self._remote_overlay.setGeometry(
                (cw.width()  - ow) // 2,
                (cw.height() - oh) // 2,
                ow, oh,
            )
        if self._customize_overlay and self._customize_overlay.isVisible():
            ow, oh = CustomizeOverlay._OW, CustomizeOverlay._OH
            self._customize_overlay.setGeometry(
                (cw.width()  - ow) // 2,
                (cw.height() - oh) // 2,
                ow, oh,
            )
        # Camera preview — bottom-right corner of the center/HUD area
        pw = _CameraPreview._W
        ph = self._cam_preview.height() or _CameraPreview._H
        self._cam_preview.setGeometry(
            cw.width() - _RIGHT_W - pw - 12,
            cw.height() - ph - 28,
            pw, ph,
        )
        # Clipboard panel — bottom-center
        if hasattr(self, '_clipboard_panel') and self._clipboard_panel.isVisible():
            self._position_clipboard_panel()
        # Quick drawer — reposition if open
        if hasattr(self, '_quick_drawer') and self._quick_drawer.isVisible():
            self._position_quick_drawer()
        if hasattr(self, '_ctrl_drawer') and self._ctrl_drawer.isVisible():
            self._position_ctrl_drawer()
        self._fit_video()

    def _update_metrics(self):
        snap = _metrics.snapshot()

        # CPU
        cpu = snap["cpu"]
        self._bar_cpu.set_value(cpu, f"{cpu:.0f}%")
        if hasattr(self, "_top_cpu_lbl"):
            self._top_cpu_lbl.set_metric(
                cpu, f"{cpu:.0f}%", getattr(self, "_metrics_display_mode", "both"),
                tooltip=f"System-wide CPU utilisation: {cpu:.1f}%",
            )

        # MEM
        mem = snap["mem"]
        self._bar_mem.set_value(mem, f"{mem:.0f}%")
        if hasattr(self, "_top_ram_lbl"):
            try:
                _vm = psutil.virtual_memory()
                _used_gb = _vm.used / (1024 ** 3)
                _total_gb = _vm.total / (1024 ** 3)
                _ram_tip = f"Physical RAM in use: {mem:.1f}% ({_used_gb:.1f}/{_total_gb:.1f} GB)"
            except Exception:
                _ram_tip = f"Physical RAM in use: {mem:.1f}%"
            self._top_ram_lbl.set_metric(
                mem, f"{mem:.0f}%", getattr(self, "_metrics_display_mode", "both"),
                tooltip=_ram_tip,
            )

        # NET
        net = snap["net"]
        if net < 1.0:
            net_str = f"{net*1024:.0f}KB/s"
        else:
            net_str = f"{net:.1f}MB/s"
        net_pct = min(100, net * 10)  # 10 MB/s = %100
        self._bar_net.set_value(net_pct, net_str)

        # GPU
        gpu = snap["gpu"]
        if gpu >= 0:
            self._bar_gpu.set_value(gpu, f"{gpu:.0f}%")
        else:
            self._bar_gpu.set_value(0, "N/A")

        # TMP
        tmp = snap["tmp"]
        if tmp >= 0:
            tmp_pct = min(100, (tmp / 100) * 100)
            self._bar_tmp.set_value(tmp_pct, f"{tmp:.0f}°C")
            if hasattr(self, "_top_temp_lbl"):
                self._top_temp_lbl.set_metric(
                    tmp, f"{tmp:.0f}°C", getattr(self, "_metrics_display_mode", "both"),
                    tooltip=f"CPU temperature: {tmp:.1f}°C",
                    max_value=110.0,
                    warning=tmp >= 90,
                )
        else:
            self._bar_tmp.set_value(0, "N/A")
            if hasattr(self, "_top_temp_lbl"):
                self._top_temp_lbl.set_metric(
                    None, "N/A", getattr(self, "_metrics_display_mode", "both"),
                    tooltip=(
                        "No confirmed CPU temperature sensor is exposed. On Windows, run "
                        "LibreHardwareMonitor with sensor support; ORI will not guess a temperature."
                    ),
                    max_value=110.0,
                )

        try:
            boot_t  = psutil.boot_time()
            elapsed = time.time() - boot_t
            h = int(elapsed // 3600)
            m = int((elapsed % 3600) // 60)
            self._uptime_lbl.setText(f"UP  {h:02d}:{m:02d}")
        except Exception:
            self._uptime_lbl.setText("UP  --:--")

        try:
            proc_count = len(psutil.pids())
            self._proc_lbl.setText(f"PROC  {proc_count}")
        except Exception:
            self._proc_lbl.setText("PROC  --")



    # ── Glass UI pieces ──────────────────────────────────────────────────────
    def _apply_win_chrome(self) -> None:
        if _OS != "Windows":
            return
        try:
            import ctypes
            hwnd = int(self.winId())
            dwm = ctypes.windll.dwmapi
            on = ctypes.c_int(1)
            dwm.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(on), ctypes.sizeof(on))  # dark title bar
            bg = QColor(C.BG)
            colorref = ctypes.c_int(bg.red() | (bg.green() << 8) | (bg.blue() << 16))
            dwm.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(colorref), ctypes.sizeof(colorref))  # Win11 caption
        except Exception:
            pass

    def _build_home_card(self) -> None:
        try:
            from memory.config_manager import get_user_name
            _user = get_user_name()
        except Exception:
            _user = ""
        card = HomeCard(_user, lambda: getattr(self.hud, "_amp_disp", 0.0), parent=self.hud)
        card.move(24, 24)
        card.hide()
        self._home_card = card
        # the metric names the update code already uses now point at the card
        self._bar_cpu = card.g_cpu
        self._bar_mem = card.g_ram
        self._bar_gpu = card.g_gpu
        self._bar_tmp = card.g_tmp
        self._bar_net = TextStat(card.net_lbl, "NET  ")
        self._uptime_lbl = card.up_lbl
        self._proc_lbl = card.proc_lbl
        self.hud.on_resize = self._place_home_card

    def _place_home_card(self) -> None:
        card = getattr(self, "_home_card", None)
        if card is None:
            return
        # Legacy resource card remains hidden; the home canvas is waveform-only.
        card.hide()
        self.hud.card_w = 0

    def _build_input_bar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(70)
        h = QHBoxLayout(bar)
        h.setContentsMargins(16, 4, 16, 14)
        h.setSpacing(10)

        # Persistent, compact controls beside the command field. The main
        # waveform stays uncluttered; the top status also reflects microphone mute.
        control_strip = QWidget()
        control_strip.setStyleSheet("background: transparent;")
        controls = QHBoxLayout(control_strip)
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(6)

        self._home_mute_btn = QPushButton("MIC ON")
        self._home_mute_btn.setFixedSize(86, 34)
        self._home_mute_btn.setToolTip("Toggle microphone mute (F4)")
        self._home_mute_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._home_mute_btn.setFont(QFont(UI_FONT, 8, QFont.Weight.Bold))
        self._home_mute_btn.clicked.connect(self._toggle_mute)
        controls.addWidget(self._home_mute_btn)

        self._home_interrupt_btn = QPushButton("STOP VOICE")
        self._home_interrupt_btn.setFixedSize(92, 34)
        self._home_interrupt_btn.setToolTip("Interrupt ORI speech immediately (Esc)")
        self._home_interrupt_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._home_interrupt_btn.setFont(QFont(UI_FONT, 8, QFont.Weight.Bold))
        _stop_icon = CONFIG_DIR / "voice-stop.svg"
        if _stop_icon.exists():
            self._home_interrupt_btn.setIcon(QIcon(str(_stop_icon)))
            self._home_interrupt_btn.setIconSize(QSize(16, 16))
        self._home_interrupt_btn.setStyleSheet(f"""
            QPushButton {{ color: {C.MUTED_C}; background: rgba(22, 0, 8, 190);
                border: 1px solid {C.MUTED_C}; border-radius: 2px; padding: 0 6px; }}
            QPushButton:hover {{ color: #ffd8df; background: rgba(50, 0, 15, 220); }}
            QPushButton:pressed {{ background: rgba(80, 0, 24, 230); }}
        """)
        self._home_interrupt_btn.clicked.connect(self._do_interrupt)
        controls.addWidget(self._home_interrupt_btn)
        h.addWidget(control_strip, stretch=0)

        pill = GlassPanel(radius=2, brackets=True, opacity=0.82)
        pill.setFixedHeight(52)
        pill.setMinimumWidth(320)
        pill.setMaximumWidth(820)
        pill.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        pl = QHBoxLayout(pill)
        pl.setContentsMargins(14, 0, 8, 0)
        pl.addLayout(self._build_input_row())
        h.addWidget(pill, stretch=10)
        self._style_mute_btn()
        return bar

    def _nav_go(self, key: str) -> None:
        self._nav_chat_on = (key == "chat")
        if key == "home":
            self._close_setup()
            self._close_controls()
            for name in ("_memory_overlay", "_audio_overlay", "_plugin_manager_overlay"):
                ov = getattr(self, name, None)
                try:
                    if ov is not None and ov.isVisible():
                        ov.close()
                except Exception:
                    pass
            if hasattr(self, "_content_panel"):
                pass
        elif key == "chat":
            self._input.setFocus()
        elif key == "voice":
            self._open_audio_devices()
        elif key == "memory":
            self._open_memory_panel()
        elif key == "tools":
            self._open_plugin_manager()
        elif key == "controls":
            on = not self._ctrl_btn.isChecked()
            self._ctrl_btn.setChecked(on)
            self._toggle_controls(on)
        elif key == "settings":
            self._toggle_settings_page()
        self._sync_nav()

    def _sync_nav(self) -> None:
        def vis(name):
            ov = getattr(self, name, None)
            try:
                return ov is not None and ov.isVisible()
            except Exception:
                return False
        active = "home"
        if vis("_plugin_manager_overlay"):
            active = "tools"
        elif vis("_memory_overlay"):
            active = "memory"
        elif vis("_audio_overlay"):
            active = "voice"
        elif self._ctrl_btn.isChecked():
            active = "controls"
        elif self._drawer_btn.isChecked():
            active = "settings"
        elif getattr(self, "_nav_chat_on", False) and self._input.hasFocus():
            active = "chat"
        for k, b in self._nav.items():
            b.setActive(k == active)

    def _build_top_bar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("TopBar")
        bar.setStyleSheet(
            f"QFrame#TopBar {{ background: rgba(1, 5, 3, 232); "
            f"border-bottom: 1px solid {C.BORDER}; }}"
        )
        row = QHBoxLayout(bar)
        row.setContentsMargins(20, 8, 20, 8)
        row.setSpacing(8)

        brand = QLabel("ORI")
        brand.setFont(QFont(UI_FONT, 19, QFont.Weight.Bold))
        brand.setStyleSheet(f"color: {C.PRI}; background: transparent; letter-spacing: 2px;")
        row.addWidget(brand)

        pipe = QLabel("// PERSONAL SYSTEM")
        pipe.setFont(QFont(UI_FONT, 8, QFont.Weight.Bold))
        pipe.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        row.addWidget(pipe)
        row.addSpacing(12)

        self._system_state_lbl = QLabel("BOOTING")
        self._system_state_lbl.setFont(QFont(UI_FONT, 8, QFont.Weight.Bold))
        self._system_state_lbl.setStyleSheet(f"color: {C.ACC}; background: transparent;")
        row.addWidget(self._system_state_lbl)

        # Small live-use indicators. They appear only while a capability is in
        # active use and blink gently; no permanent feature toolbar is added.
        access_widget = QWidget()
        access_layout = QHBoxLayout(access_widget)
        access_layout.setContentsMargins(0, 0, 0, 0)
        access_layout.setSpacing(7)
        for key, glyph, label, tip in (
            ("mic", "◉", "MIC", "ORI is reading microphone audio"),
            ("speaker", "♫", "SPK", "ORI is playing audio through the speaker"),
            ("screen", "▣", "SCREEN", "ORI is capturing or continuously viewing the screen"),
            ("keyboard", "⌨", "KEYS", "ORI is sending keyboard input"),
            ("mouse", "⌖", "MOUSE", "ORI is controlling the pointer or mouse"),
            ("browser", "◎", "WEB", "ORI is interacting with a browser"),
            ("files", "▤", "FILES", "ORI is reading or changing files"),
            ("camera", "◉", "CAM", "ORI is accessing the camera"),
            ("network", "⌁", "NET", "ORI is connected to an online service"),
            ("system", "▦", "SYSTEM", "ORI is querying or changing Windows system settings"),
            ("phone", "▯", "PHONE", "A paired phone is actively sharing input or screen data"),
        ):
            lbl = QLabel(f"{glyph} {label}")
            lbl.setVisible(False)
            lbl.setToolTip(tip)
            lbl.setFont(QFont(UI_FONT, 7, QFont.Weight.Bold))
            lbl.setStyleSheet(f"color: {C.PRI}; background: transparent;")
            self._access_labels[key] = lbl
            access_layout.addWidget(lbl)
        row.addWidget(access_widget)
        row.addStretch(1)

        def _top_chip(text: str, width: int, tooltip: str = "") -> QLabel:
            chip = QLabel(text)
            chip.setMinimumHeight(24)
            chip.setFixedWidth(width)
            chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
            chip.setFont(QFont(UI_FONT, 8, QFont.Weight.Bold))
            chip.setStyleSheet(
                f"color: {C.PRI}; background: rgba(2, 14, 7, 170); "
                f"border: 1px solid {C.BORDER}; border-radius: 2px; padding: 0 4px;"
            )
            if tooltip:
                chip.setToolTip(tooltip)
            return chip

        try:
            self._metrics_display_mode = str(_read_full_config().get("metrics_display_mode") or "both").lower()
        except Exception:
            self._metrics_display_mode = "both"
        if self._metrics_display_mode not in ("percentages", "graphs", "both"):
            self._metrics_display_mode = "both"
        self._top_cpu_lbl = MetricChip("CPU", C.PRI, 72)
        self._top_ram_lbl = MetricChip("RAM", C.PRI, 72)
        self._top_temp_lbl = MetricChip("TEMP", C.PRI, 84)
        self._top_weather_lbl = _top_chip(
            "WX OFF", 72,
            "Weather is off until you enable it in Settings."
        )
        for _chip in (self._top_cpu_lbl, self._top_ram_lbl, self._top_temp_lbl, self._top_weather_lbl):
            row.addWidget(_chip)

        self._clock_lbl = QLabel("--:--")
        self._clock_lbl.setFont(QFont(UI_FONT, 10, QFont.Weight.Bold))
        self._clock_lbl.setStyleSheet(f"color: {C.TEXT}; background: transparent;")
        row.addWidget(self._clock_lbl)
        self._date_lbl = QLabel("")
        self._date_lbl.setFont(QFont(UI_FONT, 8))
        self._date_lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        row.addWidget(self._date_lbl)

        self._settings_btn = QPushButton("SETTINGS")
        self._settings_btn.setCheckable(False)
        self._settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._settings_btn.setFixedHeight(34)
        self._settings_btn.setFont(QFont(UI_FONT, 8, QFont.Weight.Bold))
        self._settings_btn.setStyleSheet(f"""
            QPushButton {{ color: {C.PRI}; background: rgba(3, 20, 10, 220);
                border: 1px solid {C.BORDER_B}; border-radius: 2px; padding: 0 14px; }}
            QPushButton:hover {{ color: {C.WHITE}; background: {C.PRI_GHO};
                border-color: {C.PRI}; }}
        """)
        self._settings_btn.clicked.connect(self._toggle_settings_page)
        row.addWidget(self._settings_btn)
        return bar

    def set_access_indicator(self, name: str, active: bool) -> None:
        """Thread-safe entry point for the live access strip in the top bar."""
        self._access_sig.emit(str(name or "").lower().strip(), bool(active))

    def _apply_access_indicator(self, name: str, active: bool) -> None:
        aliases = {"audio_input": "mic", "microphone": "mic", "audio_output": "speaker",
                   "screen_capture": "screen", "keyboard_input": "keyboard", "pointer": "mouse",
                   "browser_control": "browser", "file": "files", "camera_access": "camera",
                   "internet": "network"}
        key = aliases.get(name, name)
        label = self._access_labels.get(key)
        if label is None:
            return
        if active:
            self._access_active.add(key)
            label.show()
        else:
            self._access_active.discard(key)
            label.hide()
        self._tick_access_indicators()

    def _tick_access_indicators(self) -> None:
        self._access_blink_phase = not self._access_blink_phase
        for key in tuple(self._access_active):
            label = self._access_labels.get(key)
            if label is not None:
                color = C.PRI if self._access_blink_phase else C.PRI_DIM
                label.setStyleSheet(f"color: {color}; background: transparent;")

    def _toggle_settings_page(self) -> None:
        """Switch between the HUD and its single full settings page.

        Settings never open on top of another settings overlay; the HUD page is
        hidden while this page is active.
        """
        if not hasattr(self, "_page_stack"):
            return
        if self._page_stack.currentWidget() is self._settings_page:
            self._page_stack.setCurrentWidget(self._home_page)
            self._settings_btn.setText("SETTINGS")
        else:
            self._close_setup()
            self._close_controls()
            self._page_stack.setCurrentWidget(self._settings_page)
            self._settings_btn.setText("← BACK TO ORI")
            self._refresh_settings_status()

    def _settings_card(self, parent_layout, title: str, subtitle: str = ""):
        """Add a real collapsible settings section, closed on first open.

        Each section keeps its header visible while its controls remain hidden
        until the user expands that section. This prevents a wall of settings
        and keeps About Developer and Terms intentionally closed by default.
        The return value is still the section's content layout, preserving the
        existing callers that populate it with controls.
        """
        shell = QFrame()
        shell.setObjectName("SettingsSection")
        shell.setStyleSheet(
            f"QFrame#SettingsSection {{ background: rgba(2, 10, 5, 110); "
            f"border: 1px solid {C.BORDER}; border-radius: 3px; }}"
        )
        outer = QVBoxLayout(shell)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        toggle = QPushButton("▸  " + title.upper())
        toggle.setCheckable(True)
        toggle.setChecked(False)
        toggle.setMinimumHeight(42)
        toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        toggle.setFont(QFont(UI_FONT, 9, QFont.Weight.Bold))
        toggle.setStyleSheet(f"""
            QPushButton {{ color: {C.PRI}; background: rgba(1, 8, 4, 215);
                border: none; text-align: left; padding: 0 15px; letter-spacing: 1px; }}
            QPushButton:hover {{ color: {C.WHITE}; background: {C.PRI_GHO}; }}
            QPushButton:checked {{ color: {C.WHITE}; border-bottom: 1px solid {C.BORDER}; }}
        """)
        outer.addWidget(toggle)

        if subtitle:
            note = QLabel(subtitle)
            note.setWordWrap(True)
            note.setContentsMargins(15, 0, 15, 10)
            note.setFont(QFont(UI_FONT, 8))
            note.setStyleSheet(f"color: {C.TEXT_DIM}; background: rgba(1, 8, 4, 215); border: none;")
            outer.addWidget(note)

        body = QFrame()
        body.setObjectName("SettingsCardBody")
        body.setVisible(False)
        body.setStyleSheet(f"QFrame#SettingsCardBody {{ background: rgba(2, 10, 5, 224); border: none; }}")
        col = QVBoxLayout(body)
        col.setContentsMargins(18, 15, 18, 16)
        col.setSpacing(10)
        outer.addWidget(body)

        def _set_open(open_: bool) -> None:
            body.setVisible(open_)
            toggle.setText(("▾  " if open_ else "▸  ") + title.upper())
            shell.setProperty("expanded", bool(open_))

        toggle.toggled.connect(_set_open)
        parent_layout.addWidget(shell)
        if not hasattr(self, "_settings_section_toggles"):
            self._settings_section_toggles = {}
            self._settings_section_shells = {}
        self._settings_section_toggles[title] = toggle
        self._settings_section_shells[title] = shell
        return col

    def _open_developer_section(self) -> None:
        """Expand and scroll to About Developer when its Instagram footer is used."""
        key = "09 / ABOUT DEVELOPER"
        toggle = getattr(self, "_settings_section_toggles", {}).get(key)
        shell = getattr(self, "_settings_section_shells", {}).get(key)
        if toggle is not None:
            toggle.setChecked(True)
        if shell is not None and getattr(self, "_settings_scroll", None) is not None:
            QTimer.singleShot(40, lambda target=shell: self._settings_scroll.ensureWidgetVisible(target, 0, 16))

    def _settings_label(self, text: str, width: int = 170) -> QLabel:
        label = QLabel(text.upper())
        label.setMinimumWidth(width)
        label.setFont(QFont(UI_FONT, 8, QFont.Weight.Bold))
        label.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
        return label

    def _settings_line(self, layout, label: str, control, width: int = 170):
        row = QHBoxLayout()
        row.setSpacing(14)
        row.addWidget(self._settings_label(label, width))
        row.addWidget(control, stretch=1)
        layout.addLayout(row)

    def _settings_input(self, text: str = "", password: bool = False):
        box = QLineEdit(text)
        box.setMinimumHeight(34)
        box.setFont(QFont(UI_FONT, 9))
        box.setPlaceholderText("Enter value…")
        box.setEchoMode(QLineEdit.EchoMode.Password if password else QLineEdit.EchoMode.Normal)
        box.setStyleSheet(f"""
            QLineEdit {{ color: {C.TEXT}; background: rgba(0, 5, 2, 220);
                border: 1px solid {C.BORDER}; border-radius: 2px; padding: 6px 9px;
                selection-background-color: {C.PRI_GHO}; }}
            QLineEdit:focus {{ border-color: {C.PRI}; }}
        """)
        return box

    def _settings_combo(self):
        box = QComboBox()
        box.setMinimumHeight(34)
        box.setFont(QFont(UI_FONT, 9))
        box.setStyleSheet(f"""
            QComboBox {{ color: {C.TEXT}; background: rgba(0, 5, 2, 220);
                border: 1px solid {C.BORDER}; border-radius: 2px; padding: 5px 9px; }}
            QComboBox QAbstractItemView {{ color: {C.TEXT}; background: #020805;
                selection-background-color: {C.PRI_GHO}; border: 1px solid {C.BORDER}; }}
        """)
        return box

    def _settings_button(self, text: str, primary: bool = False):
        btn = QPushButton(text)
        btn.setMinimumHeight(34)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFont(QFont(UI_FONT, 8, QFont.Weight.Bold))
        if primary:
            btn.setStyleSheet(f"""
                QPushButton {{ color: {C.BG}; background: {C.PRI};
                    border: 1px solid {C.PRI}; border-radius: 2px; padding: 0 12px; }}
                QPushButton:hover {{ background: {C.WHITE}; }}
            """)
        else:
            btn.setStyleSheet(f"""
                QPushButton {{ color: {C.PRI}; background: transparent;
                    border: 1px solid {C.BORDER_B}; border-radius: 2px; padding: 0 12px; }}
                QPushButton:hover {{ background: {C.PRI_GHO}; border-color: {C.PRI}; }}
            """)
        return btn

    def _build_settings_page(self) -> QWidget:
        """Compact, category-based Settings. No scrolling page or visible scrollbar."""
        cfg = _read_full_config()
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        root = QVBoxLayout(page)
        root.setContentsMargins(28, 18, 28, 14)
        root.setSpacing(12)

        heading = QHBoxLayout()
        title = QLabel("SETTINGS")
        title.setFont(QFont(UI_FONT, 17, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {C.WHITE}; background: transparent; letter-spacing: 1px;")
        heading.addWidget(title)
        heading.addStretch(1)
        caption = QLabel("ORI PERSONAL SYSTEM")
        caption.setFont(QFont(UI_FONT, 7, QFont.Weight.Bold))
        caption.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent; letter-spacing: 1px;")
        heading.addWidget(caption)
        root.addLayout(heading)

        nav = QHBoxLayout()
        nav.setSpacing(6)
        self._settings_stack = QStackedWidget()
        self._settings_nav_buttons = []
        nav_names = ("AI & PROFILE", "VOICE & AUDIO", "APPEARANCE", "SYSTEM", "PHONE REMOTE", "ABOUT")
        nav_style = f"""
            QPushButton {{ color: {C.TEXT_DIM}; background: rgba(2,10,5,120);
                border: 1px solid {C.BORDER}; border-radius: 2px; padding: 0 12px;
                min-height: 34px; font: 700 8pt '{UI_FONT}'; }}
            QPushButton:checked {{ color: {C.PRI}; background: rgba(6,35,17,180);
                border: 1px solid {C.PRI_DIM}; }}
            QPushButton:hover {{ color: {C.WHITE}; border-color: {C.BORDER_B}; }}
        """
        for index, label in enumerate(nav_names):
            button = QPushButton(label)
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setStyleSheet(nav_style)
            button.clicked.connect(lambda checked=False, i=index: self._select_settings_category(i))
            nav.addWidget(button, 1)
            self._settings_nav_buttons.append(button)
        root.addLayout(nav)

        def panel(parent_layout, title_text: str, description: str = ""):
            frame = QFrame()
            frame.setObjectName("SettingsPanel")
            frame.setStyleSheet(
                f"QFrame#SettingsPanel {{ background: rgba(2,10,5,150); "
                f"border: 1px solid {C.BORDER}; border-radius: 3px; }}"
            )
            box = QVBoxLayout(frame)
            box.setContentsMargins(16, 13, 16, 14)
            box.setSpacing(9)
            title_lbl = QLabel(title_text)
            title_lbl.setFont(QFont(UI_FONT, 9, QFont.Weight.Bold))
            title_lbl.setStyleSheet(f"color: {C.PRI}; background: transparent; letter-spacing: 1px;")
            box.addWidget(title_lbl)
            if description:
                desc = QLabel(description)
                desc.setWordWrap(True)
                desc.setFont(QFont(UI_FONT, 8))
                desc.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
                box.addWidget(desc)
            parent_layout.addWidget(frame)
            return box

        def row(parent_layout, label: str, control, label_width: int = 150):
            h = QHBoxLayout()
            h.setSpacing(12)
            lbl = QLabel(label)
            lbl.setFixedWidth(label_width)
            lbl.setFont(QFont(UI_FONT, 8, QFont.Weight.Bold))
            lbl.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
            h.addWidget(lbl)
            h.addWidget(control, 1)
            parent_layout.addLayout(h)

        def button(text: str, primary: bool = False):
            return self._settings_button(text, primary=primary)

        def page_layout():
            p = QWidget()
            lay = QVBoxLayout(p)
            lay.setContentsMargins(0, 2, 0, 0)
            lay.setSpacing(10)
            return p, lay

        # AI & PROFILE -------------------------------------------------------
        p0, l0 = page_layout()
        split = QHBoxLayout(); split.setSpacing(12)
        l0.addLayout(split)
        profile_box = QVBoxLayout()
        key_box = QVBoxLayout()
        profile_frame = QFrame(); profile_frame.setObjectName("SettingsPanel")
        profile_frame.setStyleSheet(f"QFrame#SettingsPanel {{ background: rgba(2,10,5,150); border: 1px solid {C.BORDER}; border-radius: 3px; }}")
        profile_frame.setLayout(profile_box)
        profile_box.setContentsMargins(16, 13, 16, 14); profile_box.setSpacing(9)
        key_frame = QFrame(); key_frame.setObjectName("SettingsPanel")
        key_frame.setStyleSheet(f"QFrame#SettingsPanel {{ background: rgba(2,10,5,150); border: 1px solid {C.BORDER}; border-radius: 3px; }}")
        key_frame.setLayout(key_box)
        key_box.setContentsMargins(16, 13, 16, 14); key_box.setSpacing(9)
        split.addWidget(profile_frame, 4)
        split.addWidget(key_frame, 6)

        head = QLabel("YOUR PROFILE")
        head.setFont(QFont(UI_FONT, 9, QFont.Weight.Bold)); head.setStyleSheet(f"color: {C.PRI}; background: transparent; letter-spacing: 1px;")
        profile_box.addWidget(head)
        self._settings_user_name = self._settings_input(str(cfg.get("user_name") or ""))
        self._settings_user_name.setPlaceholderText("Your preferred name")
        row(profile_box, "Name", self._settings_user_name, 95)

        self._settings_language = self._settings_combo()
        for item in ("Auto detect", "Hinglish", "Hindi", "English"):
            self._settings_language.addItem(item, item)
        _language = str(cfg.get("preferred_language") or "Auto detect")
        _idx = self._settings_language.findData(_language)
        self._settings_language.setCurrentIndex(_idx if _idx >= 0 else 0)
        row(profile_box, "Language", self._settings_language, 95)

        self._settings_style = self._settings_combo()
        for item in ("Natural & friendly", "Concise", "Detailed", "Professional"):
            self._settings_style.addItem(item, item)
        _style = str(cfg.get("conversation_style") or "Natural & friendly")
        _idx = self._settings_style.findData(_style)
        self._settings_style.setCurrentIndex(_idx if _idx >= 0 else 0)
        row(profile_box, "Speaking style", self._settings_style, 95)

        self._settings_voice = self._settings_combo()
        from memory.config_manager import AVAILABLE_VOICES, get_voice
        for voice in AVAILABLE_VOICES:
            self._settings_voice.addItem(voice, voice)
        _voice_idx = self._settings_voice.findData(get_voice())
        self._settings_voice.setCurrentIndex(_voice_idx if _voice_idx >= 0 else 0)
        row(profile_box, "ORI voice", self._settings_voice, 95)
        save_identity = button("SAVE PREFERENCES", True)
        self._save_identity_btn = save_identity
        save_identity.clicked.connect(self._save_identity_and_voice)
        profile_box.addWidget(save_identity, alignment=Qt.AlignmentFlag.AlignLeft)
        profile_box.addStretch(1)

        head = QLabel("GOOGLE AI STUDIO")
        head.setFont(QFont(UI_FONT, 9, QFont.Weight.Bold)); head.setStyleSheet(f"color: {C.PRI}; background: transparent; letter-spacing: 1px;")
        key_box.addWidget(head)
        key_note = QLabel("Use one API key from Google AI Studio. ORI chooses a compatible Gemini model automatically.")
        key_note.setWordWrap(True); key_note.setFont(QFont(UI_FONT, 8)); key_note.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        key_box.addWidget(key_note)
        self._gemini_key_input = self._settings_input(str(cfg.get("gemini_api_key") or ""), password=True)
        self._gemini_key_input.setPlaceholderText("Paste Google AI Studio API key")
        keyrow = QHBoxLayout(); keyrow.setSpacing(8)
        keyrow.addWidget(self._gemini_key_input, 1)
        self._gemini_reveal_btn = button("SHOW")
        self._gemini_reveal_btn.setCheckable(True)
        self._gemini_reveal_btn.toggled.connect(lambda on: (
            self._gemini_key_input.setEchoMode(QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password),
            self._gemini_reveal_btn.setText("HIDE" if on else "SHOW")
        ))
        keyrow.addWidget(self._gemini_reveal_btn)
        key_box.addLayout(keyrow)
        key_actions = QHBoxLayout(); key_actions.setSpacing(8)
        self._save_key_btn = button("TEST & SAVE KEY", True)
        self._save_key_btn.clicked.connect(self._save_gemini_key_from_settings)
        self._gemini_key_input.textChanged.connect(lambda *_: self._save_key_btn.setText("TEST & SAVE KEY"))
        key_actions.addWidget(self._save_key_btn)
        get_key = button("GET A KEY ↗")
        get_key.clicked.connect(lambda: __import__("webbrowser").open("https://aistudio.google.com/app/apikey"))
        key_actions.addWidget(get_key)
        key_actions.addStretch(1)
        key_box.addLayout(key_actions)
        self._gemini_status = QLabel("")
        self._gemini_status.setWordWrap(True); self._gemini_status.setFont(QFont(UI_FONT, 8))
        self._gemini_status.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        key_box.addWidget(self._gemini_status)
        key_box.addStretch(1)
        self._settings_stack.addWidget(p0)

        # VOICE & AUDIO ------------------------------------------------------
        p1, l1 = page_layout()
        audio = panel(l1, "AUDIO DEVICES", "Choose which microphone and speakers ORI uses. System default is recommended.")
        from memory.config_manager import (get_input_device, get_output_device, get_wake_word_enabled,
                                           get_push_to_talk_enabled, get_brief_enabled,
                                           get_voice_interrupt_enabled)
        from core.audio_devices import DEFAULT_LABEL
        self._settings_input_device = self._settings_combo(); self._settings_input_device.addItem(DEFAULT_LABEL, "")
        current_in = get_input_device()
        if current_in:
            self._settings_input_device.addItem(current_in, current_in); self._settings_input_device.setCurrentIndex(1)
        self._settings_output_device = self._settings_combo(); self._settings_output_device.addItem(DEFAULT_LABEL, "")
        current_out = get_output_device()
        if current_out:
            self._settings_output_device.addItem(current_out, current_out); self._settings_output_device.setCurrentIndex(1)
        row(audio, "Microphone", self._settings_input_device)
        row(audio, "Speaker", self._settings_output_device)
        audio_actions = QHBoxLayout(); audio_actions.setSpacing(8)
        self._refresh_audio_btn = button("SCAN DEVICES")
        self._refresh_audio_btn.clicked.connect(self._refresh_audio_device_lists)
        self._save_audio_btn = button("SAVE & RECONNECT", True)
        self._save_audio_btn.clicked.connect(self._save_audio_settings)
        self._settings_input_device.currentIndexChanged.connect(lambda *_: self._save_audio_btn.setText("SAVE & RECONNECT"))
        self._settings_output_device.currentIndexChanged.connect(lambda *_: self._save_audio_btn.setText("SAVE & RECONNECT"))
        audio_actions.addWidget(self._refresh_audio_btn); audio_actions.addWidget(self._save_audio_btn); audio_actions.addStretch(1)
        audio.addLayout(audio_actions)
        self._audio_status = QLabel("Using the system default devices.")
        self._audio_status.setFont(QFont(UI_FONT, 8)); self._audio_status.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        audio.addWidget(self._audio_status)

        voice = panel(l1, "VOICE BEHAVIOUR", "Optional voice shortcuts. The main screen stays clean; these controls do not add feature buttons to the HUD.")
        self._settings_wake = QPushButton("WAKE WORD: ON" if get_wake_word_enabled() else "WAKE WORD: OFF")
        self._settings_wake.setCheckable(True); self._settings_wake.setChecked(bool(get_wake_word_enabled()))
        self._settings_wake.toggled.connect(self._on_settings_wake_toggled)
        self._settings_ptt = QPushButton("PUSH TO TALK: ON" if get_push_to_talk_enabled() else "PUSH TO TALK: OFF")
        self._settings_ptt.setCheckable(True); self._settings_ptt.setChecked(bool(get_push_to_talk_enabled()))
        self._settings_ptt.toggled.connect(self._on_settings_ptt_toggled)
        self._settings_brief = QPushButton("MORNING BRIEF: ON" if get_brief_enabled() else "MORNING BRIEF: OFF")
        self._settings_brief.setCheckable(True); self._settings_brief.setChecked(bool(get_brief_enabled()))
        self._settings_brief.toggled.connect(self._on_settings_brief_toggled)
        self._settings_autostart = QPushButton("START WITH WINDOWS: ON" if self._check_autostart() else "START WITH WINDOWS: OFF")
        self._settings_autostart.setCheckable(True); self._settings_autostart.setChecked(self._check_autostart())
        self._settings_autostart.toggled.connect(self._on_settings_autostart_toggled)
        self._settings_voice_interrupt = QPushButton(
            "VOICE INTERRUPT: ON" if get_voice_interrupt_enabled() else "VOICE INTERRUPT: OFF"
        )
        self._settings_voice_interrupt.setCheckable(True)
        self._settings_voice_interrupt.setChecked(get_voice_interrupt_enabled())
        self._settings_voice_interrupt.toggled.connect(self._on_settings_voice_interrupt_toggled)
        toggle_row = QHBoxLayout(); toggle_row.setSpacing(8)
        for toggle in (self._settings_wake, self._settings_ptt, self._settings_brief,
                       self._settings_autostart, self._settings_voice_interrupt):
            toggle.setMinimumHeight(36); toggle.setCursor(Qt.CursorShape.PointingHandCursor)
            toggle.setFont(QFont(UI_FONT, 8, QFont.Weight.Bold))
            toggle.setStyleSheet(f"QPushButton {{ color: {C.TEXT_MED}; background: rgba(3,14,7,150); border: 1px solid {C.BORDER}; padding: 0 10px; }} QPushButton:checked {{ color: {C.PRI}; border-color: {C.PRI_DIM}; background: {C.PRI_GHO}; }}")
            toggle_row.addWidget(toggle, 1)
        voice.addLayout(toggle_row)
        voice.addStretch(1)
        self._settings_stack.addWidget(p1)

        # APPEARANCE ---------------------------------------------------------
        p2, l2 = page_layout()
        appearance = panel(l2, "TERMINAL APPEARANCE", "ORI keeps its dark grid and terminal layout. Only the signal accent changes here.")
        self._settings_accent = self._settings_combo()
        for label, hexv in (("PHOSPHOR GREEN", "#43ff91"), ("AMBER TERMINAL", "#ffc35a"), ("ICE GREEN", "#b6ffd0")):
            self._settings_accent.addItem(label, hexv)
        old_accent = str(cfg.get("ui_color") or "#43ff91").lower()
        accent_idx = self._settings_accent.findData(old_accent)
        self._settings_accent.setCurrentIndex(accent_idx if accent_idx >= 0 else 0)
        row(appearance, "Signal accent", self._settings_accent)
        apply_theme = button("APPLY ACCENT", True)
        self._save_theme_btn = apply_theme
        apply_theme.clicked.connect(self._save_theme_settings)
        appearance.addWidget(apply_theme, alignment=Qt.AlignmentFlag.AlignLeft)
        note = QLabel("The idle signal has a subtle ambient motion. Live microphone and speaker audio drive the actual spectrum.")
        note.setWordWrap(True); note.setFont(QFont(UI_FONT, 8)); note.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        appearance.addWidget(note)
        appearance.addStretch(1)
        self._settings_stack.addWidget(p2)

        # SYSTEM -------------------------------------------------------------
        p3, l3 = page_layout()
        system = panel(l3, "SYSTEM DISPLAY", "Choose whether CPU and memory show values, mini graphs or both in the top bar.")
        self._settings_metrics_combo = self._settings_combo()
        metric_mode = str(cfg.get("metrics_display_mode") or "both").lower()
        for label, value in (("Percentages only", "percentages"), ("Mini graphs only", "graphs"), ("Percentages + graphs", "both")):
            self._settings_metrics_combo.addItem(label, value)
        metric_idx = self._settings_metrics_combo.findData(metric_mode)
        self._settings_metrics_combo.setCurrentIndex(metric_idx if metric_idx >= 0 else 2)
        row(system, "CPU / Memory / Temp", self._settings_metrics_combo)
        self._save_metrics_btn = button("SAVE DISPLAY", True)
        self._save_metrics_btn.clicked.connect(self._save_metrics_display_settings)
        self._settings_metrics_combo.currentIndexChanged.connect(lambda *_: self._save_metrics_btn.setText("SAVE DISPLAY"))
        system.addWidget(self._save_metrics_btn, alignment=Qt.AlignmentFlag.AlignLeft)
        self._sensor_status_lbl = QLabel("")
        self._sensor_status_lbl.setWordWrap(True); self._sensor_status_lbl.setFont(QFont(UI_FONT, 8)); self._sensor_status_lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        system.addWidget(self._sensor_status_lbl)
        sensor_btn = button("RECHECK CPU SENSOR")
        sensor_btn.clicked.connect(self._recheck_temperature_sensor)
        system.addWidget(sensor_btn, alignment=Qt.AlignmentFlag.AlignLeft)
        self._refresh_temperature_sensor_status()

        location = panel(
            l3,
            "LOCATION & WEATHER",
            "Allow Windows device location to show your area and current weather. Coordinates are shared with OpenStreetMap and Open-Meteo only after your consent.",
        )
        self._location_status_lbl = QLabel(
            "LOCATION NOT ENABLED · ORI will ask once when the configured app starts."
        )
        self._weather_status_lbl = self._location_status_lbl
        self._location_status_lbl.setWordWrap(True)
        self._location_status_lbl.setFont(QFont(UI_FONT, 8))
        self._location_status_lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        location.addWidget(self._location_status_lbl)

        location_actions = QHBoxLayout()
        location_actions.setSpacing(8)
        self._location_enable_btn = button("ALLOW DEVICE LOCATION", True)
        self._location_enable_btn.clicked.connect(self._enable_device_location)
        self._location_open_settings_btn = button("WINDOWS LOCATION PRIVACY")
        self._location_open_settings_btn.clicked.connect(self._open_windows_location_settings)
        location_actions.addWidget(self._location_enable_btn)
        location_actions.addWidget(self._location_open_settings_btn)
        location_actions.addStretch(1)
        location.addLayout(location_actions)

        self._location_disable_btn = button("DISABLE LOCATION & WEATHER")
        self._location_disable_btn.clicked.connect(self._disable_device_location)
        location.addWidget(self._location_disable_btn, alignment=Qt.AlignmentFlag.AlignLeft)
        location.addWidget(self._small_note(
            "Location is requested from Windows only while ORI is in the foreground. "
            "The saved coordinates stay in your local ORI configuration until you disable this feature. "
            "Windows permission can also be revoked in Windows Location Privacy."
        ))
        location.addStretch(1)
        system.addStretch(1)
        self._settings_stack.addWidget(p3)

        # PHONE REMOTE -------------------------------------------------------
        p4, l4 = page_layout()
        remote = panel(l4, "PHONE REMOTE", "Pair a trusted phone on the same Wi-Fi network. The QR code is one-time and expires after 10 minutes.")
        self._remote_status_lbl = QLabel("Checking local dashboard…")
        self._remote_status_lbl.setWordWrap(True); self._remote_status_lbl.setFont(QFont(UI_FONT, 9, QFont.Weight.Bold)); self._remote_status_lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        remote.addWidget(self._remote_status_lbl)
        self._remote_url_lbl = QLabel("Not paired")
        self._remote_url_lbl.setWordWrap(True); self._remote_url_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._remote_url_lbl.setFont(QFont(UI_FONT, 8)); self._remote_url_lbl.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        remote.addWidget(self._remote_url_lbl)
        remote_actions = QHBoxLayout(); remote_actions.setSpacing(8)
        self._show_qr_btn = button("PAIR PHONE", True)
        self._show_qr_btn.clicked.connect(self._settings_open_remote)
        self._copy_link_btn = button("COPY LINK")
        self._copy_link_btn.clicked.connect(self._settings_copy_remote_link)
        remote_actions.addWidget(self._show_qr_btn); remote_actions.addWidget(self._copy_link_btn); remote_actions.addStretch(1)
        remote.addLayout(remote_actions)
        remote.addWidget(self._small_note("Phone and PC must be on the same trusted Wi-Fi. ORI never changes a Public network to Private or opens a public-internet port automatically."))
        remote.addStretch(1)
        self._settings_stack.addWidget(p4)

        # ABOUT & UPDATES ----------------------------------------------------
        p5, l5 = page_layout()
        about = panel(l5, "ABOUT ORI", "Product information, creator profile and verified software updates.")
        from ori_metadata import (
            ABOUT_TEXT as _ORI_ABOUT_TEXT,
            TERMS_TEXT as _ORI_TERMS_TEXT,
            INSTAGRAM_URL as _ORI_INSTAGRAM_URL,
        )
        about_text = QLabel(_ORI_ABOUT_TEXT)
        about_text.setWordWrap(True)
        about_text.setFont(QFont(UI_FONT, 8))
        about_text.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
        about.addWidget(about_text)

        social_row = QHBoxLayout()
        self._instagram_btn = button("INSTAGRAM PROFILE ↗")
        _instagram_icon = CONFIG_DIR / "instagram.svg"
        if _instagram_icon.exists():
            self._instagram_btn.setIcon(QIcon(str(_instagram_icon)))
        self._instagram_btn.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(_ORI_INSTAGRAM_URL))
        )
        social_row.addWidget(self._instagram_btn)
        social_row.addStretch(1)
        about.addLayout(social_row)

        update_note = QLabel(
            "SOFTWARE UPDATES · Check for a new ORI release. Downloads are verified before installation."
        )
        update_note.setWordWrap(True)
        update_note.setFont(QFont(UI_FONT, 8))
        update_note.setStyleSheet(f"color: {C.ACC}; background: transparent;")
        about.addWidget(update_note)
        self._app_update_status_lbl = QLabel("Update check has not been run.")
        self._app_update_status_lbl.setWordWrap(True)
        self._app_update_status_lbl.setFont(QFont(UI_FONT, 8))
        self._app_update_status_lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        about.addWidget(self._app_update_status_lbl)
        update_actions = QHBoxLayout()
        update_actions.setSpacing(8)
        self._check_updates_btn = button("CHECK FOR UPDATES", True)
        self._check_updates_btn.clicked.connect(self._check_app_updates)
        update_actions.addWidget(self._check_updates_btn)
        self._download_update_btn = button("DOWNLOAD UPDATE")
        self._download_update_btn.setEnabled(False)
        self._download_update_btn.clicked.connect(self._download_app_update)
        update_actions.addWidget(self._download_update_btn)
        self._install_update_btn = button("INSTALL & RESTART")
        self._install_update_btn.setEnabled(False)
        self._install_update_btn.clicked.connect(self._install_app_update)
        update_actions.addWidget(self._install_update_btn)
        update_actions.addStretch(1)
        about.addLayout(update_actions)

        terms_button = button("TERMS & CONDITIONS")
        terms_button.clicked.connect(lambda: self._show_terms_dialog(_ORI_TERMS_TEXT))
        about.addWidget(terms_button, alignment=Qt.AlignmentFlag.AlignLeft)
        about.addStretch(1)
        self._settings_stack.addWidget(p5)

        root.addWidget(self._settings_stack, 1)
        self._settings_page_status = QLabel("")
        self._settings_page_status.setWordWrap(True)
        self._settings_page_status.setFont(QFont(UI_FONT, 8))
        self._settings_page_status.setStyleSheet(f"color: {C.ACC}; background: transparent; padding-top: 2px;")
        root.addWidget(self._settings_page_status)
        self._select_settings_category(0)
        self._settings_stack.currentChanged.connect(lambda *_: self._refresh_settings_status())
        return page

    def _select_settings_category(self, index: int) -> None:
        stack = getattr(self, "_settings_stack", None)
        buttons = getattr(self, "_settings_nav_buttons", [])
        if stack is None or not buttons:
            return
        index = max(0, min(int(index), stack.count() - 1))
        stack.setCurrentIndex(index)
        for i, btn in enumerate(buttons):
            btn.blockSignals(True)
            btn.setChecked(i == index)
            btn.blockSignals(False)
        if index == 4:
            self._refresh_remote_status()
        if index == 3:
            self._refresh_temperature_sensor_status()
        if index == 0:
            self._refresh_settings_status()

    def _show_terms_dialog(self, terms: str) -> None:
        from PyQt6.QtWidgets import QDialog, QDialogButtonBox
        dialog = QDialog(self)
        dialog.setWindowTitle("ORI · Terms & Conditions")
        dialog.resize(760, 620)
        dialog.setStyleSheet(f"QDialog {{ background: {C.BG}; color: {C.TEXT}; }}")
        box = QVBoxLayout(dialog)
        body = QTextEdit()
        body.setReadOnly(True)
        body.setPlainText(str(terms or ""))
        body.setStyleSheet(f"QTextEdit {{ color: {C.TEXT_MED}; background: rgba(0,0,0,130); border: 1px solid {C.BORDER}; padding: 10px; }}")
        box.addWidget(body, 1)
        actions = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        actions.rejected.connect(dialog.reject)
        actions.accepted.connect(dialog.accept)
        box.addWidget(actions)
        dialog.exec()

    def _refresh_temperature_sensor_status(self) -> None:
        if not hasattr(self, "_sensor_status_lbl"):
            return
        value = _metrics.snapshot().get("tmp", -1.0)
        if value is not None and float(value) >= 0:
            self._sensor_status_lbl.setText(f"CPU SENSOR ONLINE · {float(value):.1f} °C · Live hardware reading.")
            self._sensor_status_lbl.setStyleSheet(f"color: {C.GREEN}; background: transparent;")
        else:
            self._sensor_status_lbl.setText(
                "CPU temperature is unavailable. With LibreHardwareMonitor 0.9.6, open Options → Remote Web Server → Run (default localhost:8085). ORI reads its local data.json endpoint and never invents a temperature."
            )
            self._sensor_status_lbl.setStyleSheet(f"color: {C.ACC}; background: transparent;")

    def _recheck_temperature_sensor(self) -> None:
        # Reset the cached WMI state. The background metric thread will re-probe
        # the supported hardware providers on its next slow cycle.
        for attr in ("_lhwmi_conn", "_wmi_conn"):
            try:
                setattr(_metrics, attr, None)
            except Exception:
                pass
        for attr in ("_lhwmi_ok", "_wmi_ok"):
            try:
                setattr(_metrics, attr, None)
            except Exception:
                pass
        try:
            _metrics._slow_tick = 0
        except Exception:
            pass
        self._sensor_status_lbl.setText("Rechecking hardware temperature sensors…")
        QTimer.singleShot(2600, self._finish_temperature_sensor_recheck)

    def _finish_temperature_sensor_recheck(self) -> None:
        self._update_metrics()
        self._refresh_temperature_sensor_status()

    def _refresh_remote_status(self) -> None:
        if getattr(self, "_remote_dashboard_running", False):
            if hasattr(self, "_remote_status_lbl"):
                self._remote_status_lbl.setText("LOCAL DASHBOARD READY · Pair your phone on the same Wi-Fi.")
                self._remote_status_lbl.setStyleSheet(f"color: {C.GREEN}; background: transparent;")
        elif hasattr(self, "_remote_status_lbl"):
            detail = str(getattr(self, "_remote_status_detail", "Dashboard is starting…") or "Dashboard is starting…")
            self._remote_status_lbl.setText("REMOTE NOT READY · " + detail[:240])
            self._remote_status_lbl.setStyleSheet(f"color: {C.ACC}; background: transparent;")

    def _wrap_layout(self, layout):
        holder = QWidget()
        holder.setStyleSheet("background: transparent;")
        holder.setLayout(layout)
        return holder

    def _small_note(self, text: str):
        label = QLabel(text)
        label.setWordWrap(True)
        label.setFont(QFont(UI_FONT, 8))
        label.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        return label

    def _check_app_updates(self) -> None:
        if hasattr(self, "_check_updates_btn"):
            self._check_updates_btn.setEnabled(False)
            self._check_updates_btn.setText("CHECKING…")
        if hasattr(self, "_app_update_status_lbl"):
            self._app_update_status_lbl.setText("Checking the configured official GitHub repository…")
        def worker():
            try:
                from core.app_updater import check_for_updates
                result = check_for_updates()
            except Exception as exc:
                result = {"ok": False, "message": f"Update check failed: {type(exc).__name__}: {exc}"}
            self._app_update_check_sig.emit(result)
        threading.Thread(target=worker, name="ori-update-check", daemon=True).start()

    def _apply_app_update_check(self, result: object) -> None:
        data = result if isinstance(result, dict) else {"ok": False, "message": "Invalid update response."}
        self._latest_update_info = data
        if hasattr(self, "_check_updates_btn"):
            self._check_updates_btn.setEnabled(True)
            self._check_updates_btn.setText("CHECK FOR UPDATES")
        if hasattr(self, "_download_update_btn"):
            self._download_update_btn.setEnabled(bool(data.get("ok") and data.get("update_available") and data.get("asset") and data.get("checksum_asset")))
        if hasattr(self, "_app_update_status_lbl"):
            if data.get("ok") and data.get("update_available"):
                self._app_update_status_lbl.setText(
                    f"UPDATE AVAILABLE · ORI {data.get('latest_version')} · SHA-256 verification required before install."
                )
                self._app_update_status_lbl.setStyleSheet(f"color: {C.GREEN}; background: transparent;")
            else:
                self._app_update_status_lbl.setText(str(data.get("message") or "No update information."))
                self._app_update_status_lbl.setStyleSheet(f"color: {C.TEXT_DIM if data.get('ok') else C.ACC}; background: transparent;")

    def _download_app_update(self) -> None:
        info = getattr(self, "_latest_update_info", None)
        if not isinstance(info, dict) or not info.get("update_available"):
            return
        self._download_update_btn.setEnabled(False)
        self._download_update_btn.setText("DOWNLOADING…")
        if hasattr(self, "_app_update_status_lbl"):
            self._app_update_status_lbl.setText("Downloading release and verifying its SHA-256 checksum…")
        def worker():
            try:
                from core.app_updater import download_latest_update
                result = download_latest_update(info)
            except Exception as exc:
                result = {"ok": False, "message": f"Update download failed: {type(exc).__name__}: {exc}"}
            self._app_update_download_sig.emit(result)
        threading.Thread(target=worker, name="ori-update-download", daemon=True).start()

    def _apply_app_update_download(self, result: object) -> None:
        data = result if isinstance(result, dict) else {"ok": False, "message": "Invalid download response."}
        self._staged_update = data if data.get("ok") else None
        if hasattr(self, "_download_update_btn"):
            self._download_update_btn.setEnabled(False)
            self._download_update_btn.setText("DOWNLOAD UPDATE")
        frozen = bool(getattr(sys, "frozen", False))
        if hasattr(self, "_install_update_btn"):
            self._install_update_btn.setEnabled(bool(data.get("ok") and frozen))
        if hasattr(self, "_app_update_status_lbl"):
            message = str(data.get("message") or "Update download finished.")
            if data.get("ok") and not frozen:
                message += " Source/development build detected: close ORI, then replace the source folder with the verified release package or update through Git."
            self._app_update_status_lbl.setText(message)
            self._app_update_status_lbl.setStyleSheet(f"color: {C.GREEN if data.get('ok') else C.ACC}; background: transparent;")

    def _install_app_update(self) -> None:
        data = getattr(self, "_staged_update", None)
        if not isinstance(data, dict) or not data.get("staged_dir"):
            return
        answer = QMessageBox.question(
            self, "Install ORI update?",
            "ORI will close, replace its program files, preserve your configuration and memory, then restart. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            from core.app_updater import schedule_windows_update
            result = schedule_windows_update(str(data["staged_dir"]))
            if not result.get("ok"):
                self._app_update_status_lbl.setText(str(result.get("message")))
                return
            self._app_update_status_lbl.setText(str(result.get("message")))
            QApplication.quit()
        except Exception as exc:
            self._app_update_status_lbl.setText(f"Could not schedule update: {type(exc).__name__}: {exc}")

    def _refresh_settings_status(self):
        if not hasattr(self, "_gemini_status"):
            return
        cfg = _read_full_config()
        key = str(cfg.get("gemini_api_key") or "").strip()
        if key and cfg.get("gemini_key_verified"):
            self._gemini_status.setText("CONNECTED · Google AI Studio key verified.")
            self._gemini_status.setStyleSheet(f"color: {C.GREEN}; background: transparent;")
        elif key:
            self._gemini_status.setText("KEY SAVED · Verify the connection before using live AI.")
            self._gemini_status.setStyleSheet(f"color: {C.ACC}; background: transparent;")
        else:
            self._gemini_status.setText("NOT CONNECTED · Add a Google AI Studio API key to start ORI.")
            self._gemini_status.setStyleSheet(f"color: {C.ACC}; background: transparent;")

    def _confirm_location_data_sharing(self) -> bool:
        reply = QMessageBox.question(
            self,
            "Enable ORI Location & Weather",
            "ORI can ask Windows for your device location. If you allow it, ORI sends the coordinates to OpenStreetMap to resolve your area name and to Open-Meteo to retrieve current weather. The coordinates are saved only in your local ORI configuration for weather refreshes.\n\nContinue and request Windows location access?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            self._weather_write_config({"location_prompt_decision": "later"})
            if hasattr(self, "_location_status_lbl"):
                self._location_status_lbl.setText(
                    "LOCATION NOT ENABLED · You can allow it later from Settings."
                )
            return False
        self._weather_write_config({"location_prompt_decision": "accepted"})
        return True

    def _maybe_prompt_startup_location(self) -> None:
        """Ask once on startup, then reuse the saved consent on later launches."""
        if not getattr(self, "_ready", False):
            return
        config = _read_full_config()
        decision = str(config.get("location_prompt_decision") or "")
        if decision == "accepted":
            self._begin_device_location_request()
            return
        if decision in ("later", "disabled"):
            if config.get("weather_enabled"):
                self._launch_weather_worker("refresh")
            return
        if self._confirm_location_data_sharing():
            self._begin_device_location_request()
        elif config.get("weather_enabled"):
            self._launch_weather_worker("refresh")

    def _enable_device_location(self) -> None:
        config = _read_full_config()
        if config.get("location_prompt_decision") != "accepted":
            if not self._confirm_location_data_sharing():
                return
        self._begin_device_location_request()

    def _begin_device_location_request(self) -> None:
        if self._location_request_inflight:
            return
        if not getattr(self, "_ready", False):
            if hasattr(self, "_location_status_lbl"):
                self._location_status_lbl.setText("FINISH ORI SETUP FIRST · Then enable device location here.")
            return
        self._location_request_inflight = True
        if hasattr(self, "_location_enable_btn"):
            self._location_enable_btn.setEnabled(False)
            self._location_enable_btn.setText("REQUESTING WINDOWS LOCATION…")
        if hasattr(self, "_location_status_lbl"):
            self._location_status_lbl.setText(
                "WAITING FOR WINDOWS LOCATION PERMISSION AND A DEVICE POSITION…"
            )
        try:
            from core.location_service import request_location_access
            started = request_location_access(
                lambda result: self._location_access_sig.emit(result)
            )
            if not started:
                self._location_request_inflight = False
        except Exception as exc:
            self._location_access_sig.emit({
                "ok": False,
                "reason": "unavailable",
                "error": f"Could not start device location: {type(exc).__name__}: {exc}",
            })

    def _on_device_location_result(self, result: object) -> None:
        self._location_request_inflight = False
        if hasattr(self, "_location_enable_btn"):
            self._location_enable_btn.setEnabled(True)
            self._location_enable_btn.setText("REFRESH DEVICE LOCATION")
        if not isinstance(result, dict) or not result.get("ok"):
            error = str(
                result.get("error") if isinstance(result, dict)
                else "Windows returned an invalid location response."
            )
            reason = str(result.get("reason") or "") if isinstance(result, dict) else ""
            if hasattr(self, "_location_status_lbl"):
                self._location_status_lbl.setText("LOCATION UNAVAILABLE · " + error)
            if reason == "denied":
                self._set_weather_top_off(
                    "LOC DENIED",
                    "Windows denied ORI location access. Open Windows Location Privacy to change it."
                )
            elif reason == "unavailable":
                self._set_weather_top_off("LOC N/A", "Windows device location is unavailable in this build or on this PC.")
            return

        try:
            latitude = float(result["latitude"])
            longitude = float(result["longitude"])
        except (KeyError, TypeError, ValueError):
            self._location_status_lbl.setText("LOCATION ERROR · Windows returned invalid coordinates.")
            return
        accuracy = result.get("accuracy_m")
        if hasattr(self, "_location_status_lbl"):
            self._location_status_lbl.setText(
                "LOCATION FOUND · Resolving your area and current weather…"
            )
        self._launch_location_weather_worker(latitude, longitude, accuracy)

    def _launch_location_weather_worker(
        self, latitude: float, longitude: float, accuracy_m: float | None
    ) -> None:
        self._location_generation += 1
        generation = self._location_generation

        def worker() -> None:
            try:
                from core.weather_service import (
                    fetch_current_weather,
                    reverse_geocode_coordinates,
                )
                location = reverse_geocode_coordinates(latitude, longitude)
                result = fetch_current_weather(location)
                result.update({
                    "ok": True,
                    "request_mode": "device",
                    "device_accuracy_m": accuracy_m,
                })
            except Exception as exc:
                result = {
                    "ok": False,
                    "request_mode": "device",
                    "error": f"{type(exc).__name__}: {exc}"[:500],
                }
            result["generation"] = generation
            self._location_weather_sig.emit(result)

        threading.Thread(
            target=worker,
            daemon=True,
            name="ori-location-weather",
        ).start()

    def _on_location_weather_result(self, result: object) -> None:
        if not isinstance(result, dict):
            result = {"ok": False, "error": "Location/weather returned an invalid response."}
        if result.get("generation") != self._location_generation:
            return
        if not result.get("ok"):
            error = str(result.get("error") or "Weather provider did not return a result.")
            if hasattr(self, "_location_status_lbl"):
                self._location_status_lbl.setText(
                    "LOCATION RECEIVED · WEATHER UPDATE FAILED · " + error
                )
            self._set_weather_top_off("WX ERR", error)
            return

        self._on_weather_result(result)
        accuracy = result.get("device_accuracy_m")
        if accuracy is not None:
            try:
                accuracy_text = f"Windows location accuracy: approximately ±{float(accuracy):.0f} m."
            except (TypeError, ValueError):
                accuracy_text = "Windows did not report an accuracy estimate."
        else:
            accuracy_text = "Windows did not report an accuracy estimate."
        locality = str(result.get("location_label") or "Current location")
        if hasattr(self, "_location_status_lbl"):
            self._location_status_lbl.setText(
                f"LOCATION ACTIVE · {locality}\n{accuracy_text}\n"
                "Area name: © OpenStreetMap contributors · Weather: Open-Meteo."
            )

    def _disable_device_location(self) -> None:
        self._location_generation += 1
        self._location_request_inflight = False
        self._weather_write_config(
            {"location_prompt_decision": "disabled", "weather_enabled": False},
            remove=(
                "weather_latitude", "weather_longitude", "weather_city",
                "weather_region", "weather_country", "weather_location_label",
                "weather_location_source", "weather_last_updated",
            ),
        )
        self._set_weather_top_off(
            "WX OFF",
            "ORI location and weather are disabled. You can revoke Windows permission in Location Privacy."
        )
        if hasattr(self, "_location_status_lbl"):
            self._location_status_lbl.setText(
                "LOCATION & WEATHER DISABLED · Saved coordinates cleared. To revoke the Windows permission too, open Windows Location Privacy."
            )

    def _open_windows_location_settings(self) -> None:
        QDesktopServices.openUrl(QUrl("ms-settings:privacy-location"))

    def _weather_write_config(self, updates: dict | None = None, remove: tuple[str, ...] = ()) -> dict:
        data = _read_full_config()
        for key in remove:
            data.pop(key, None)
        if updates:
            data.update(updates)
        API_FILE.parent.mkdir(parents=True, exist_ok=True)
        API_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return data

    def _set_weather_top_off(self, label: str = "WX OFF", tooltip: str = "Weather is disabled. Enable it in Settings → System & Weather.") -> None:
        if hasattr(self, "_top_weather_lbl"):
            self._top_weather_lbl.setText(label)
            self._top_weather_lbl.setToolTip(tooltip)

    def _launch_weather_worker(self, mode: str, city: str = "") -> None:
        if self._weather_busy:
            return
        self._weather_generation += 1
        generation = self._weather_generation
        self._weather_busy = True
        button = {
            "ip": getattr(self, "_weather_enable_btn", None),
            "city": getattr(self, "_weather_city_btn", None),
            "refresh": getattr(self, "_weather_refresh_btn", None),
        }.get(mode)
        self._weather_request_button = button
        self._weather_button_texts = {
            "ip": "ENABLE APPROX. AREA WEATHER",
            "city": "USE CITY & GET WEATHER",
            "refresh": "REFRESH WEATHER",
        }
        for _button in (getattr(self, "_weather_enable_btn", None),
                        getattr(self, "_weather_city_btn", None),
                        getattr(self, "_weather_refresh_btn", None),
                        getattr(self, "_weather_disable_btn", None)):
            if _button is not None:
                _button.setEnabled(False)
        if button is not None:
            button.setText("LOCATING…" if mode == "ip" else ("LOOKING UP…" if mode == "city" else "REFRESHING…"))
        if hasattr(self, "_weather_status_lbl"):
            self._weather_status_lbl.setText({
                "ip": "REQUESTING APPROXIMATE AREA… Your public IP is used only because you enabled this action.",
                "city": "LOOKING UP THE CITY AND CURRENT CONDITIONS…",
                "refresh": "REFRESHING CURRENT WEATHER…",
            }.get(mode, "CHECKING WEATHER…"))

        def worker():
            from core.weather_service import (
                resolve_approximate_ip_location, geocode_city, fetch_current_weather,
            )
            try:
                cfg_now = _read_full_config()
                if mode == "ip":
                    location = resolve_approximate_ip_location()
                elif mode == "city":
                    location = geocode_city(city)
                else:
                    try:
                        lat = float(cfg_now["weather_latitude"])
                        lon = float(cfg_now["weather_longitude"])
                    except (KeyError, TypeError, ValueError):
                        raise RuntimeError("No saved weather area. Enable approximate-area weather or enter a city first.")
                    location = {
                        "latitude": lat, "longitude": lon,
                        "city": cfg_now.get("weather_city") or "Saved area",
                        "region": cfg_now.get("weather_region") or "",
                        "country": cfg_now.get("weather_country") or "",
                        "location_label": cfg_now.get("weather_location_label") or cfg_now.get("weather_city") or "Saved area",
                        "location_source": cfg_now.get("weather_location_source") or "saved area",
                    }
                result = fetch_current_weather(location)
                result["request_mode"] = mode
                result["ok"] = True
            except Exception as exc:
                result = {"ok": False, "request_mode": mode, "error": str(exc)[:500]}
            result["generation"] = generation
            self._weather_result_sig.emit(result)

        threading.Thread(target=worker, daemon=True, name=f"ori-weather-{mode}").start()

    def _enable_approx_weather(self) -> None:
        self._launch_weather_worker("ip")

    def _use_manual_weather_city(self) -> None:
        city = self._weather_city_input.text().strip()
        if len(city) < 2:
            self._weather_status_lbl.setText("ENTER A CITY OR AREA NAME FIRST.")
            self._weather_city_input.setFocus()
            return
        self._launch_weather_worker("city", city)

    def _refresh_saved_weather(self) -> None:
        cfg = _read_full_config()
        if not cfg.get("weather_enabled"):
            self._set_weather_top_off()
            return
        self._launch_weather_worker("refresh")

    def _refresh_weather_if_enabled(self) -> None:
        cfg = _read_full_config()
        if cfg.get("location_prompt_decision") == "accepted":
            return
        if cfg.get("weather_enabled"):
            self._launch_weather_worker("refresh")
        else:
            self._set_weather_top_off()

    def _disable_weather(self) -> None:
        # Invalidate an in-flight request so it cannot re-enable weather after
        # the user has explicitly disabled and cleared the stored area.
        self._weather_generation += 1
        self._weather_busy = False
        for _button in (getattr(self, "_weather_enable_btn", None),
                        getattr(self, "_weather_city_btn", None),
                        getattr(self, "_weather_refresh_btn", None),
                        getattr(self, "_weather_disable_btn", None)):
            if _button is not None:
                _button.setEnabled(True)
        if hasattr(self, "_weather_enable_btn"):
            self._weather_enable_btn.setText("ENABLE APPROX. AREA WEATHER")
        if hasattr(self, "_weather_city_btn"):
            self._weather_city_btn.setText("USE CITY & GET WEATHER")
        if hasattr(self, "_weather_refresh_btn"):
            self._weather_refresh_btn.setText("REFRESH WEATHER")
        self._weather_write_config(
            {"weather_enabled": False},
            remove=("weather_latitude", "weather_longitude", "weather_city", "weather_region",
                    "weather_country", "weather_location_label", "weather_location_source", "weather_last_updated"),
        )
        self._set_weather_top_off()
        if hasattr(self, "_weather_status_lbl"):
            self._weather_status_lbl.setText("WEATHER DISABLED. Saved area coordinates have been cleared from ORI configuration.")
        if hasattr(self, "_settings_page_status"):
            self._settings_page_status.setText("LOCATION WEATHER DISABLED AND SAVED AREA CLEARED.")

    def _on_weather_result(self, result: object) -> None:
        if not isinstance(result, dict):
            result = {"ok": False, "error": "Weather provider returned an invalid response."}
        if result.get("generation", self._weather_generation) != self._weather_generation:
            return
        self._weather_busy = False
        for _button in (getattr(self, "_weather_enable_btn", None),
                        getattr(self, "_weather_city_btn", None),
                        getattr(self, "_weather_refresh_btn", None),
                        getattr(self, "_weather_disable_btn", None)):
            if _button is not None:
                _button.setEnabled(True)
        for _key, _button in (("ip", getattr(self, "_weather_enable_btn", None)),
                              ("city", getattr(self, "_weather_city_btn", None)),
                              ("refresh", getattr(self, "_weather_refresh_btn", None))):
            if _button is not None:
                _button.setText(self._weather_button_texts.get(_key, _button.text()))
        if not result.get("ok"):
            error = str(result.get("error") or "Unknown weather error")
            cfg_after_error = _read_full_config()
            if hasattr(self, "_weather_status_lbl"):
                prior_time = str(cfg_after_error.get("weather_last_updated") or "never")
                self._weather_status_lbl.setText(
                    "WEATHER REFRESH FAILED · " + error +
                    (f"\nPrevious estimate retained; last successful update: {prior_time}." if cfg_after_error.get("weather_enabled") else "")
                )
            if cfg_after_error.get("weather_enabled"):
                # Do not leave a failed refresh looking like live/current data.
                location = str(cfg_after_error.get("weather_city") or "saved area")
                prior_time = str(cfg_after_error.get("weather_last_updated") or "unknown time")
                self._set_weather_top_off(
                    "WX STALE",
                    f"Saved weather for {location} may be stale. Last successful update: {prior_time}.\nRefresh failed: {error}"
                )
            else:
                self._set_weather_top_off("WX ERR", "Weather could not be loaded: " + error)
            if hasattr(self, "_settings_page_status"):
                self._settings_page_status.setText("WEATHER REFRESH FAILED: " + error)
            return

        city = str(result.get("city") or "Selected area")
        region = str(result.get("region") or "")
        country = str(result.get("country") or "")
        label = str(result.get("location_label") or ", ".join(p for p in (city, region, country) if p))
        temp = float(result["temperature_c"])
        feels = result.get("apparent_temperature_c")
        humidity = result.get("relative_humidity")
        wind = result.get("wind_speed_kmh")
        mode = str(result.get("request_mode") or "refresh")
        location_source = str(result.get("location_source") or "saved area")
        patch = {
            "weather_enabled": True,
            "weather_latitude": float(result["latitude"]),
            "weather_longitude": float(result["longitude"]),
            "weather_city": city,
            "weather_region": region,
            "weather_country": country,
            "weather_location_label": label,
            "weather_location_source": location_source,
            "weather_last_updated": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        self._weather_write_config(patch)
        if mode == "ip" and hasattr(self, "_weather_enable_btn"):
            self._weather_enable_btn.setText("AREA WEATHER ENABLED ✓")
        elif mode == "city" and hasattr(self, "_weather_city_btn"):
            self._weather_city_btn.setText("CITY WEATHER SAVED ✓")
        elif mode == "refresh" and hasattr(self, "_weather_refresh_btn"):
            self._weather_refresh_btn.setText("REFRESHED ✓")
        if hasattr(self, "_weather_city_input") and mode == "city":
            self._weather_city_input.setText(city)
        if hasattr(self, "_top_weather_lbl"):
            display = f"WX {temp:.0f}° · {city}"
            fm = self._top_weather_lbl.fontMetrics()
            display = fm.elidedText(display, Qt.TextElideMode.ElideRight, self._top_weather_lbl.width() - 8)
            self._top_weather_lbl.setText(display)
            self._top_weather_lbl.setToolTip(
                f"{label}: {temp:.1f}°C · {result.get('condition', 'Current conditions')}\n"
                f"Feels like: {feels if feels is not None else 'N/A'}°C · Humidity: {humidity if humidity is not None else 'N/A'}% · "
                f"Wind: {wind if wind is not None else 'N/A'} km/h\n"
                f"Source: Open-Meteo · locality: OpenStreetMap contributors · location method: {location_source}."
            )
        details = (
            f"CURRENT ESTIMATE · {label} · {temp:.1f}°C · {result.get('condition', 'Current conditions')}"
            f" · feels like {feels:.1f}°C" if feels is not None else
            f"CURRENT ESTIMATE · {label} · {temp:.1f}°C · {result.get('condition', 'Current conditions')}"
        )
        if humidity is not None:
            details += f" · humidity {humidity:.0f}%"
        if wind is not None:
            details += f" · wind {wind:.1f} km/h"
        details += f"\nSource: Open-Meteo · Location: {location_source} · updated {patch['weather_last_updated']}"
        if hasattr(self, "_weather_status_lbl"):
            self._weather_status_lbl.setText(details)
        if hasattr(self, "_settings_page_status"):
            self._settings_page_status.setText("CURRENT WEATHER UPDATED.")

    def _save_gemini_key_from_settings(self):
        key = self._gemini_key_input.text().strip()
        if len(key) < 20:
            self._settings_page_status.setText(
                "KEY NOT SAVED: enter a Google AI Studio key."
            )
            self._gemini_key_input.setFocus()
            return
        if not self._save_key_btn.isEnabled():
            return
        self._save_key_btn.setEnabled(False)
        self._gemini_key_input.setEnabled(False)
        self._save_key_btn.setText("VERIFYING WITH GOOGLE…")
        self._gemini_status.setText("Checking Google AI Studio key…")
        self._gemini_status.setStyleSheet(f"color: {C.ACC}; background: transparent;")

        def work():
            try:
                from core.key_validation import validate_google_api_key
                ok, message = validate_google_api_key(key, timeout=8.0)
            except Exception as exc:
                ok, message = False, f"Verification failed: {type(exc).__name__}."
            self._gemini_key_test_sig.emit(key, bool(ok), str(message))

        threading.Thread(target=work, daemon=True, name="ori-settings-key-test").start()

    def _on_gemini_key_test_done(self, key: str, ok: bool, message: str):
        self._save_key_btn.setEnabled(True)
        self._gemini_key_input.setEnabled(True)
        if not ok:
            self._save_key_btn.setText("TEST & SAVE KEY")
            self._gemini_status.setText(message)
            self._gemini_status.setStyleSheet(f"color: {C.RED}; background: transparent;")
            self._settings_page_status.setText("Google AI Studio key was not saved.")
            return

        data = _read_full_config()
        data["gemini_api_key"] = key
        data["assistant_mode"] = "cloud"
        data["gemini_key_verified"] = True
        data.setdefault("assistant_name", "ORI")
        data.setdefault(
            "os_system",
            {"Windows": "windows", "Darwin": "mac", "Linux": "linux"}.get(_OS, "linux"),
        )
        API_FILE.parent.mkdir(parents=True, exist_ok=True)
        API_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        self._ready = True
        QTimer.singleShot(1200, self._maybe_prompt_startup_location)
        self._refresh_settings_status()
        self._gemini_status.setText("KEY VERIFIED · " + message)
        self._gemini_status.setStyleSheet(f"color: {C.GREEN}; background: transparent;")
        self._save_key_btn.setText("CONNECTED ✓")
        self._settings_page_status.setText("GOOGLE AI STUDIO KEY VERIFIED. Reconnecting ORI…")
        self._log.append_log("SYS: Google AI Studio key verified and saved.")
        if self.on_api_key_change:
            try:
                self.on_api_key_change()
            except Exception as exc:
                self._settings_page_status.setText(
                    f"Key verified and saved. Reconnect request failed: {exc}"
                )
        if self._overlay is not None:
            self._overlay.hide()
            self._overlay = None

    def _save_identity_and_voice(self):
        from memory.config_manager import save_assistant_config, get_voice, save_voice
        name = "ORI"
        user = self._settings_user_name.text().strip()
        language = self._settings_language.currentData() or "Auto detect"
        style = self._settings_style.currentData() or "Natural & friendly"
        voice = self._settings_voice.currentData() or self._settings_voice.currentText()
        old_voice = get_voice()
        save_assistant_config(name, user)
        data = _read_full_config()
        data["assistant_name"] = name
        data["user_name"] = user
        data["preferred_language"] = language
        data["conversation_style"] = style
        data["guest_mode"] = bool(data.get("guest_mode", True))
        data["onboarding_completed"] = True
        data["assistant_mode"] = "cloud"
        API_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        if voice != old_voice:
            save_voice(str(voice))
        self._assistant_name = name
        self.setWindowTitle(f"{name.upper()} — {APP_VERSION}")
        self._title_lbl.setText(name)
        if voice != old_voice and self.on_voice_change:
            self.on_voice_change()
        self._save_identity_btn.setText("SAVED ✓")
        self._settings_page_status.setText(
            "PREFERENCES SAVED." + (" VOICE SESSION RECONNECTING." if voice != old_voice else "")
        )

    def _save_audio_settings(self):
        from memory.config_manager import get_input_device, get_output_device, save_input_device, save_output_device
        new_in = str(self._settings_input_device.currentData() or "")
        new_out = str(self._settings_output_device.currentData() or "")
        changed = (new_in != get_input_device()) or (new_out != get_output_device())
        save_input_device(new_in)
        save_output_device(new_out)
        if changed and self.on_audio_device_change:
            self.on_audio_device_change()
        self._audio_status.setText("Audio devices saved." + (" Reconnecting the voice session." if changed else " No device change detected."))
        self._save_audio_btn.setText("SAVED ✓")
        self._settings_page_status.setText("AUDIO SETTINGS SAVED.")

    def _refresh_audio_device_lists(self):
        self._refresh_audio_btn.setEnabled(False)
        self._refresh_audio_btn.setText("SCANNING…")
        def worker():
            try:
                from core.audio_devices import list_devices
                inputs = list_devices("input", refresh=True)
                outputs = list_devices("output", refresh=True)
            except Exception as exc:
                inputs, outputs = [], []
                self._log_sig.emit(f"ERR: Audio device scan failed: {exc}")
            self._audio_choices_sig.emit(inputs, outputs)
        threading.Thread(target=worker, daemon=True, name="ori-audio-scan").start()

    def _populate_audio_choices(self, inputs, outputs):
        from memory.config_manager import get_input_device, get_output_device
        self._refresh_audio_btn.setEnabled(True)
        self._refresh_audio_btn.setText("SCAN DEVICES")
        for box, names, current in (
            (self._settings_input_device, inputs or [], get_input_device()),
            (self._settings_output_device, outputs or [], get_output_device()),
        ):
            box.blockSignals(True)
            box.clear()
            box.addItem("System default", "")
            for name in names:
                box.addItem(str(name), str(name))
            if current and box.findData(current) < 0:
                box.addItem(f"{current} (saved, not detected)", current)
            idx = box.findData(current) if current else 0
            box.setCurrentIndex(idx if idx >= 0 else 0)
            box.blockSignals(False)
        self._audio_status.setText(f"Detected {len(inputs or [])} microphone(s) and {len(outputs or [])} speaker(s).")

    def _save_metrics_display_settings(self):
        mode = str(self._settings_metrics_combo.currentData() or "both").lower()
        if mode not in ("percentages", "graphs", "both"):
            mode = "both"
        data = _read_full_config()
        data["metrics_display_mode"] = mode
        API_FILE.parent.mkdir(parents=True, exist_ok=True)
        API_FILE.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        self._metrics_display_mode = mode
        self._update_metrics()
        self._save_metrics_btn.setText("SAVED ✓")
        labels = {
            "percentages": "Percentages only",
            "graphs": "Graphs only",
            "both": "Percentages and graphs",
        }
        self._settings_page_status.setText(
            f"SYSTEM DISPLAY UPDATED: {labels[mode]}. Temperature remains in °C when available."
        )

    def _save_theme_settings(self):
        accent = str(self._settings_accent.currentData() or "#43ff91")
        old = current_palette()
        if not apply_ui_accent(accent):
            self._settings_page_status.setText("COLOUR VALUE INVALID.")
            return
        new = current_palette()
        retheme_all_widgets(old, new)
        data = _read_full_config()
        data["ui_color"] = accent.lower()
        API_FILE.parent.mkdir(parents=True, exist_ok=True)
        API_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
        self._save_theme_btn.setText("APPLIED ✓")
        self._settings_page_status.setText("INTERFACE ACCENT APPLIED.")

    def _on_settings_voice_interrupt_toggled(self, enabled: bool):
        try:
            from memory.config_manager import save_voice_interrupt_enabled
            save_voice_interrupt_enabled(bool(enabled))
            self._settings_voice_interrupt.setText(
                "VOICE INTERRUPT: ON" if enabled else "VOICE INTERRUPT: OFF"
            )
            callback = getattr(self, "on_voice_interrupt_change", None)
            if callable(callback):
                callback(bool(enabled))
            self._settings_page_status.setText(
                "VOICE BARGE-IN ENABLED · Sustained speech is distinguished from speaker echo and noise."
                if enabled else "VOICE BARGE-IN DISABLED · Use the interrupt key/button to stop ORI."
            )
        except Exception as exc:
            self._settings_page_status.setText(f"VOICE INTERRUPT SETTING FAILED: {exc}")

    def _on_settings_wake_toggled(self, enabled: bool):
        try:
            from memory.config_manager import get_wake_word_enabled
            current = bool(get_wake_word_enabled())
            if enabled != current:
                self._toggle_wake_word()
            self._settings_wake.setText("WAKE WORD: ON" if enabled else "WAKE WORD: OFF")
        except Exception as exc:
            self._settings_page_status.setText(f"WAKE WORD SETTING FAILED: {exc}")

    def _on_settings_ptt_toggled(self, enabled: bool):
        try:
            from memory.config_manager import get_push_to_talk_enabled
            if bool(get_push_to_talk_enabled()) != bool(enabled):
                self._toggle_ptt()
            self._settings_ptt.setText("PUSH-TO-TALK: ON" if enabled else "PUSH-TO-TALK: OFF")
        except Exception as exc:
            self._settings_page_status.setText(f"PUSH-TO-TALK SETTING FAILED: {exc}")

    def _on_settings_brief_toggled(self, enabled: bool):
        from memory.config_manager import save_brief_enabled
        save_brief_enabled(bool(enabled))
        self._settings_brief.setText("MORNING BRIEF: ON" if enabled else "MORNING BRIEF: OFF")

    def _on_settings_autostart_toggled(self, enabled: bool):
        try:
            current = self._check_autostart()
            if current != bool(enabled):
                self._toggle_autostart()
            actual = self._check_autostart()
            self._settings_autostart.blockSignals(True)
            self._settings_autostart.setChecked(actual)
            self._settings_autostart.setText("START WITH WINDOWS: ON" if actual else "START WITH WINDOWS: OFF")
            self._settings_autostart.blockSignals(False)
        except Exception as exc:
            self._settings_page_status.setText(f"AUTO-START SETTING FAILED: {exc}")

    def _load_inline_plugin_settings(self):
        if self._plugin_inline_loaded:
            return
        section_shell = getattr(self, "_settings_section_shells", {}).get("06 / INTEGRATIONS")
        if not self.get_plugin_settings:
            if section_shell is not None:
                section_shell.hide()
            # The runtime may not have finished booting yet. Try again when
            # Settings is opened next time.
            self._plugin_inline_loaded = False
            return
        try:
            sections = self.get_plugin_settings() or []
        except Exception:
            if section_shell is not None:
                section_shell.hide()
            self._plugin_inline_loaded = True
            return
        # Clear the waiting note before drawing the schema-declared fields.
        while self._plugin_settings_layout.count():
            item = self._plugin_settings_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self._plugin_inline_widgets = {}
        if not sections:
            if section_shell is not None:
                section_shell.hide()
            self._plugin_inline_loaded = True
            return
        if section_shell is not None:
            section_shell.show()
        for sec in sections:
            ns = str(sec.get("namespace") or sec.get("plugin") or "plugin")
            sub = QFrame()
            sub.setStyleSheet(f"QFrame {{ background: rgba(3, 14, 7, 170); border: 1px solid {C.BORDER}; }}")
            sub_lay = QVBoxLayout(sub)
            sub_lay.setContentsMargins(10, 10, 10, 10)
            sub_lay.setSpacing(7)
            heading = QLabel(str(sec.get("title") or ns).upper())
            heading.setFont(QFont(UI_FONT, 8, QFont.Weight.Bold))
            heading.setStyleSheet(f"color: {C.PRI}; background: transparent; border: none;")
            sub_lay.addWidget(heading)
            widgets = {}
            values = sec.get("values") or {}
            for field in sec.get("fields") or []:
                if not isinstance(field, dict) or not field.get("key"):
                    continue
                key = str(field["key"])
                ftype = str(field.get("type") or "text").lower()
                stored = values.get(key, field.get("default", ""))
                if ftype == "choice":
                    ctrl = self._settings_combo()
                    for option in field.get("options") or []:
                        ctrl.addItem(str(option), str(option))
                    idx = ctrl.findText(str(stored))
                    if idx >= 0:
                        ctrl.setCurrentIndex(idx)
                elif ftype == "toggle":
                    ctrl = QPushButton("ON" if bool(stored) else "OFF")
                    ctrl.setCheckable(True)
                    ctrl.setChecked(bool(stored))
                    ctrl.setMinimumHeight(30)
                    ctrl.setStyleSheet(f"QPushButton {{ color: {C.PRI}; background: {C.PRI_GHO}; border: 1px solid {C.BORDER}; }} QPushButton:checked {{ color: {C.BG}; background: {C.PRI}; }}")
                    ctrl.toggled.connect(lambda on, b=ctrl: b.setText("ON" if on else "OFF"))
                else:
                    ctrl = self._settings_input("" if stored is None else str(stored), password=(ftype == "password"))
                    if field.get("placeholder"):
                        ctrl.setPlaceholderText(str(field["placeholder"]))
                self._settings_line(sub_lay, str(field.get("label") or key), ctrl, 150)
                widgets[key] = (ctrl, ftype)
            self._plugin_inline_widgets[ns] = {"fields": widgets, "schema": sec}
            actions = QHBoxLayout()
            save = self._settings_button("SAVE " + ns.upper(), primary=True)
            self._plugin_inline_widgets[ns]["save_button"] = save
            save.clicked.connect(lambda _=False, namespace=ns: self._save_inline_plugin(namespace))
            for _ctrl, _ftype in widgets.values():
                if _ftype == "choice":
                    _ctrl.currentIndexChanged.connect(lambda *_args, b=save, label="SAVE " + ns.upper(): b.setText(label))
                elif _ftype == "toggle":
                    _ctrl.toggled.connect(lambda *_args, b=save, label="SAVE " + ns.upper(): b.setText(label))
                else:
                    _ctrl.textChanged.connect(lambda *_args, b=save, label="SAVE " + ns.upper(): b.setText(label))
            actions.addWidget(save)
            action = sec.get("action")
            if isinstance(action, dict) and callable(action.get("run")):
                test = self._settings_button(str(action.get("label") or "TEST CONNECTION"))
                test.clicked.connect(lambda _=False, namespace=ns: self._test_inline_plugin(namespace))
                actions.addWidget(test)
            actions.addStretch(1)
            sub_lay.addLayout(actions)
            status = QLabel("")
            status.setWordWrap(True)
            status.setFont(QFont(UI_FONT, 8))
            status.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent; border: none;")
            sub_lay.addWidget(status)
            self._plugin_inline_widgets[ns]["status"] = status
            self._plugin_settings_layout.addWidget(sub)
        self._plugin_settings_layout.addStretch(1)
        self._plugin_inline_loaded = True

    def _inline_plugin_values(self, namespace: str) -> dict:
        rec = self._plugin_inline_widgets.get(namespace) or {}
        values = {}
        for key, (ctrl, ftype) in rec.get("fields", {}).items():
            if ftype == "choice":
                values[key] = ctrl.currentText()
            elif ftype == "toggle":
                values[key] = ctrl.isChecked()
            else:
                values[key] = ctrl.text().strip()
        return values

    def _save_inline_plugin(self, namespace: str):
        try:
            from memory.config_manager import save_plugin_config
            save_plugin_config(namespace, self._inline_plugin_values(namespace))
            rec = self._plugin_inline_widgets[namespace]
            rec["status"].setText("Saved to this PC.")
            rec["status"].setStyleSheet(f"color: {C.PRI}; background: transparent; border: none;")
            save_button = rec.get("save_button")
            if save_button is not None:
                save_button.setText("SAVED ✓")
        except Exception as exc:
            self._plugin_inline_widgets[namespace]["status"].setText(f"Save failed: {exc}")

    def _test_inline_plugin(self, namespace: str):
        rec = self._plugin_inline_widgets.get(namespace) or {}
        sec = rec.get("schema") or {}
        action = sec.get("action") or {}
        run = action.get("run")
        if not callable(run):
            return
        self._save_inline_plugin(namespace)
        rec["status"].setText("Testing connection…")
        values = self._inline_plugin_values(namespace)
        def worker():
            try:
                result = run(values)
                if isinstance(result, tuple) and len(result) == 2:
                    ok, message = bool(result[0]), str(result[1])
                else:
                    ok, message = bool(result), str(result)
            except Exception as exc:
                ok, message = False, str(exc)
            self._plugin_test_done_sig.emit(namespace, ok, message)
        threading.Thread(target=worker, daemon=True, name=f"ori-plugin-test-{namespace}").start()

    def _on_plugin_test_done(self, namespace: str, ok: bool, message: str):
        rec = self._plugin_inline_widgets.get(namespace) or {}
        status = rec.get("status")
        if status is not None:
            status.setText(message[:600])
            status.setStyleSheet(f"color: {C.PRI if ok else C.RED}; background: transparent; border: none;")

    def _build_header(self) -> None:
        """Create only hidden compatibility buttons for legacy drawer handlers."""
        self._drawer_btn = QPushButton("⚙", self)
        self._drawer_btn.setCheckable(True)
        self._drawer_btn.clicked.connect(self._toggle_drawer)
        self._drawer_btn.hide()
        self._ctrl_btn = QPushButton("🎛", self)
        self._ctrl_btn.setCheckable(True)
        self._ctrl_btn.clicked.connect(self._toggle_controls)
        self._ctrl_btn.hide()

    def _tick_clock(self):
        t = time.strftime("%I:%M %p")
        d = time.strftime("%a, %d %b %Y")
        self._clock_lbl.setText(t)
        self._date_lbl.setText(d)
        if hasattr(self, "_nav"):
            self._sync_nav()

    def _build_left_panel(self) -> QWidget:
        w = QWidget()
        w.setFixedWidth(_LEFT_W)
        lay = QVBoxLayout(w)
        lay.setContentsMargins(18, 22, 8, 16)
        lay.setSpacing(2)

        # brand: the assistant's own name (rename it in CUSTOMISE)
        self._title_lbl = QLabel("ORI")
        _bf = QFont(UI_FONT, 26)
        _bf.setWeight(QFont.Weight.Bold)
        self._title_lbl.setFont(_bf)
        self._title_lbl.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        lay.addWidget(self._title_lbl)
        self._sub_lbl = QLabel("PERSONAL AI DESKTOP SYSTEM")
        self._sub_lbl.setFont(QFont(UI_FONT, 9))
        self._sub_lbl.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
        lay.addWidget(self._sub_lbl)
        lay.addSpacing(22)

        self._nav = {}
        for key, label, icon in (
            ("home",     "Home",     "home"),
            ("chat",     "Chat",     "chat"),
            ("voice",    "Voice",    "voice"),
            ("memory",   "Memory",   "memory"),
            ("tools",    "Tools",    "tools"),
            ("controls", "Controls", "controls"),
            ("settings", "Settings", "settings"),
        ):
            b = NavButton(label, icon)
            b.clicked.connect(lambda k=key: self._nav_go(k))
            lay.addWidget(b)
            self._nav[key] = b
            lay.addSpacing(4)
        self._nav["home"].setActive(True)
        lay.addStretch()
        return w

    def _build_right_panel(self) -> QWidget:
        outer = QWidget()
        outer.setFixedWidth(_RIGHT_W)
        _ol = QVBoxLayout(outer)
        _ol.setContentsMargins(0, 16, 16, 16)
        w = GlassPanel(radius=18)
        _ol.addWidget(w)
        lay = QVBoxLayout(w)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(8)

        def _sec(txt):
            l = QLabel(f"▸ {txt}")
            l.setFont(QFont(UI_FONT, 7, QFont.Weight.Bold))
            l.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
            return l

        lay.addWidget(_sec("ACTIVITY"))
        self._log = LogWidget()
        lay.addWidget(self._log, stretch=1)

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER}; margin: 2px 0;")
        lay.addWidget(sep)

        lay.addWidget(_sec("FILE UPLOAD"))
        self._drop_zone = FileDropZone()
        self._drop_zone.file_selected.connect(self._on_file_selected)
        lay.addWidget(self._drop_zone)

        self._file_hint = QLabel("No file loaded — drop or click above to upload")
        self._file_hint.setFont(QFont(UI_FONT, 7))
        self._file_hint.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
        self._file_hint.setWordWrap(True)
        lay.addWidget(self._file_hint)

        self._interrupt_btn = QPushButton("✋  INTERRUPT  [ESC]")
        self._interrupt_btn.setFixedHeight(34)
        self._interrupt_btn.setFont(QFont(UI_FONT, 8, QFont.Weight.Bold))
        self._interrupt_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._interrupt_btn.setStyleSheet(f"""
            QPushButton {{
                background: #140008; color: {C.MUTED_C};
                border: 1px solid {C.MUTED_C}; border-radius: 3px;
            }}
            QPushButton:hover {{
                background: #200010; border: 1px solid #ff6688;
            }}
            QPushButton:pressed {{
                background: #300018;
            }}
        """)
        self._interrupt_btn.clicked.connect(self._do_interrupt)
        lay.addWidget(self._interrupt_btn)

        self._mute_btn = QPushButton("🎙  MICROPHONE ACTIVE")
        self._mute_btn.setFixedHeight(30)
        self._mute_btn.setFont(QFont(UI_FONT, 8, QFont.Weight.Bold))
        self._mute_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._mute_btn.clicked.connect(self._toggle_mute)
        self._style_mute_btn()
        lay.addWidget(self._mute_btn)

        return outer

    def _build_quick_drawer(self) -> QWidget:
        """Floating overlay panel shown when the ⚙ header button is toggled."""
        _BTN_STYLE_PRI = f"""
            QPushButton {{
                background: #07163a; color: {C.PRI};
                border: 1px solid {C.PRI_DIM}; border-radius: 3px;
                text-align: left; padding: 0 8px;
            }}
            QPushButton:hover {{ background: {C.PRI_GHO}; border-color: {C.PRI}; }}
        """
        _BTN_STYLE_DIM = f"""
            QPushButton {{
                background: transparent; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 3px;
                text-align: left; padding: 0 8px;
            }}
            QPushButton:hover {{ color: {C.PRI}; border-color: {C.BORDER_B}; }}
        """

        self._BTN_PRI, self._BTN_DIM = _BTN_STYLE_PRI, _BTN_STYLE_DIM
        w = QWidget(self.centralWidget())
        w.setObjectName("QuickDrawer")
        w.setStyleSheet(f"""
            QWidget#QuickDrawer {{
                background: rgba(5, 14, 36, 238);
                border: 1px solid {C.BORDER_B};
                border-radius: 14px;
            }}
        """)
        w.hide()

        lay = QVBoxLayout(w)
        lay.setContentsMargins(10, 8, 10, 10)
        lay.setSpacing(5)

        hdr = QLabel("◈ SETUP")
        hdr.setFont(QFont(UI_FONT, 7, QFont.Weight.Bold))
        hdr.setStyleSheet(f"color: {C.PRI_DIM}; background: transparent; "
                          f"border-bottom: 1px solid {C.BORDER}; padding-bottom: 4px;")
        lay.addWidget(hdr)

        remote_btn = QPushButton("◉  REMOTE CONTROL")
        remote_btn.setFixedHeight(30)
        remote_btn.setFont(QFont(UI_FONT, 8, QFont.Weight.Bold))
        remote_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        remote_btn.setStyleSheet(_BTN_STYLE_PRI)
        remote_btn.clicked.connect(self._open_remote)
        lay.addWidget(remote_btn)

        sc_btn = QPushButton("⊞  CREATE DESKTOP SHORTCUT")
        sc_btn.setFixedHeight(26)
        sc_btn.setFont(QFont(UI_FONT, 7))
        sc_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        sc_btn.setStyleSheet(_BTN_STYLE_DIM)
        sc_btn.clicked.connect(self._create_desktop_shortcut)
        lay.addWidget(sc_btn)

        self._autostart_btn = QPushButton("◉  AUTO-START: OFF")
        self._autostart_btn.setFixedHeight(26)
        self._autostart_btn.setFont(QFont(UI_FONT, 7))
        self._autostart_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._autostart_btn.clicked.connect(self._toggle_autostart)
        lay.addWidget(self._autostart_btn)

        # Product identity is not user-renamable; all supported preferences are in Settings.

        audio_btn = QPushButton("🎧  AUDIO DEVICES")
        audio_btn.setFixedHeight(26)
        audio_btn.setFont(QFont(UI_FONT, 7))
        audio_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        audio_btn.setStyleSheet(_BTN_STYLE_DIM)
        audio_btn.clicked.connect(self._open_audio_devices)
        lay.addWidget(audio_btn)

        mem_btn = QPushButton("🧠  MEMORY")
        mem_btn.setFixedHeight(26)
        mem_btn.setFont(QFont(UI_FONT, 7))
        mem_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        mem_btn.setStyleSheet(_BTN_STYLE_DIM)
        mem_btn.clicked.connect(self._open_memory_panel)
        lay.addWidget(mem_btn)

        plugin_btn = QPushButton("🧩  PLUGINS")
        plugin_btn.setFixedHeight(26)
        plugin_btn.setFont(QFont(UI_FONT, 7))
        plugin_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        plugin_btn.setStyleSheet(_BTN_STYLE_DIM)
        plugin_btn.clicked.connect(self._open_plugin_manager)
        lay.addWidget(plugin_btn)

        settings_btn = QPushButton("⚙  PLUGIN SETTINGS")
        settings_btn.setFixedHeight(26)
        settings_btn.setFont(QFont(UI_FONT, 7))
        settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        settings_btn.setStyleSheet(_BTN_STYLE_DIM)
        settings_btn.clicked.connect(self._open_plugin_settings)
        lay.addWidget(settings_btn)

        w.adjustSize()
        return w

    def _build_controls_drawer(self) -> QWidget:
        """The switches that get flicked every day, in their own panel."""
        w = QWidget(self.centralWidget())
        w.setObjectName("QuickDrawer")
        w.setStyleSheet(self._quick_drawer.styleSheet())
        w.hide()

        lay = QVBoxLayout(w)
        lay.setContentsMargins(10, 8, 10, 10)
        lay.setSpacing(5)

        hdr = QLabel("◈ CONTROLS")
        hdr.setFont(QFont(UI_FONT, 7, QFont.Weight.Bold))
        hdr.setStyleSheet(f"color: {C.PRI_DIM}; background: transparent; "
                          f"border-bottom: 1px solid {C.BORDER}; padding-bottom: 4px;")
        lay.addWidget(hdr)

        def _row(button, style=None, height=26):
            button.setFixedHeight(height)
            button.setFont(QFont(UI_FONT, 7))
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            if style:
                button.setStyleSheet(style)
            lay.addWidget(button)
            return button

        fs_btn = _row(QPushButton("⛶  FULLSCREEN  [F11]"), self._BTN_DIM)
        fs_btn.clicked.connect(self._toggle_fullscreen)

        self._brief_btn = _row(QPushButton())
        self._brief_btn.clicked.connect(self._toggle_brief)

        self._wake_btn = _row(QPushButton())
        self._wake_btn.clicked.connect(self._toggle_wake_word)
        self._wake_sleep_btn = _row(QPushButton())
        self._wake_sleep_btn.clicked.connect(self._tap_wake_manual)
        # Neutral until the real state lands from the background warm-up.
        self._wake_btn.setText("🎙  WAKE WORD")
        self._wake_btn.setStyleSheet(self._BTN_DIM)
        self._wake_sleep_btn.hide()

        self._ptt_btn = _row(QPushButton())
        self._ptt_btn.clicked.connect(self._toggle_ptt)
        self._refresh_talk_btns()

        w.adjustSize()
        return w

    def _warm_wake_state(self) -> None:
        """Work out the wake-word state off the UI thread, once.

        It used to be resolved when the drawer opened, and that made opening the
        drawer take two seconds the first time — measured at 2.10s, all of it
        `import openwakeword` dragging in onnxruntime behind it. The button
        count had nothing to do with it; the Qt thread was simply waiting on an
        import. Afterwards the same check costs about a millisecond, so it only
        ever needed to happen somewhere other than in front of the user.
        """
        def work():
            try:
                self._wake_state()
            except Exception:
                pass
            self._wake_btns_sig.emit()
        threading.Thread(target=work, daemon=True, name="wake-state-warm").start()

    def _toggle_drawer(self, checked: bool):
        if checked:
            self._close_controls()
            self._position_quick_drawer()
            self._quick_drawer.show()
            self._quick_drawer.raise_()
        else:
            self._quick_drawer.hide()

    def _toggle_controls(self, checked: bool):
        if checked:
            self._close_setup()
            self._refresh_wake_btns()   # cheap now: the state was warmed at boot
            self._position_ctrl_drawer()
            self._ctrl_drawer.show()
            self._ctrl_drawer.raise_()
        else:
            self._ctrl_drawer.hide()

    def _close_setup(self):
        if hasattr(self, "_quick_drawer"):
            self._quick_drawer.hide()
        if hasattr(self, "_drawer_btn"):
            self._drawer_btn.setChecked(False)

    def _close_controls(self):
        if hasattr(self, "_ctrl_drawer"):
            self._ctrl_drawer.hide()
        if hasattr(self, "_ctrl_btn"):
            self._ctrl_btn.setChecked(False)

    def _place_drawer(self, drawer, left: int):
        _W = 220
        drawer.setFixedWidth(_W)
        drawer.adjustSize()
        drawer.setGeometry(left, 20, _W, drawer.sizeHint().height())

    def _position_quick_drawer(self):
        if hasattr(self, "_quick_drawer"):
            self._place_drawer(self._quick_drawer, _LEFT_W + 6)

    def _position_ctrl_drawer(self):
        # Under its own header button rather than under the other one's.
        if hasattr(self, "_ctrl_drawer"):
            left = _LEFT_W + 6
            self._place_drawer(self._ctrl_drawer, left)

    def _build_input_row(self) -> QHBoxLayout:
        row = QHBoxLayout(); row.setSpacing(8)
        row.setContentsMargins(0, 0, 0, 0)
        self._input = QLineEdit()
        self._input.setPlaceholderText("Talk to ORI or type a message…")
        self._input.setFont(QFont(UI_FONT, 11))
        self._input.setFixedHeight(40)
        self._input.setStyleSheet(f"""
            QLineEdit {{
                background: transparent; color: {C.WHITE};
                border: none; padding: 3px 4px;
                selection-background-color: {C.PRI_DIM};
            }}
        """)
        self._input.returnPressed.connect(self._send)
        row.addWidget(self._input)

        send = QPushButton("➤")
        send.setFixedSize(36, 36)
        send.setFont(QFont(UI_FONT, 11, QFont.Weight.Bold))
        send.setCursor(Qt.CursorShape.PointingHandCursor)
        send.setStyleSheet(f"""
            QPushButton {{
                background: rgba(4, 20, 10, 220); color: {C.PRI};
                border: 1px solid {C.BORDER_B}; border-radius: 2px;
            }}
            QPushButton:hover {{ background: {C.PRI_DIM}; color: {C.BG}; border: 1px solid {C.PRI}; }}
        """)
        send.clicked.connect(self._send)
        row.addWidget(send)
        return row

    def _build_content_panel(self) -> QWidget:
        """
        Collapsible panel below the HUD — shows search results, news, briefings.
        Hidden by default; appears when show_content() is called.
        """
        w = QWidget()
        w.setObjectName("ContentPanel")
        w.setStyleSheet(f"""
            QWidget#ContentPanel {{
                background: {C.PANEL};
                border-top: 1px solid {C.BORDER_B};
            }}
        """)
        w.hide()

        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 7, 12, 8)
        lay.setSpacing(5)

        # ── header row ────────────────────────────────────���──────────────────
        hdr = QHBoxLayout(); hdr.setSpacing(6)

        dot = QLabel("◈")
        dot.setFont(QFont(UI_FONT, 9, QFont.Weight.Bold))
        dot.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        hdr.addWidget(dot)

        self._content_title_lbl = QLabel("BRIEFING")
        self._content_title_lbl.setFont(QFont(UI_FONT, 8, QFont.Weight.Bold))
        self._content_title_lbl.setStyleSheet(
            f"color: {C.PRI}; background: transparent; letter-spacing: 1px;"
        )
        hdr.addWidget(self._content_title_lbl)
        hdr.addStretch()

        self._content_ts_lbl = QLabel("")
        self._content_ts_lbl.setFont(QFont(UI_FONT, 7))
        self._content_ts_lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        hdr.addWidget(self._content_ts_lbl)

        dismiss = QPushButton("DISMISS  ✕")
        dismiss.setFont(QFont(UI_FONT, 7))
        dismiss.setFixedHeight(18)
        dismiss.setCursor(Qt.CursorShape.PointingHandCursor)
        dismiss.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.TEXT_DIM};
                border: 1px solid {C.BORDER}; border-radius: 2px; padding: 0 5px;
            }}
            QPushButton:hover {{ color: {C.TEXT}; border-color: {C.BORDER_B}; }}
        """)
        dismiss.clicked.connect(w.hide)
        hdr.addWidget(dismiss)
        lay.addLayout(hdr)

        # ── separator ─────────────────────────────────────────────────────────
        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER};"); lay.addWidget(sep)

        # ── text display ──────────────────────────────────────────────────────
        self._content_display = QTextEdit()
        self._content_display.setReadOnly(True)
        self._content_display.setFont(QFont(UI_FONT, 8))
        self._content_display.setMinimumHeight(60)
        self._content_display.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._content_display.setStyleSheet(f"""
            QTextEdit {{
                background: rgba(3, 10, 28, 150);
                color: {C.TEXT};
                border: 1px solid {C.BORDER};
                border-radius: 3px;
                padding: 6px 8px;
                selection-background-color: {C.PRI_GHO};
            }}
            QScrollBar:vertical {{
                background: {C.BG}; width: 6px; border: none;
            }}
            QScrollBar::handle:vertical {{
                background: {C.BORDER_B}; border-radius: 3px; min-height: 16px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0; border: none;
            }}
        """)
        lay.addWidget(self._content_display)

        return w

    def _show_content(self, title: str, text: str):
        """Slot — runs on Qt main thread. Updates and shows the content panel."""
        import time as _time
        self._content_title_lbl.setText(title.upper()[:48])
        self._content_ts_lbl.setText(_time.strftime("%H:%M:%S"))
        self._content_display.setPlainText(text)
        self._content_display.moveCursor(
            self._content_display.textCursor().MoveOperation.Start
        )
        first_show = not self._content_panel.isVisible()
        self._content_panel.show()
        if first_show:
            total = self._center_split.height()
            self._center_split.setSizes([max(total - 220, 120), 220])

    # ── document review ──────────────────────────────────────────────────────
    # Rendered as rich text into the content panel that already exists, rather
    # than into a panel of its own. A review is read, not clicked, so QTextEdit
    # gives scrolling, selection and copy for nothing, and the HUD gains no
    # widget it has to lay out. Severity decides colour and order here because
    # that is presentation; the plugin supplies no styling and knows no palette,
    # which is also what lets a re-theme repaint a review correctly.

    # Severity is marked by a symbol and a colour, not by a word. The findings
    # themselves are in the user's language, and "[SERIOUS]" sitting inside a
    # Turkish sentence is the kind of seam this project tries not to have —
    # while translating the tag would mean a table per language, which is worse.
    # A shape carries it in every language, and shape plus colour still reads
    # for someone who cannot separate red from amber. What the marks mean
    # arrives the way everything else does: ORI says it out loud.
    _REVIEW_MARKS = {"serious": ("RED", "▲"), "caution": ("ACC2", "●"), "note": ("PRI_DIM", "·")}

    @staticmethod
    def _esc(s) -> str:
        return (str(s or "").replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;").replace("\n", "<br>"))

    def _show_review(self, title: str, summary: str, findings, unclear):
        """Slot — Qt main thread. Lays a document review into the content panel."""
        e = self._esc
        parts = [f'<div style="color:{C.TEXT}; font-family:{UI_FONT};">']

        if summary:
            parts.append(
                f'<div style="color:{C.WHITE}; border-left:2px solid {C.PRI};'
                f' padding-left:8px; margin-bottom:10px;">{e(summary)}</div>')

        for f in (findings or []):
            key, mark = self._REVIEW_MARKS.get(f.get("severity"), ("PRI_DIM", "·"))
            colour = getattr(C, key)
            parts.append(f'<div style="margin-bottom:11px;">')
            parts.append(
                f'<span style="color:{colour}; font-weight:bold;">{mark}</span> '
                f'<span style="color:{C.WHITE}; font-weight:bold;">'
                f'{e(f.get("heading"))}</span>')
            if f.get("detail"):
                parts.append(f'<div style="margin-left:12px;">{e(f["detail"])}</div>')
            if f.get("quote"):
                # The document's own wording, visually separated from the
                # explanation so the two are never mistaken for each other.
                parts.append(
                    f'<div style="margin-left:12px; color:{C.TEXT_DIM};'
                    f' border-left:1px solid {C.BORDER}; padding-left:7px;">'
                    f'&ldquo;{e(f["quote"])}&rdquo;</div>')
            if f.get("suggestion"):
                parts.append(
                    f'<div style="margin-left:12px; color:{C.PRI};">'
                    f'&rarr; {e(f["suggestion"])}</div>')
            parts.append('</div>')

        if unclear:
            parts.append(
                f'<div style="margin-top:6px; border-top:1px solid {C.BORDER};'
                f' padding-top:7px; color:{C.TEXT_MED};">'
                'The document does not settle:</div>')
            for u in unclear:
                parts.append(
                    f'<div style="margin-left:12px; color:{C.TEXT_MED};">'
                    f'&middot; {e(u)}</div>')
        parts.append('</div>')

        import time as _time
        self.hud.glance(0.0, -0.85, hold=1.3)
        # Left as written, not upper-cased. The other content-panel titles are
        # the app's own English labels, but this one is the document's name in
        # the user's language, and str.upper() applies English casing rules to
        # it: Turkish "Sözleşmesi" comes back "SÖZLEŞMESI", having lost the
        # dotted capital İ. Python has no locale-aware upper to reach for, and
        # imposing one language's rules on all of them is the bug, not the fix.
        self._content_title_lbl.setText((title or "Document")[:48])
        self._content_ts_lbl.setText(_time.strftime("%H:%M:%S"))
        self._content_display.setHtml("".join(parts))
        self._content_display.moveCursor(
            self._content_display.textCursor().MoveOperation.Start)
        first_show = not self._content_panel.isVisible()
        self._content_panel.show()
        if first_show:
            total = self._center_split.height()
            self._center_split.setSizes([max(total - 260, 120), 260, 0])

    # ── quiz panel ───────────────────────────────────────────────────────────
    # An interactive twin of the content panel. The plugin only ever hands over
    # questions; everything about asking, marking and reporting happens here,
    # and the finished result is pushed back into the conversation the same way
    # a dropped file is — as a message ORI reads and responds to. That keeps
    # the tool call short (it returns the moment the board is up) and leaves the
    # talking to the assistant, in the user's own language.

    def _quiz_btn(self, text: str, primary: bool = False) -> QPushButton:
        b = QPushButton(text)
        b.setFont(QFont(UI_FONT, 8))
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setMinimumHeight(24)
        edge = C.BORDER_B if primary else C.BORDER
        col = C.PRI if primary else C.TEXT_MED
        b.setStyleSheet(f"""
            QPushButton {{
                background: {C.PANEL2}; color: {col};
                border: 1px solid {edge}; border-radius: 2px;
                padding: 3px 9px; text-align: left;
            }}
            QPushButton:hover {{ color: {C.WHITE}; border-color: {C.PRI_DIM}; }}
            QPushButton:disabled {{ color: {C.TEXT_DIM}; border-color: {C.BORDER}; }}
        """)
        return b

    def _build_quiz_panel(self) -> QWidget:
        w = QWidget()
        w.setObjectName("QuizPanel")
        w.setStyleSheet(f"""
            QWidget#QuizPanel {{
                background: {C.PANEL};
                border-top: 1px solid {C.BORDER_B};
            }}
        """)
        w.hide()

        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 7, 12, 8)
        lay.setSpacing(6)

        hdr = QHBoxLayout(); hdr.setSpacing(6)
        dot = QLabel("◈")
        dot.setFont(QFont(UI_FONT, 9, QFont.Weight.Bold))
        dot.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        hdr.addWidget(dot)

        self._quiz_title_lbl = QLabel("QUIZ")
        self._quiz_title_lbl.setFont(QFont(UI_FONT, 8, QFont.Weight.Bold))
        self._quiz_title_lbl.setStyleSheet(
            f"color: {C.PRI}; background: transparent; letter-spacing: 1px;")
        hdr.addWidget(self._quiz_title_lbl)
        hdr.addStretch()

        self._quiz_count_lbl = QLabel("")
        self._quiz_count_lbl.setFont(QFont(UI_FONT, 7))
        self._quiz_count_lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        hdr.addWidget(self._quiz_count_lbl)

        quit_btn = QPushButton("DISMISS  ✕")
        quit_btn.setFont(QFont(UI_FONT, 7))
        quit_btn.setFixedHeight(18)
        quit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        quit_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.TEXT_DIM};
                border: 1px solid {C.BORDER}; border-radius: 2px; padding: 0 5px;
            }}
            QPushButton:hover {{ color: {C.TEXT}; border-color: {C.BORDER_B}; }}
        """)
        quit_btn.clicked.connect(self._hide_quiz)
        hdr.addWidget(quit_btn)
        lay.addLayout(hdr)

        rule = QFrame(); rule.setFixedHeight(1)
        rule.setStyleSheet(f"background: {C.BORDER};")
        lay.addWidget(rule)

        self._quiz_q_lbl = QLabel("")
        self._quiz_q_lbl.setWordWrap(True)
        self._quiz_q_lbl.setFont(QFont(UI_FONT, 9))
        self._quiz_q_lbl.setStyleSheet(f"color: {C.WHITE}; background: transparent;")
        lay.addWidget(self._quiz_q_lbl)

        self._quiz_answers = QWidget()
        self._quiz_answers.setStyleSheet("background: transparent;")
        self._quiz_answers_lay = QVBoxLayout(self._quiz_answers)
        self._quiz_answers_lay.setContentsMargins(0, 2, 0, 0)
        self._quiz_answers_lay.setSpacing(4)
        lay.addWidget(self._quiz_answers)

        self._quiz_note_lbl = QLabel("")
        self._quiz_note_lbl.setWordWrap(True)
        self._quiz_note_lbl.setFont(QFont(UI_FONT, 8))
        self._quiz_note_lbl.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
        self._quiz_note_lbl.hide()
        lay.addWidget(self._quiz_note_lbl)

        foot = QHBoxLayout()
        foot.addStretch()
        self._quiz_next_btn = self._quiz_btn("NEXT  →", primary=True)
        self._quiz_next_btn.setFixedWidth(110)
        self._quiz_next_btn.clicked.connect(self._quiz_next)
        self._quiz_next_btn.hide()
        foot.addWidget(self._quiz_next_btn)
        lay.addLayout(foot)

        self._quiz = None
        return w

    def _show_quiz(self, topic: str, questions, grader=None):
        """Slot — Qt main thread. Puts a fresh quiz on the board."""
        if not questions:
            return
        self._quiz = {
            "topic": topic or "",
            "questions": list(questions),
            "grader": grader,
            "i": 0,
            "results": [],
            "answered": False,
        }
        self._quiz_title_lbl.setText((topic or "quiz").upper()[:48])
        self.hud.glance(0.0, -0.85, hold=1.3)
        first_show = not self._quiz_panel.isVisible()
        self._quiz_panel.show()
        if first_show:
            total = self._center_split.height()
            self._center_split.setSizes([max(total - 250, 120), 0, 250])
        self._quiz_render()

    def _hide_quiz(self):
        self._quiz = None
        self._quiz_panel.hide()

    def _quiz_clear_answers(self):
        while self._quiz_answers_lay.count():
            item = self._quiz_answers_lay.takeAt(0)
            child = item.widget()
            if child is not None:
                child.setParent(None)
                child.deleteLater()

    def _quiz_render(self):
        q = self._quiz["questions"][self._quiz["i"]]
        n, total = self._quiz["i"] + 1, len(self._quiz["questions"])
        self._quiz_count_lbl.setText(f"{n} / {total}")
        self._quiz_q_lbl.setText(q.get("question", ""))
        self._quiz_note_lbl.hide()
        self._quiz_next_btn.hide()
        self._quiz["answered"] = False
        self._quiz_clear_answers()

        opts = q.get("options") or []
        if opts:
            for text in opts:
                b = self._quiz_btn("   " + text)
                b.clicked.connect(lambda _=False, t=text: self._quiz_submit(t))
                self._quiz_answers_lay.addWidget(b)
        else:
            row = QWidget(); row.setStyleSheet("background: transparent;")
            h = QHBoxLayout(row); h.setContentsMargins(0, 0, 0, 0); h.setSpacing(6)
            field = QLineEdit()
            field.setFont(QFont(UI_FONT, 9))
            field.setPlaceholderText("your answer")
            field.setStyleSheet(f"""
                QLineEdit {{
                    background: {C.PANEL2}; color: {C.WHITE};
                    border: 1px solid {C.BORDER}; border-radius: 2px; padding: 4px 7px;
                }}
                QLineEdit:focus {{ border-color: {C.PRI_DIM}; }}
            """)
            send = self._quiz_btn("ANSWER", primary=True)
            send.setFixedWidth(90)
            field.returnPressed.connect(lambda: self._quiz_submit(field.text()))
            send.clicked.connect(lambda: self._quiz_submit(field.text()))
            h.addWidget(field, stretch=1)
            h.addWidget(send)
            self._quiz_answers_lay.addWidget(row)
            field.setFocus()

    def _quiz_submit(self, given: str):
        if self._quiz is None or self._quiz["answered"]:
            return
        self._quiz["answered"] = True
        q = self._quiz["questions"][self._quiz["i"]]
        grader = self._quiz.get("grader")
        verdict = None
        if callable(grader):
            try:
                verdict = grader(q, given)
            except Exception:
                verdict = None
        self._quiz["results"].append({
            "question": q.get("question", ""),
            "type": q.get("type", ""),
            "given": str(given or "").strip(),
            "answer": q.get("answer", ""),
            "correct": verdict,
        })

        for i in range(self._quiz_answers_lay.count()):
            wdg = self._quiz_answers_lay.itemAt(i).widget()
            if wdg is not None:
                wdg.setEnabled(False)

        if verdict is True:
            mark, colour = "✓  correct", C.GREEN
        elif verdict is False:
            mark, colour = "✕  " + str(q.get("answer", "")), C.RED
        else:
            # Open answers and near-miss gap-fills are ORI's to judge. Saying
            # so is honest; marking it wrong here would be a guess.
            mark, colour = "…  noted — I'll go over this one with you", C.ACC2
        note = q.get("note") or ""
        self._quiz_note_lbl.setText(mark + (("\n" + note) if note else ""))
        self._quiz_note_lbl.setStyleSheet(f"color: {colour}; background: transparent;")
        self._quiz_note_lbl.show()

        last = self._quiz["i"] >= len(self._quiz["questions"]) - 1
        self._quiz_next_btn.setText("FINISH  →" if last else "NEXT  →")
        self._quiz_next_btn.show()
        self._quiz_next_btn.setFocus()

    def _quiz_next(self):
        if self._quiz is None:
            return
        if self._quiz["i"] >= len(self._quiz["questions"]) - 1:
            self._quiz_finish()
        else:
            self._quiz["i"] += 1
            self._quiz_render()

    def _quiz_finish(self):
        if self._quiz is None:
            return
        topic = self._quiz["topic"]
        results = self._quiz["results"]
        right = sum(1 for r in results if r["correct"] is True)
        unsure = sum(1 for r in results if r["correct"] is None)
        total = len(results)
        self._quiz_panel.hide()
        self._quiz = None

        self._log.append_log(f"QUIZ: {topic or 'quiz'} — {right}/{total} correct")

        # Hand it back to ORI as a message, not as a tool return: the tool
        # call ended minutes ago. This is the same channel a dropped file uses.
        lines = [f"[QUIZ_DONE] topic={topic or 'general'} | "
                 f"auto-marked {right}/{total} correct"
                 + (f", {unsure} still need your marking" if unsure else "")]
        for i, r in enumerate(results, 1):
            state = ("correct" if r["correct"] is True
                     else "wrong" if r["correct"] is False else "NEEDS MARKING")
            lines.append(
                f"{i}. [{r['type']}] {r['question']} | they answered: "
                f"{r['given'] or '(blank)'} | expected: {r['answer']} | {state}")
        lines.append(
            "Mark every question flagged NEEDS MARKING yourself — accept an answer "
            "that means the same thing. Then tell them how they did in their own "
            "language: the score, what they got wrong and why, in a couple of "
            "sentences. Offer another round only if it fits. "
            "Remember something only if it would still matter next week — that they "
            "are working through a subject, or keep missing the same thing. A score "
            "from one session is not worth a memory, and a memory per quiz would "
            "bury the things that are.")
        msg = "\n".join(lines)
        if self.on_text_command:
            threading.Thread(target=self.on_text_command, args=(msg,), daemon=True).start()

    def _build_footer(self) -> QWidget:
        w = QFrame()
        w.setObjectName("TerminalFooter")
        w.setFixedHeight(31)
        w.setStyleSheet(f"QFrame#TerminalFooter {{ background: rgba(0, 4, 2, 225); border-top: 1px solid {C.BORDER}; }}")
        lay = QHBoxLayout(w)
        lay.setContentsMargins(20, 0, 20, 0)
        left = QLabel("F4  MUTE MIC     ·     ESC  INTERRUPT     ·     F11  FULLSCREEN")
        left.setFont(QFont(UI_FONT, 7, QFont.Weight.Bold))
        left.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        lay.addWidget(left)
        lay.addStretch(1)
        right = QLabel("ORI 3.5.0 // LIVE DESKTOP")
        right.setFont(QFont(UI_FONT, 7, QFont.Weight.Bold))
        right.setStyleSheet(f"color: {C.PRI_DIM}; background: transparent;")
        lay.addWidget(right)
        return w

    def _on_file_selected(self, path: str):
        self._current_file = path
        p    = Path(path)
        cat  = _file_category(p)
        icon, _ = _FILE_ICONS.get(cat, _FILE_ICONS["unknown"])
        size = _fmt_size(p.stat().st_size)
        self._file_hint.setText(f"{icon}  {p.name}  ·  {size}  ·  Tell {self._assistant_name} what to do with it")
        self._log.append_log(f"FILE: {p.name} ({size}) loaded")
        if self.on_text_command:
            msg = (
                f"[FILE_UPLOADED] path={path} | name={p.name} | "
                f"type={p.suffix.lstrip('.')} | size={size} | "
                f"Briefly tell the user you can see the file '{p.name}' "
                f"({size}) has been uploaded and ask what they'd like to do with it."
            )
            threading.Thread(target=self.on_text_command, args=(msg,), daemon=True).start()

    def set_muted_from_remote(self, muted: bool | None = None) -> bool:
        """Thread-safe remote microphone control for the MainWindow.

        This method lives on MainWindow; the JarvisUI facade below exposes a
        matching forwarding method for DashboardServer.
        """
        if muted is None:
            return bool(self._muted)
        self._remote_mute_sig.emit(bool(muted))
        return bool(muted)

    def notify_phone_connected(self) -> None:
        """Thread-safe notification that a paired phone has connected."""
        self._remote_connected_sig.emit()

    def _apply_phone_connected(self) -> None:
        if self._remote_overlay and self._remote_overlay.isVisible():
            self._remote_overlay.mark_connected()

    def _open_remote(self):
        if not self.on_remote_clicked:
            self._log.append_log("SYS: Phone dashboard is unavailable. Check the local remote server status in Settings.")
            return
        result = self.on_remote_clicked()
        if not result:
            self._log.append_log("SYS: Could not generate remote key. The dashboard must be fully started and a LAN address must be available.")
            return
        url    = result[0]
        key    = result[1]
        auto   = result[2] if len(result) >= 3 else ""
        manual = result[3] if len(result) >= 4 else url
        if self._remote_overlay:
            self._remote_overlay._do_close()
        cw  = self.centralWidget()
        ow, oh = RemoteKeyOverlay._OW, RemoteKeyOverlay._OH
        ov  = RemoteKeyOverlay(url, key, auto_login_url=auto, manual_url=manual,
                               expiry_secs=600, parent=cw)
        ov.set_new_key_callback(self.on_remote_clicked)
        ov.setGeometry(
            (cw.width()  - ow) // 2,
            (cw.height() - oh) // 2,
            ow, oh,
        )
        ov.closed.connect(lambda: setattr(self, '_remote_overlay', None))
        ov.show()
        self._remote_overlay = ov
        self._log.append_log(f"SYS: Remote key generated — manual: {manual or url}")

    # ── Settings-page remote helpers ────────────────────────────────────────────

    def _settings_open_remote(self) -> None:
        """Called by the SHOW QR CODE button in Settings → 12 / PHONE REMOTE CONTROL."""
        if not self.on_remote_clicked:
            if hasattr(self, "_remote_status_lbl"):
                self._remote_status_lbl.setText(
                    "Dashboard not running yet — wait a moment, then try again."
                )
                self._remote_status_lbl.setStyleSheet(
                    f"color: {C.RED}; background: transparent;"
                )
            return
        result = self.on_remote_clicked()
        if not result:
            detail = str(getattr(self, "_remote_status_detail", "") or "Dashboard is not ready yet.")
            if hasattr(self, "_remote_status_lbl"):
                self._remote_status_lbl.setText(
                    "REMOTE NOT READY · " + detail[:240]
                )
                self._remote_status_lbl.setStyleSheet(
                    f"color: {C.RED}; background: transparent;"
                )
            return
        url    = result[0]
        key    = result[1]
        auto   = result[2] if len(result) >= 3 else ""
        manual = result[3] if len(result) >= 4 else url
        # Update Settings status labels
        if hasattr(self, "_remote_status_lbl"):
            self._remote_status_lbl.setText(
                "QR CODE READY · Scan with your phone camera. Link expires in 10 minutes."
            )
            self._remote_status_lbl.setStyleSheet(
                f"color: {C.PRI}; background: transparent;"
            )
        if hasattr(self, "_remote_url_lbl"):
            self._remote_url_lbl.setText(auto or url)
        # Also show the floating QR overlay (same as before)
        if self._remote_overlay:
            self._remote_overlay._do_close()
        cw  = self.centralWidget()
        ow, oh = RemoteKeyOverlay._OW, RemoteKeyOverlay._OH
        ov  = RemoteKeyOverlay(url, key, auto_login_url=auto, manual_url=manual,
                               expiry_secs=600, parent=cw)
        ov.set_new_key_callback(self.on_remote_clicked)
        ov.setGeometry(
            (cw.width()  - ow) // 2,
            (cw.height() - oh) // 2,
            ow, oh,
        )
        ov.closed.connect(lambda: setattr(self, "_remote_overlay", None))
        ov.show()
        self._remote_overlay = ov
        self._log.append_log(f"SYS: Remote key generated — scan QR or visit {manual or url}")

    def _settings_copy_remote_link(self) -> None:
        """Copy the active dashboard URL without generating a new pairing key."""
        url = self._remote_url_lbl.text().strip() if hasattr(self, "_remote_url_lbl") else ""
        if not url or url in ("—", "Not available", "Not paired"):
            if hasattr(self, "_settings_page_status"):
                self._settings_page_status.setText("Pair your phone first to create a local dashboard link.")
            return
        # The label contains the same one-time auto-login URL encoded in the QR.
        # It expires after ten minutes and must only be shared with a trusted phone.
        QApplication.clipboard().setText(url)
        if hasattr(self, "_settings_page_status"):
            self._settings_page_status.setText("ONE-TIME PHONE LINK COPIED · Share only with your paired device.")

    def update_remote_settings_status(
        self, url: str, running: bool = True, detail: str = ""
    ) -> None:
        """Thread-safe entry point for dashboard readiness and startup errors."""
        self._remote_status_sig.emit(str(url or ""), bool(running), str(detail or ""))

    def _apply_remote_settings_status(self, url: str, running: bool, detail: str = "") -> None:
        """Update the Settings page only on the Qt UI thread."""
        self._remote_dashboard_running = bool(running)
        self._remote_status_detail = str(detail or ("Dashboard is starting…" if not running else ""))
        if hasattr(self, "_remote_status_lbl"):
            if running:
                self._remote_status_lbl.setText("LOCAL DASHBOARD READY · Pair your phone on the same Wi-Fi.")
                self._remote_status_lbl.setStyleSheet(f"color: {C.GREEN}; background: transparent;")
            else:
                self._remote_status_lbl.setText("REMOTE NOT READY · " + self._remote_status_detail[:240])
                self._remote_status_lbl.setStyleSheet(f"color: {C.ACC}; background: transparent;")
        if hasattr(self, "_remote_url_lbl"):
            if running and url:
                self._remote_url_lbl.setText(url)
            elif not running:
                self._remote_url_lbl.setText("Not available")

    # ── Auto-start ──────────────────────────────────────────────────────────────

    def _check_autostart(self) -> bool:
        """Returns True if auto-start is currently registered on this OS."""
        try:
            if _OS == "Windows":
                import winreg
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_READ)
                try:
                    winreg.QueryValueEx(key, "ORI_AI")
                    return True
                except FileNotFoundError:
                    return False
                finally:
                    winreg.CloseKey(key)
            elif _OS == "Darwin":
                return (Path.home() / "Library" / "LaunchAgents"
                        / "com.jarvis.assistant.plist").exists()
            else:
                return (Path.home() / ".config" / "autostart" / "jarvis.desktop").exists()
        except Exception:
            return False

    def _toggle_autostart(self):
        currently_on = self._check_autostart()
        try:
            script = str(Path(__file__).resolve().parent / "main.py")
            if _OS == "Windows":
                import winreg
                reg = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_ALL_ACCESS)
                if currently_on:
                    winreg.DeleteValue(reg, "ORI_AI")
                else:
                    pythonw = Path(sys.executable).parent / "pythonw.exe"
                    exe = str(pythonw if pythonw.exists() else sys.executable)
                    winreg.SetValueEx(reg, "ORI_AI", 0, winreg.REG_SZ,
                                      f'"{exe}" "{script}"')
                winreg.CloseKey(reg)
            elif _OS == "Darwin":
                plist_dir = Path.home() / "Library" / "LaunchAgents"
                plist_dir.mkdir(parents=True, exist_ok=True)
                plist = plist_dir / "com.jarvis.assistant.plist"
                if currently_on:
                    plist.unlink(missing_ok=True)
                else:
                    plist.write_text(
                        '<?xml version="1.0" encoding="UTF-8"?>\n'
                        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
                        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
                        '<plist version="1.0"><dict>\n'
                        '  <key>Label</key><string>com.jarvis.assistant</string>\n'
                        '  <key>ProgramArguments</key><array>\n'
                        f'    <string>{sys.executable}</string>\n'
                        f'    <string>{script}</string>\n'
                        '  </array>\n'
                        '  <key>RunAtLoad</key><true/>\n'
                        '</dict></plist>\n'
                    )
            else:
                desk_dir = Path.home() / ".config" / "autostart"
                desk_dir.mkdir(parents=True, exist_ok=True)
                desk = desk_dir / "jarvis.desktop"
                if currently_on:
                    desk.unlink(missing_ok=True)
                else:
                    desk.write_text(
                        "[Desktop Entry]\n"
                        f"Name={self._assistant_name}\n"
                        f"Exec={sys.executable} {script}\n"
                        "Type=Application\nTerminal=false\n"
                        "X-GNOME-Autostart-enabled=true\n"
                    )
            enabled = not currently_on
            self._update_autostart_btn(enabled)
            self._log.append_log(
                f"SYS: Auto-start {'enabled' if enabled else 'disabled'}.")
        except Exception as e:
            self._log.append_log(f"ERR: Auto-start failed — {e}")

    def _update_autostart_btn(self, enabled: bool):
        if not hasattr(self, '_autostart_btn'):
            return
        if enabled:
            self._autostart_btn.setText("◉  AUTO-START: ON")
            self._autostart_btn.setStyleSheet(f"""
                QPushButton {{
                    background: #001a08; color: {C.GREEN};
                    border: 1px solid {C.GREEN_D}; border-radius: 3px;
                }}
                QPushButton:hover {{ background: #002010; }}
            """)
        else:
            self._autostart_btn.setText("◉  AUTO-START: OFF")
            self._autostart_btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; color: {C.TEXT_DIM};
                    border: 1px solid {C.BORDER}; border-radius: 3px;
                }}
                QPushButton:hover {{ color: {C.TEXT}; border: 1px solid {C.BORDER_B}; }}
            """)

    def _toggle_brief(self):
        from memory.config_manager import get_brief_enabled, save_brief_enabled
        new_val = not get_brief_enabled()
        save_brief_enabled(new_val)
        self._update_brief_btn(new_val)

    # ── Wake word settings ───────────────────────────────────────────────────

    def _wake_state(self) -> dict:
        """Combined state for the two wake-word buttons. Readiness is a cheap,
        deterministic on-disk check now (see core.wake_word.is_ready), so there
        is nothing to cache — the button never flickers to a stale value."""
        if self.wake_get_state:
            try:
                s = self.wake_get_state()
                return {"ready": bool(s.get("ready")),
                        "enabled": bool(s.get("enabled")),
                        "awake": bool(s.get("awake"))}
            except Exception:
                pass
        # Before JarvisLive has wired its callback (drawer built at startup).
        ready, enabled = False, False
        try:
            from core.wake_word import is_ready
            from memory.config_manager import get_wake_word_enabled
            ready, enabled = is_ready(), get_wake_word_enabled()
        except Exception:
            pass
        return {"ready": ready, "enabled": enabled, "awake": True}

    def _refresh_wake_btns(self):
        if not hasattr(self, '_wake_btn'):
            return
        st = self._wake_state()
        _on = f"""
            QPushButton {{ background: #001a08; color: {C.GREEN};
                border: 1px solid {C.GREEN_D}; border-radius: 3px;
                text-align: left; padding: 0 8px; }}
            QPushButton:hover {{ background: #002010; }}"""
        _off = f"""
            QPushButton {{ background: transparent; color: {C.TEXT_DIM};
                border: 1px solid {C.BORDER}; border-radius: 3px;
                text-align: left; padding: 0 8px; }}
            QPushButton:hover {{ color: {C.TEXT}; border: 1px solid {C.BORDER_B}; }}"""
        self._wake_btn.setEnabled(True)
        if not st["ready"]:
            self._wake_btn.setText("⬇  WAKE WORD: DOWNLOAD")
            self._wake_btn.setStyleSheet(_off)
            self._wake_sleep_btn.hide()
        elif st["enabled"]:
            self._wake_btn.setText("🎙  WAKE WORD: ON")
            self._wake_btn.setStyleSheet(_on)
            self._wake_sleep_btn.show()
            self._wake_sleep_btn.setText("😴  SLEEP NOW" if st["awake"] else "👂  WAKE NOW")
            self._wake_sleep_btn.setStyleSheet(_off)
        else:
            self._wake_btn.setText("🎙  WAKE WORD: OFF")
            self._wake_btn.setStyleSheet(_off)
            self._wake_sleep_btn.hide()

    def _refresh_talk_btns(self):
        """Repaint the push-to-talk row from the saved setting."""
        if not hasattr(self, "_ptt_btn"):
            return
        from core.hotkey import chord_label
        from memory.config_manager import get_push_to_talk_enabled
        _on = f"""
            QPushButton {{ background: #001a08; color: {C.GREEN};
                border: 1px solid {C.GREEN_D}; border-radius: 3px;
                text-align: left; padding: 0 8px; }}
            QPushButton:hover {{ background: #002010; }}"""
        _off = f"""
            QPushButton {{ background: transparent; color: {C.TEXT_DIM};
                border: 1px solid {C.BORDER}; border-radius: 3px;
                text-align: left; padding: 0 8px; }}
            QPushButton:hover {{ color: {C.TEXT}; border: 1px solid {C.BORDER_B}; }}"""

        ptt = get_push_to_talk_enabled()
        self._ptt_btn.setText(f"🎚  PUSH-TO-TALK: {chord_label()}" if ptt
                              else "🎚  PUSH-TO-TALK: OFF")
        self._ptt_btn.setStyleSheet(_on if ptt else _off)
        self._ptt_btn.setToolTip(
            "Microphone stays closed until you hold the key — nothing is sent "
            "while you are not holding it." if ptt
            else "Hold a key to talk instead of streaming the mic continuously.")


    def _toggle_ptt(self):
        from memory.config_manager import (get_push_to_talk_enabled,
                                           save_push_to_talk_enabled)
        want = not get_push_to_talk_enabled()
        save_push_to_talk_enabled(want)
        scope = None
        if self.on_push_to_talk:
            try:
                scope = self.on_push_to_talk(want)
            except Exception as e:
                self._log.append_log(f"ERR: Push-to-talk failed — {e}")
                save_push_to_talk_enabled(False)
                want = False
        self._apply_ptt_shortcut(want and scope != "global")
        self._refresh_talk_btns()

    def _apply_ptt_shortcut(self, needed: bool):
        """Bind the chord inside the window when no global hook is available.

        On macOS and Linux there is no dependency-free way to read global key
        state, so the chord is at least live whenever this window has focus.
        Qt gives no key-release for a QShortcut, so a press latches the mic open
        and a short timer closes it; held down, auto-repeat keeps pushing that
        timer out, which behaves like holding a key.
        """
        from PyQt6.QtGui import QKeySequence, QShortcut
        from core.hotkey import qt_sequence

        if not needed:
            sc = getattr(self, "_ptt_sc", None)
            if sc is not None:
                sc.setEnabled(False)
                self._ptt_sc = None
            self._ptt_hold(False)
            return
        if getattr(self, "_ptt_sc", None) is not None:
            return

        self._ptt_release = QTimer(self)
        self._ptt_release.setSingleShot(True)
        self._ptt_release.setInterval(420)
        self._ptt_release.timeout.connect(lambda: self._ptt_hold(False))

        def _press():
            self._ptt_hold(True)
            self._ptt_release.start()

        self._ptt_sc = QShortcut(QKeySequence(qt_sequence()), self)
        self._ptt_sc.setAutoRepeat(True)
        self._ptt_sc.activated.connect(_press)

    def _ptt_hold(self, held: bool):
        """Report a windowed press/release to whoever owns the microphone."""
        cb = getattr(self, "ptt_hold", None)
        if cb:
            try:
                cb(bool(held))
            except Exception:
                pass

    def _toggle_wake_word(self):
        st = self._wake_state()
        if not st["ready"]:
            # First time: download openwakeword + model in a worker thread.
            self._wake_btn.setText("⬇  DOWNLOADING… (one-time)")
            self._wake_btn.setEnabled(False)
            def _work():
                try:
                    from core.wake_word import install_and_download
                    ok, msg = install_and_download(
                        logger=lambda m: self._log_sig.emit(f"SYS: {m}"))
                except Exception as e:
                    ok, msg = False, str(e)
                if ok and self.on_wake_toggle:
                    try:
                        self.on_wake_toggle(True)   # auto-enable after a successful download
                    except Exception:
                        pass
                self._wake_dl_sig.emit(ok, msg)
            threading.Thread(target=_work, daemon=True).start()
            return
        # Already downloaded → just flip enabled/disabled through JarvisLive.
        if self.on_wake_toggle:
            try:
                self.on_wake_toggle(not st["enabled"])
            except Exception:
                pass
        self._refresh_wake_btns()

    def _on_wake_install_done(self, ok: bool, msg: str):
        self._log_sig.emit(f"SYS: {'Wake word ready.' if ok else 'Wake word setup failed: ' + msg}")
        self._refresh_wake_btns()

    def _tap_wake_manual(self):
        if self.on_wake_manual:
            try:
                self.on_wake_manual()
            except Exception:
                pass
        self._refresh_wake_btns()

    def _update_brief_btn(self, enabled: bool):
        if not hasattr(self, '_brief_btn'):
            return
        if enabled:
            self._brief_btn.setText("☀  MORNING BRIEF: ON")
            self._brief_btn.setStyleSheet(f"""
                QPushButton {{
                    background: #001a08; color: {C.GREEN};
                    border: 1px solid {C.GREEN_D}; border-radius: 3px;
                    text-align: left; padding: 0 8px;
                }}
                QPushButton:hover {{ background: #002010; }}
            """)
        else:
            self._brief_btn.setText("☀  MORNING BRIEF: OFF")
            self._brief_btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; color: {C.TEXT_DIM};
                    border: 1px solid {C.BORDER}; border-radius: 3px;
                    text-align: left; padding: 0 8px;
                }}
                QPushButton:hover {{ color: {C.TEXT}; border: 1px solid {C.BORDER_B}; }}
            """)

    # ── Customization ────────────────────────────────────────────────────────────

    def _open_customize(self):
        cfg = _read_full_config()
        if self._customize_overlay:
            self._customize_overlay.hide()
        cw = self.centralWidget()
        ov = CustomizeOverlay(
            cfg.get("assistant_name", "ORI") or "ORI",
            cfg.get("user_name", ""),
            cfg.get("ui_color", "") or DEFAULT_UI_COLOR,
            cfg.get("voice_name", ""),
            parent=cw,
        )
        ow, oh = CustomizeOverlay._OW, CustomizeOverlay._OH
        oh = min(oh, cw.height() - 16)
        ov.setGeometry(
            (cw.width()  - ow) // 2,
            (cw.height() - oh) // 2,
            ow, oh,
        )
        ov.on_preview = self._preview_ui_color
        ov.saved.connect(self._apply_name_update)
        ov.show()
        self._customize_overlay = ov

    def _preview_ui_color(self, hex_color: str):
        """Live preview — paints the whole interface the new colour (does NOT write to config)."""
        old = current_palette()
        if apply_ui_accent(hex_color):
            retheme_all_widgets(old, current_palette())

    def _apply_name_update(self, name: str, user_name: str, ui_color: str = "",
                           voice: str = ""):
        """Update all name/theme-dependent UI elements and persist to config."""
        self._assistant_name = "ORI"
        display = self._assistant_name.upper()
        self.setWindowTitle(f"{display} — {APP_VERSION}")
        self._title_lbl.setText(display)
        self._sub_lbl.setText("PERSONAL AI DESKTOP SYSTEM")
        self._log._ai_name_lc = self._assistant_name.lower()
        self.hud._assistant_name = display

        color_changed = False
        if ui_color:
            old = current_palette()
            if apply_ui_accent(ui_color):
                # Live-paint the whole interface (panels, buttons, borders, HUD)
                retheme_all_widgets(old, current_palette())
                color_changed = old["PRI"] != C.PRI

        # Voice change → persist and, if it actually changed, rebuild the Live
        # session so the new voice takes effect (it's fixed at connect time).
        voice_changed = False
        if voice:
            from memory.config_manager import get_voice, save_voice
            if voice != get_voice():
                save_voice(voice)
                voice_changed = True

        try:
            data = _read_full_config()
            data["assistant_name"] = "ORI"
            data["user_name"] = user_name.strip()
            if ui_color:
                data["ui_color"] = ui_color.strip().lower()
            API_FILE.write_text(json.dumps(data, indent=4), encoding="utf-8")
            self._log.append_log(f"SYS: Identity updated — {display}")
            if color_changed:
                self._log.append_log(f"SYS: UI colour applied — {ui_color}")
            if voice_changed:
                self._log.append_log(f"SYS: Voice set — {voice}")
        except Exception as e:
            self._log.append_log(f"ERR: Config save failed — {e}")

        if voice_changed and self.on_voice_change:
            self.on_voice_change()

    def _centre_overlay(self, ov) -> None:
        """Place a floating overlay in the middle of the HUD and show it."""
        cw = self.centralWidget()
        ov.adjustSize()
        ov.setGeometry(
            max(0, (cw.width()  - ov.width())  // 2),
            max(0, (cw.height() - ov.height()) // 2),
            ov.width(), ov.height(),
        )
        ov.show()
        ov.raise_()

    # ── Audio devices ────────────────────────────────────────────────────────

    def _open_audio_devices(self):
        ov = AudioDeviceOverlay(parent=self.centralWidget())
        ov.picked.connect(self._on_audio_devices_applied)
        self._centre_overlay(ov)
        self._audio_overlay = ov            # keep a reference so it isn't GC'd

    def _on_audio_devices_applied(self):
        self._log.append_log("SYS: Audio devices updated.")
        if self.on_audio_device_change:
            self.on_audio_device_change()

    # ── Memory panel ─────────────────────────────────────────────────────────

    def _open_memory_panel(self):
        ov = MemoryOverlay(parent=self.centralWidget())
        self._centre_overlay(ov)
        self._memory_overlay = ov

    # ── Irreversible-action confirmation ─────────────────────────────────────

    def _show_confirm_banner(self, title: str, detail: str):
        self._hide_confirm_banner()
        ov = ConfirmBanner(title, detail, parent=self.centralWidget())
        ov.answered.connect(self._on_confirm_answered)
        self._centre_overlay(ov)
        self._confirm_overlay = ov

    def _hide_confirm_banner(self):
        ov = getattr(self, "_confirm_overlay", None)
        if ov is not None:
            ov.hide()
            ov.deleteLater()
            self._confirm_overlay = None

    def _on_confirm_answered(self, accepted: bool):
        # Tear the banner down first: core.confirm.resolve() may be about to
        # shut the machine down, and a live widget mid-callback is not where you
        # want to be when that happens.
        self._hide_confirm_banner()
        try:
            from core.confirm import resolve
            resolve(bool(accepted))
        except Exception as e:
            self._log.append_log(f"ERR: Confirmation failed — {e}")

    def _open_plugin_manager(self):
        plugins = self.get_plugins() if self.get_plugins else []
        cw = self.centralWidget()
        ov = PluginManagerOverlay(plugins, parent=cw)
        ov.adjustSize()
        ov.setGeometry(
            (cw.width()  - ov.width())  // 2,
            (cw.height() - ov.height()) // 2,
            ov.width(), ov.height(),
        )
        ov.show()
        ov.raise_()
        self._plugin_manager_overlay = ov   # keep a reference so it isn't GC'd

    def _open_plugin_settings(self):
        sections = self.get_plugin_settings() if self.get_plugin_settings else []
        cw = self.centralWidget()
        ov = PluginSettingsOverlay(sections, parent=cw)
        ow = PluginSettingsOverlay._OW
        oh = min(560, cw.height() - 16)
        ov.setGeometry(
            (cw.width()  - ow) // 2,
            (cw.height() - oh) // 2,
            ow, oh,
        )
        ov.show()
        ov.raise_()
        self._plugin_settings_overlay = ov   # keep a reference so it isn't GC'd

    # ── Clipboard intelligence ───────────────────────────────────────────────────

    def _on_clipboard_changed(self):
        try:
            text = QApplication.clipboard().text().strip()
            if len(text) >= 10:
                self._clipboard_sig.emit(text)
        except Exception:
            pass

    def _show_clipboard_panel(self, text: str):
        self._clipboard_panel.show_clipboard(text)
        self._position_clipboard_panel()

    def _position_clipboard_panel(self):
        cw = self.centralWidget()
        pw = ClipboardPanel._W
        ph = self._clipboard_panel.sizeHint().height() or ClipboardPanel._H
        x = (cw.width() - pw) // 2
        y = cw.height() - ph - 6
        self._clipboard_panel.setGeometry(x, y, pw, ph)
        self._clipboard_panel.raise_()

    def _on_clipboard_action(self, cmd: str):
        if self.on_text_command:
            threading.Thread(target=self.on_text_command, args=(cmd,), daemon=True).start()

    # ────────────────────────────────────────────────────────────────────────────

    
    def _do_interrupt(self):
        if self.on_interrupt:
            self.on_interrupt()

    def _toggle_mute(self):
        # A deliberate press settles the question: whatever the video did, or is
        # about to do, the user has now said what they want.
        self._video_auto_muted = False
        self._set_muted(not self._muted)

    def _set_muted(self, muted: bool, note: str = ""):
        muted = bool(muted)
        if muted == self._muted:
            return
        self._muted = muted
        self.hud.muted = muted
        self._apply_access_indicator("mic", not muted)
        self._style_mute_btn()
        if muted:
            self._apply_state("MUTED")
            self._log.append_log("SYS: Microphone muted." + (f" {note}" if note else ""))
            state = "MIC MUTED"
        else:
            self._apply_state("LISTENING")
            self._log.append_log("SYS: Microphone active." + (f" {note}" if note else ""))
            state = "LISTENING"
        # Also publish mute changes to the authenticated phone dashboard so
        # its system status does not remain stale while the desktop mic is muted.
        notify = getattr(self, "_activity_publish", None)
        if callable(notify):
            try:
                notify(state)
            except Exception:
                pass

    def _style_mute_btn(self):
        _mic_icon = CONFIG_DIR / ("microphone-muted.svg" if self._muted else "microphone-on.svg")
        if _mic_icon.exists():
            _mic_qicon = QIcon(str(_mic_icon))
            for _target in (getattr(self, "_mute_btn", None), getattr(self, "_home_mute_btn", None)):
                if _target is not None:
                    _target.setIcon(_mic_qicon)
                    _target.setIconSize(QSize(16, 16))
        if self._muted:
            self._mute_btn.setText("MICROPHONE MUTED")
            self._mute_btn.setStyleSheet(f"""
                QPushButton {{ background: #140006; color: {C.MUTED_C};
                    border: 1px solid {C.MUTED_C}; border-radius: 3px; }}
            """)
            if hasattr(self, "_home_mute_btn"):
                self._home_mute_btn.setText("UNMUTE MIC")
                self._home_mute_btn.setStyleSheet(f"""
                    QPushButton {{ color: {C.MUTED_C}; background: rgba(22, 0, 8, 210);
                        border: 1px solid {C.MUTED_C}; border-radius: 2px; padding: 0 6px; }}
                    QPushButton:hover {{ background: rgba(50, 0, 15, 230); }}
                """)
                self._home_mute_btn.setToolTip("Microphone is muted. Click to unmute (F4).")
        else:
            self._mute_btn.setText("MICROPHONE ACTIVE")
            self._mute_btn.setStyleSheet(f"""
                QPushButton {{ background: #00140a; color: {C.GREEN};
                    border: 1px solid {C.GREEN}; border-radius: 3px; }}
                QPushButton:hover {{ background: #001f10; }}
            """)
            if hasattr(self, "_home_mute_btn"):
                self._home_mute_btn.setText("MUTE MIC")
                self._home_mute_btn.setStyleSheet(f"""
                    QPushButton {{ color: {C.PRI}; background: rgba(3, 20, 10, 210);
                        border: 1px solid {C.BORDER_B}; border-radius: 2px; padding: 0 6px; }}
                    QPushButton:hover {{ color: {C.WHITE}; background: {C.PRI_GHO};
                        border-color: {C.PRI}; }}
                """)
                self._home_mute_btn.setToolTip("Microphone is active. Click to mute (F4).")

    def _send(self):
        txt = self._input.text().strip()
        if not txt: return
        self._input.clear()
        self._log.append_log(f"You: {txt}")
        if self.on_text_command:
            threading.Thread(target=self.on_text_command, args=(txt,), daemon=True).start()

    def _apply_state(self, state: str):
        self.hud.state    = state
        self.hud.speaking = (state == "SPEAKING")
        label = str(state or "READY").upper()
        if self._muted and label not in ("ERROR", "DISCONNECTED"):
            label = "MIC MUTED"
            color = C.MUTED_C
        else:
            color = C.ACC if label in ("THINKING", "PROCESSING", "CONNECTING") else (C.RED if label in ("ERROR", "DISCONNECTED") else C.PRI)
        if hasattr(self, "_system_state_lbl"):
            self._system_state_lbl.setText("// " + label)
            self._system_state_lbl.setStyleSheet(f"color: {color}; background: transparent;")

    def _apply_local_mode(self) -> None:
        """Mark cloud-only controls inactive when the local text backend is used."""
        self._sub_lbl.setText("LOCAL AI · SPOKEN REPLIES")
        for name in ("_mute_btn", "_wake_btn", "_wake_sleep_btn", "_ptt_btn"):
            button = getattr(self, name, None)
            if button is not None:
                button.setEnabled(False)
                button.setToolTip(
                    "Microphone input, wake word, and push-to-talk are not connected "
                    "in local mode yet. ORI will speak its text replies aloud."
                )

    def _check_config(self) -> bool:
        """Gemini key is required for the primary voice + desktop-action runtime."""
        try:
            d = _read_full_config()
            key = str(d.get("gemini_api_key") or "").strip()
            os_name = str(d.get("os_system") or "").strip()
            return len(key) >= 16 and bool(os_name) and bool(d.get("onboarding_completed", False))
        except Exception:
            return False

    def _show_setup(self):
        ov = SetupOverlay(self.centralWidget())
        cw = self.centralWidget()
        ow, oh = 560, 470
        ov.setGeometry(
            (cw.width()  - ow) // 2,
            (cw.height() - oh) // 2,
            ow, oh,
        )
        ov.done.connect(self._on_setup_done)
        ov.show()
        self._overlay = ov

    def _on_setup_done(self, key: str, os_name: str, profile: dict | None = None):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        # Merge instead of replacing the entire config so customization,
        # local-model settings and plugin preferences survive reconfiguration.
        data = _read_full_config()
        data["gemini_api_key"] = key.strip()
        data["os_system"] = os_name
        data["assistant_mode"] = "cloud"
        data["assistant_name"] = "ORI"
        data["gemini_key_verified"] = True
        if isinstance(profile, dict):
            for field in ("user_name", "preferred_language", "conversation_style",
                          "guest_mode", "onboarding_completed"):
                if field in profile:
                    data[field] = profile[field]
        API_FILE.write_text(json.dumps(data, indent=4, ensure_ascii=False), encoding="utf-8")
        self._ready = True
        QTimer.singleShot(1200, self._maybe_prompt_startup_location)
        if self._overlay:
            self._overlay.hide()
            self._overlay = None
        self._apply_state("LISTENING")
        self._assistant_name = "ORI"
        self._log.append_log(f"SYS: Initialised. OS={os_name.upper()}. ORI online.")


class _RootShim:
    def __init__(self, app: QApplication):
        self._app = app
    def mainloop(self):
        self._app.exec()
    def protocol(self, *_):
        pass


class JarvisUI:
    def __init__(self, size=None):
        self._app = QApplication.instance() or QApplication(sys.argv)
        self._app.setStyle("Fusion")
        self.on_state_change = None
        self._win = MainWindow()
        self._win._activity_publish = self.set_state
        self.root = _RootShim(self._app)
        self._win.show()

    @property
    def muted(self) -> bool:
        return self._win._muted

    @muted.setter
    def muted(self, v: bool):
        if v != self._win._muted:
            self._win._toggle_mute()

    def set_muted_from_remote(self, muted: bool | None = None) -> bool:
        """Expose remote microphone control through the public JarvisUI facade."""
        return self._win.set_muted_from_remote(muted)

    def set_access_indicator(self, name: str, active: bool) -> None:
        """Show/hide a live capability indicator without adding feature buttons."""
        self._win.set_access_indicator(name, active)

    @property
    def current_file(self) -> str | None:
        return self._win._drop_zone.current_file()

    @property
    def on_text_command(self):
        return self._win.on_text_command

    @on_text_command.setter
    def on_text_command(self, cb):
        self._win.on_text_command = cb

    @property
    def on_voice_interrupt_change(self):
        return getattr(self._win, "on_voice_interrupt_change", None)

    @on_voice_interrupt_change.setter
    def on_voice_interrupt_change(self, cb):
        self._win.on_voice_interrupt_change = cb

    @property
    def on_remote_clicked(self):
        return self._win.on_remote_clicked

    @on_remote_clicked.setter
    def on_remote_clicked(self, cb):
        self._win.on_remote_clicked = cb

    @property
    def on_interrupt(self):
        return self._win.on_interrupt

    @on_interrupt.setter
    def on_interrupt(self, cb):
        self._win.on_interrupt = cb

    @property
    def on_voice_change(self):
        return self._win.on_voice_change

    @on_voice_change.setter
    def on_voice_change(self, cb):
        self._win.on_voice_change = cb

    @property
    def on_audio_device_change(self):
        return self._win.on_audio_device_change

    @on_audio_device_change.setter
    def on_audio_device_change(self, cb):
        self._win.on_audio_device_change = cb

    @property
    def on_api_key_change(self):
        return self._win.on_api_key_change

    @on_api_key_change.setter
    def on_api_key_change(self, cb):
        self._win.on_api_key_change = cb

    def show_confirm(self, title: str, detail: str) -> None:
        """Thread-safe: raise the irreversible-action gate. Called from action
        handlers running in executor threads, so it goes through a signal."""
        self._win._confirm_sig.emit(str(title)[:120], str(detail)[:300])

    def hide_confirm(self) -> None:
        """Thread-safe: take the gate down."""
        self._win._confirm_hide_sig.emit()

    @property
    def get_plugins(self):
        return self._win.get_plugins

    @get_plugins.setter
    def get_plugins(self, cb):
        self._win.get_plugins = cb

    @property
    def get_plugin_settings(self):
        return self._win.get_plugin_settings

    @get_plugin_settings.setter
    def get_plugin_settings(self, cb):
        self._win.get_plugin_settings = cb

    @property
    def on_wake_toggle(self):
        return self._win.on_wake_toggle

    @on_wake_toggle.setter
    def on_wake_toggle(self, cb):
        self._win.on_wake_toggle = cb

    @property
    def on_wake_manual(self):
        return self._win.on_wake_manual

    @on_wake_manual.setter
    def on_wake_manual(self, cb):
        self._win.on_wake_manual = cb

    @property
    def wake_get_state(self):
        return self._win.wake_get_state

    @wake_get_state.setter
    def wake_get_state(self, cb):
        self._win.wake_get_state = cb

    def set_audio_level(self, level: float) -> None:
        """Thread-safe audio envelope update for the HUD."""
        try:
            self._win.hud.set_audio_level(level)
        except Exception:
            pass

    def set_audio_spectrum(self, bands, source: str = "input") -> None:
        """Forward actual FFT bands; the HUD handles only smoothing/painting."""
        try:
            self._win.hud.set_audio_spectrum(bands, source)
        except Exception:
            pass

    def glance(self, dx: float, dy: float, hold: float = 1.1) -> None:
        """Compatibility no-op; the waveform HUD has no character to move."""
        return

    @property
    def ptt_hold(self):
        return self._win.ptt_hold

    @ptt_hold.setter
    def ptt_hold(self, cb):
        self._win.ptt_hold = cb

    @property
    def on_push_to_talk(self):
        return self._win.on_push_to_talk

    @on_push_to_talk.setter
    def on_push_to_talk(self, cb):
        self._win.on_push_to_talk = cb

    def notify_phone_connected(self) -> None:
        self._win.notify_phone_connected()

    def update_remote_settings_status(self, url: str, running: bool = True, detail: str = "") -> None:
        """Thread-safe dashboard status update for the Qt window."""
        self._win.update_remote_settings_status(url, running, detail)

    def set_state(self, state: str):
        self._win._state_sig.emit(state)
        callback = getattr(self, "on_state_change", None)
        if callback is not None:
            try:
                callback(str(state))
            except Exception:
                pass

    def set_local_mode(self) -> None:
        """Thread-safe UI adjustment for local text mode."""
        self._win._local_mode_sig.emit()

    def write_log(self, text: str):
        self._win._log_sig.emit(text)

    def wait_for_api_key(self):
        while not self._win._ready:
            time.sleep(0.1)

    def show_content(self, title: str, text: str):
        """Thread-safe: display content in the panel below the HUD."""
        self._win._content_sig.emit(title[:48], text[:4000])

    def show_quiz(self, topic: str, questions, grade=None) -> None:
        """Thread-safe: put an interactive quiz on the board.

        `grade(question, given)` decides each answer — the plugin supplies it so
        the marking rules live with the questions rather than being duplicated
        here. Returning None from it means "ORI should judge this one", which
        is how open answers and near-miss gap-fills are handled.

        Returns immediately: the user answers at their own pace and the finished
        result is delivered back through on_text_command.
        """
        self._win._quiz_sig.emit(str(topic or ""), list(questions or []), grade)

    def hide_quiz(self) -> None:
        """Thread-safe: clear any quiz currently on the board."""
        self._win._quiz_hide_sig.emit()

    def show_review(self, title: str, summary: str, findings, unclear=None) -> None:
        """Thread-safe: lay a document review into the panel below the HUD.

        `findings` is a list of {heading, detail, severity, quote, suggestion};
        severity is one of 'serious' / 'caution' / 'note' and decides colour and
        order here, so the caller supplies no styling of its own.
        """
        self._win._review_sig.emit(str(title or ""), str(summary or ""),
                                   list(findings or []), list(unclear or []))

    def prompt_reconfig(self):
        """Thread-safe: show the API key setup overlay (e.g. after an auth error)."""
        self._win._ready = False
        self._win._reconfig_sig.emit()

    def show_camera_frame(self, img_bytes: bytes):
        """Thread-safe: show a webcam frame in the small overlay (screen captures)."""
        self._win._camera_sig.emit(img_bytes)

    def show_video(self, source: str, title: str = "", muted: bool = True,
                   audio_source: str = "") -> None:
        """Thread-safe: play a video in the central visualisation area.

        `source` is a local path or a direct media URL. `audio_source` is for
        the case where the sound arrives as its own stream — YouTube serves no
        combined format any more — and when it is given the two are played
        together and kept in step.

        Muted by default, and that is a decision rather than a default: a
        soundtrack talking over ORI is the one way this could make the
        assistant worse. The user turns sound on from the header button or by
        asking, and closes it the same two ways.
        """
        self._win._video_open_sig.emit(str(source or ""), str(title or ""),
                                       bool(muted), str(audio_source or ""))

    def stop_video(self) -> None:
        """Thread-safe: close the video and give the HUD back to the avatar."""
        self._win._video_close_sig.emit()

    def set_video_muted(self, muted: bool) -> None:
        """Thread-safe: silence or unsilence whatever is playing."""
        self._win._video_mute_sig.emit(bool(muted))

    def video_is_playing(self) -> bool:
        return bool(self._win.video_is_playing())

    def start_camera_stream(self) -> None:
        """Thread-safe: start live camera feed in the full HUD area."""
        self._win.start_camera_stream()

    def stop_camera_stream(self) -> None:
        """Thread-safe: stop the live camera feed."""
        self._win.stop_camera_stream()

    @property
    def assistant_name(self) -> str:
        return self._win._assistant_name

    def start_speaking(self):
        self.set_state("SPEAKING")

    def stop_speaking(self):
        if not self.muted:
            self.set_state("LISTENING")
