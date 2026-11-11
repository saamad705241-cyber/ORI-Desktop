"""
Glass-style building blocks for the HUD, all painted with QPainter.

Nothing here needs OpenGL or an extra package. Every widget reads the live
palette (ui_theme.C) when it paints, so the hue wheel in CUSTOMISE re-tints
them instantly with no stylesheet rewriting.

    Backdrop     – the window background (procedural, or assets/ui_background.*)
    GlassPanel   – translucent rounded panel with a glowing edge
    NavButton    – round-icon navigation entry
    RingGauge    – circular meter (same set_value(pct, text) API as MetricBar)
    HomeCard     – greeting + clock + system status (real readings only)
    paint_holo_orb – the animated centrepiece used by the HUD canvas

Glass note: Qt cannot blur what is *behind* a window, so the "frosted" look is
produced by painting translucent gradients over an already soft backdrop. It is
an honest approximation, not a live desktop blur.
"""
from __future__ import annotations

import math
import random
import time
from collections import deque
from pathlib import Path

import numpy as np
from PyQt6.QtCore import QLineF, QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QBrush, QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen,
    QPixmap, QPolygonF, QRadialGradient,
)
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from ui_theme import C, UI_FONT, qcol


def _mix(a: str, b: str, k: float) -> QColor:
    """Linear mix of two #rrggbb colours (k=0 → a, k=1 → b)."""
    ca, cb = QColor(a), QColor(b)
    k = max(0.0, min(1.0, k))
    return QColor(int(ca.red() + (cb.red() - ca.red()) * k),
                  int(ca.green() + (cb.green() - ca.green()) * k),
                  int(ca.blue() + (cb.blue() - ca.blue()) * k))


# ══════════════════════════════════════════════════════════════════════════════
#  Backdrop
# ══════════════════════════════════════════════════════════════════════════════

class Backdrop(QWidget):
    """Subtle terminal grid with scanlines. No stars, planets, or fake blur."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cache: QPixmap | None = None
        self._key = None

    def _make(self, W: int, H: int) -> QPixmap:
        pm = QPixmap(max(1, W), max(1, H))
        pm.fill(QColor(C.BG))
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        p.fillRect(0, 0, W, H, QColor(C.BG))

        # Faint machine-grid, kept deliberately subtle behind the waveform.
        grid = QColor(C.PRI)
        grid.setAlpha(17)
        p.setPen(QPen(grid, 1))
        for x in range(0, W, 36):
            p.drawLine(x, 0, x, H)
        for y in range(0, H, 36):
            p.drawLine(0, y, W, y)

        # Horizontal CRT scanlines; no noisy animation or bright gradients.
        scan = QColor(C.PRI)
        scan.setAlpha(9)
        p.setPen(QPen(scan, 1))
        for y in range(2, H, 4):
            p.drawLine(0, y, W, y)

        # Fine corner registration marks like a diagnostic interface.
        p.setPen(QPen(qcol(C.PRI, 90), 1))
        pad, mark = 18, 18
        for x, sx in ((pad, 1), (W-pad, -1)):
            for y, sy in ((pad, 1), (H-pad, -1)):
                p.drawLine(x, y, x + sx*mark, y)
                p.drawLine(x, y, x, y + sy*mark)

        # Tiny amber register marks add contrast without turning the app orange.
        p.setPen(QPen(qcol(C.ACC, 80), 1))
        p.drawLine(W - 68, 18, W - 42, 18)
        p.drawLine(18, H - 19, 42, H - 19)
        p.end()
        return pm

    def paintEvent(self, _):
        W, H = self.width(), self.height()
        if W < 2 or H < 2:
            return
        key = (W, H, C.PRI, C.ACC, C.BG)
        if self._cache is None or self._key != key:
            self._cache = self._make(W, H)
            self._key = key
        p = QPainter(self)
        p.drawPixmap(0, 0, self._cache)
        p.end()


# ══════════════════════════════════════════════════════════════════════════════
#  GlassPanel
# ══════════════════════════════════════════════════════════════════════════════

class GlassPanel(QWidget):
    def __init__(self, parent=None, radius: float = 18.0,
                 brackets: bool = False, opacity: float = 1.0):
        super().__init__(parent)
        self._radius = radius
        self._brackets = brackets
        self._opacity = opacity
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)

    def paintEvent(self, _):
        p = QPainter(self)
        if not p.isActive():
            return
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5)
        path = QPainterPath()
        path.addRoundedRect(r, self._radius, self._radius)
        k = self._opacity

        body = QLinearGradient(r.topLeft(), r.bottomLeft())
        body.setColorAt(0.0, qcol(C.PANEL2, int(170 * k)))
        body.setColorAt(1.0, qcol(C.PANEL, int(135 * k)))
        p.fillPath(path, body)

        sheen = QLinearGradient(r.topLeft(), QPointF(r.left(), r.top() + r.height() * 0.40))
        sheen.setColorAt(0.0, QColor(255, 255, 255, int(24 * k)))
        sheen.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.fillPath(path, sheen)

        p.setPen(QPen(qcol(C.PRI, 26), 5))
        p.drawPath(path)
        edge = QLinearGradient(r.topLeft(), r.bottomRight())
        edge.setColorAt(0.0, qcol(C.BORDER_B, 215))
        edge.setColorAt(0.5, qcol(C.BORDER_A, 120))
        edge.setColorAt(1.0, qcol(C.BORDER_B, 170))
        p.setPen(QPen(QBrush(edge), 1.3))
        p.drawPath(path)

        if self._brackets:
            L, o = 24.0, 1.5
            p.setPen(QPen(qcol(C.PRI, 235), 2.2, Qt.PenStyle.SolidLine,
                          Qt.PenCapStyle.RoundCap))
            x0, y0, x1, y1 = r.left() + o, r.top() + o, r.right() - o, r.bottom() - o
            p.drawLine(QLineF(x0, y0 + L, x0, y0 + self._radius * 0.5))
            p.drawLine(QLineF(x0 + self._radius * 0.5, y0, x0 + L, y0))
            p.drawLine(QLineF(x1, y1 - L, x1, y1 - self._radius * 0.5))
            p.drawLine(QLineF(x1 - self._radius * 0.5, y1, x1 - L, y1))
        p.end()


# ══════════════════════════════════════════════════════════════════════════════
#  Navigation button
# ══════════════════════════════════════════════════════════════════════════════

def _draw_icon(p: QPainter, kind: str, x: float, y: float, s: float, col: QColor):
    """Simple line icons on an s×s square at (x, y)."""
    def pt(a, b):
        return QPointF(x + a * s, y + b * s)

    pen = QPen(col, max(1.6, s * 0.075), Qt.PenStyle.SolidLine,
               Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)

    if kind == "home":
        p.drawPolyline(QPolygonF([pt(.18, .50), pt(.50, .22), pt(.82, .50)]))
        p.drawPolyline(QPolygonF([pt(.27, .45), pt(.27, .80), pt(.73, .80), pt(.73, .45)]))
        p.drawPolyline(QPolygonF([pt(.44, .80), pt(.44, .60), pt(.56, .60), pt(.56, .80)]))
    elif kind == "chat":
        p.drawRoundedRect(QRectF(x + .18 * s, y + .24 * s, .64 * s, .44 * s), s * .10, s * .10)
        p.drawPolyline(QPolygonF([pt(.36, .68), pt(.32, .82), pt(.50, .68)]))
    elif kind == "voice":
        p.drawRoundedRect(QRectF(x + .41 * s, y + .18 * s, .18 * s, .36 * s), s * .09, s * .09)
        p.drawArc(QRectF(x + .29 * s, y + .30 * s, .42 * s, .34 * s), 180 * 16, 180 * 16)
        p.drawLine(QLineF(pt(.50, .64), pt(.50, .80)))
        p.drawLine(QLineF(pt(.40, .80), pt(.60, .80)))
    elif kind == "memory":
        p.drawRoundedRect(QRectF(x + .30 * s, y + .30 * s, .40 * s, .40 * s), s * .06, s * .06)
        for f in (.40, .50, .60):
            p.drawLine(QLineF(pt(f, .30), pt(f, .20)))
            p.drawLine(QLineF(pt(f, .70), pt(f, .80)))
            p.drawLine(QLineF(pt(.30, f), pt(.20, f)))
            p.drawLine(QLineF(pt(.70, f), pt(.80, f)))
    elif kind == "tools":
        for a, b in ((.22, .22), (.54, .22), (.22, .54), (.54, .54)):
            p.drawRoundedRect(QRectF(x + a * s, y + b * s, .24 * s, .24 * s), s * .05, s * .05)
    elif kind == "controls":
        for yy, kx in ((.28, .36), (.50, .64), (.72, .44)):
            p.drawLine(QLineF(pt(.20, yy), pt(.80, yy)))
            p.setBrush(QBrush(col))
            p.drawEllipse(pt(kx, yy), s * .07, s * .07)
            p.setBrush(Qt.BrushStyle.NoBrush)
    elif kind == "settings":
        c = pt(.5, .5)
        p.drawEllipse(c, s * .11, s * .11)
        p.drawEllipse(c, s * .23, s * .23)
        for i in range(8):
            a = math.radians(i * 45)
            p.drawLine(QLineF(c.x() + math.cos(a) * s * .23, c.y() + math.sin(a) * s * .23,
                              c.x() + math.cos(a) * s * .32, c.y() + math.sin(a) * s * .32))


class NavButton(QWidget):
    clicked = pyqtSignal()

    def __init__(self, label: str, icon: str, parent=None):
        super().__init__(parent)
        self._label, self._icon = label, icon
        self._active = False
        self._hover = False
        self.setFixedHeight(54)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)
        self.setToolTip(label)

    def setActive(self, on: bool):
        if on != self._active:
            self._active = on
            self.update()

    def enterEvent(self, e):
        self._hover = True
        self.update()

    def leaveEvent(self, e):
        self._hover = False
        self.update()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self.rect().contains(e.position().toPoint()):
            self.clicked.emit()

    def paintEvent(self, _):
        p = QPainter(self)
        if not p.isActive():
            return
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()
        d = 40.0
        cx, cy = 8 + d / 2, H / 2

        if self._active:
            pill = QRectF(2, 3, W - 4, H - 6)
            g = QLinearGradient(pill.left(), 0, pill.right(), 0)
            g.setColorAt(0.0, qcol(C.PRI, 95))
            g.setColorAt(0.65, qcol(C.PRI, 28))
            g.setColorAt(1.0, qcol(C.PRI, 0))
            path = QPainterPath()
            path.addRoundedRect(pill, pill.height() / 2, pill.height() / 2)
            p.fillPath(path, g)
            p.setPen(QPen(qcol(C.PRI, 150), 1.2))
            p.drawPath(path)

        # round glass disc
        disc = QRectF(cx - d / 2, cy - d / 2, d, d)
        rg = QRadialGradient(cx - d * .15, cy - d * .2, d * .8)
        rg.setColorAt(0.0, qcol(C.PRI, 85 if (self._active or self._hover) else 45))
        rg.setColorAt(1.0, qcol(C.PANEL, 190))
        p.setBrush(QBrush(rg))
        ring = qcol(C.PRI, 255 if self._active else (200 if self._hover else 135))
        p.setPen(QPen(qcol(C.PRI, 40), 5))
        p.drawEllipse(disc)
        p.setPen(QPen(ring, 1.4))
        p.drawEllipse(disc)

        ic = qcol(C.WHITE if (self._active or self._hover) else C.TEXT_MED)
        _draw_icon(p, self._icon, cx - d * .30, cy - d * .30, d * .60, ic)

        f = QFont(UI_FONT, 11)
        f.setWeight(QFont.Weight.DemiBold if self._active else QFont.Weight.Normal)
        p.setFont(f)
        p.setPen(qcol(C.WHITE if self._active else C.TEXT_MED))
        p.drawText(QRectF(cx + d / 2 + 14, 0, W - d - 36, H),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self._label)
        p.end()


# ══════════════════════════════════════════════════════════════════════════════
#  RingGauge / small readouts
# ══════════════════════════════════════════════════════════════════════════════

class RingGauge(QWidget):
    """Circular meter. Same set_value(pct, text) contract as MetricBar."""

    def __init__(self, label: str, color: str = "PRI", parent=None):
        super().__init__(parent)
        self._label, self._color = label, color
        self._value, self._text = 0.0, "--"
        self.setMinimumSize(54, 54)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(58)

    def set_value(self, pct: float, text: str):
        v = max(0.0, min(100.0, pct))
        if v == self._value and text == self._text:
            return
        self._value, self._text = v, text
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        if not p.isActive():
            return
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()
        d = min(W, H) - 6
        box = QRectF((W - d) / 2, (H - d) / 2, d, d)

        na = self._text in ("N/A", "--")
        # a palette name ("PRI", "ACC"...) is resolved live so the hue wheel re-tints it
        col = qcol(getattr(C, self._color, self._color))
        if not na:
            if self._value > 85:
                col = qcol(C.RED)
            elif self._value > 65:
                col = qcol(C.ACC2)

        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(qcol(C.BORDER, 200), 3.2))
        p.drawEllipse(box)
        if not na and self._value > 0:
            glow = QColor(col)
            glow.setAlpha(55)
            p.setPen(QPen(glow, 7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawArc(box, 90 * 16, int(-self._value * 3.6 * 16))
            p.setPen(QPen(col, 3.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawArc(box, 90 * 16, int(-self._value * 3.6 * 16))

        p.setPen(qcol(C.TEXT_MED))
        p.setFont(QFont(UI_FONT, 7))
        p.drawText(QRectF(box.left(), box.top() + d * .16, d, d * .30),
                   Qt.AlignmentFlag.AlignCenter, self._label)
        p.setPen(qcol(C.WHITE if not na else C.TEXT_DIM))
        f = QFont(UI_FONT, 9)
        f.setWeight(QFont.Weight.DemiBold)
        p.setFont(f)
        p.drawText(QRectF(box.left(), box.top() + d * .44, d, d * .34),
                   Qt.AlignmentFlag.AlignCenter, self._text)
        p.end()


class TextStat:
    """Stand-in with the MetricBar API that simply sets a label's text."""

    def __init__(self, label: QLabel, prefix: str = ""):
        self._label, self._prefix = label, prefix

    def set_value(self, pct: float, text: str):
        self._label.setText(f"{self._prefix}{text}")


class _Wave(QWidget):
    """Thin live strip fed by a real 0–1 level (the same one that drives the
    orb). Flat when nothing is being said or heard."""

    def __init__(self, source, parent=None):
        super().__init__(parent)
        self._source = source
        self._hist: deque[float] = deque([0.0] * 72, maxlen=72)
        self.setFixedHeight(28)
        self._t = QTimer(self)
        self._t.timeout.connect(self._tick)
        self._t.start(70)

    def _tick(self):
        if not self.isVisible():
            return
        try:
            self._hist.append(float(self._source()))
        except Exception:
            self._hist.append(0.0)
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        if not p.isActive():
            return
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()
        mid = H / 2
        n = len(self._hist)
        step = W / n
        p.setPen(QPen(qcol(C.PRI, 70), 1))
        p.drawLine(QLineF(0, mid, W, mid))
        p.setPen(QPen(qcol(C.PRI, 235), 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        for i, v in enumerate(self._hist):
            h = (0.04 + min(1.0, v) * 0.96) * (H / 2 - 1)
            x = i * step + step / 2
            p.drawLine(QLineF(x, mid - h, x, mid + h))
        p.end()


# ══════════════════════════════════════════════════════════════════════════════
#  HomeCard
# ══════════════════════════════════════════════════════════════════════════════

def greeting_for_hour(h: int) -> str:
    if 5 <= h < 12:
        return "Good Morning,"
    if 12 <= h < 17:
        return "Good Afternoon,"
    if 17 <= h < 21:
        return "Good Evening,"
    return "Good Night,"


class HomeCard(GlassPanel):
    """Greeting, clock and live system status. Every number on it is a real
    reading from the monitor; an unavailable sensor shows N/A."""

    CARD_W = 306

    def __init__(self, user_name: str, level_source, parent=None):
        super().__init__(parent, radius=18, brackets=True)
        self.setFixedWidth(self.CARD_W)
        self._user = (user_name or "").strip()

        v = QVBoxLayout(self)
        v.setContentsMargins(22, 18, 22, 16)
        v.setSpacing(3)

        self._greet = QLabel("")
        self._greet.setFont(QFont(UI_FONT, 15))
        self._greet.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        v.addWidget(self._greet)

        self._name = QLabel(self._user)
        f = QFont(UI_FONT, 25)
        f.setWeight(QFont.Weight.Bold)
        self._name.setFont(f)
        self._name.setStyleSheet(f"color: {C.WHITE}; background: transparent;")
        self._name.setWordWrap(True)
        self._name.setVisible(bool(self._user))
        v.addWidget(self._name)

        quote = QLabel("“Let’s make something amazing today”")
        quote.setFont(QFont(UI_FONT, 10))
        quote.setWordWrap(True)
        quote.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
        v.addSpacing(4)
        v.addWidget(quote)

        v.addSpacing(6)
        v.addWidget(_Wave(level_source))

        self._clock = QLabel("")
        self._clock.setFont(QFont(UI_FONT, 9))
        self._clock.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        v.addSpacing(2)
        v.addWidget(self._clock)

        v.addSpacing(8)
        sep = QWidget()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {C.BORDER};")
        v.addWidget(sep)
        v.addSpacing(6)

        cap = QLabel("System Status")
        cap.setFont(QFont(UI_FONT, 9))
        cap.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
        v.addWidget(cap)

        row = QHBoxLayout()
        row.setSpacing(6)
        self.g_cpu = RingGauge("CPU", "PRI")
        self.g_ram = RingGauge("RAM", "ACC2")
        self.g_gpu = RingGauge("GPU", "ACC")
        self.g_tmp = RingGauge("TEMP", "#ff7a9a")
        for g in (self.g_cpu, self.g_ram, self.g_gpu, self.g_tmp):
            row.addWidget(g)
        v.addLayout(row)

        self.net_lbl = QLabel("NET  --")
        self.net_lbl.setFont(QFont(UI_FONT, 8))
        self.net_lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        self.up_lbl = QLabel("UP  --:--")
        self.up_lbl.setFont(QFont(UI_FONT, 8))
        self.up_lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        self.proc_lbl = QLabel("PROC  --")
        self.proc_lbl.setFont(QFont(UI_FONT, 8))
        self.proc_lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        foot = QHBoxLayout()
        foot.addWidget(self.net_lbl)
        foot.addStretch()
        foot.addWidget(self.up_lbl)
        foot.addSpacing(10)
        foot.addWidget(self.proc_lbl)
        v.addSpacing(2)
        v.addLayout(foot)

        self.refresh_greeting()

    def refresh_greeting(self):
        self._greet.setText(greeting_for_hour(time.localtime().tm_hour))

    def set_clock(self, date_txt: str, time_txt: str):
        self._clock.setText(f"{date_txt}   |   {time_txt}")
        self.refresh_greeting()


# ══════════════════════════════════════════════════════════════════════════════
#  Holographic orb (HUD centrepiece)
# ══════════════════════════════════════════════════════════════════════════════

_GLOBE = None


def _globe_points():
    """Fibonacci sphere with a procedural land mask. Built once."""
    global _GLOBE
    if _GLOBE is not None:
        return _GLOBE
    n = 900
    i = np.arange(n) + 0.5
    y = 1 - 2 * i / n
    rxy = np.sqrt(1 - y * y)
    th = math.pi * (3 - math.sqrt(5)) * i
    x, z = np.cos(th) * rxy, np.sin(th) * rxy
    lat, lon = np.arcsin(y), np.arctan2(z, x)
    v = (np.sin(lon * 2 + 1.3) * np.cos(lat * 3)
         + 0.6 * np.sin(lon * 5 - lat * 2) + 0.5 * np.cos(lon * 3 + lat * 4))
    land = v > 0.30
    _GLOBE = (x, y, z, land)
    return _GLOBE


def paint_holo_orb(p: QPainter, cx: float, cy: float, r: float, *,
                   amp: float, t: float, live: bool, main: QColor, acc: QColor):
    """Draw the orb centred on (cx, cy). `r` is the radius of the whole
    composition (sphere + orbit rings + platform). Motion is driven by `t`
    (time) and `amp` (the real, smoothed audio level)."""
    rs = r * 0.50 * (1.0 + 0.018 * math.sin(t * 1.4) + 0.05 * amp)
    py = cy + rs * 1.62                       # platform centre

    def col(c: QColor, a: float) -> QColor:
        q = QColor(c)
        q.setAlpha(max(0, min(255, int(a))))
        return q

    p.setBrush(Qt.BrushStyle.NoBrush)

    # atmosphere behind everything
    glow = QRadialGradient(cx, cy, rs * 2.6)
    glow.setColorAt(0.0, col(main, 80 + 90 * amp))
    glow.setColorAt(0.5, col(main, 22 + 30 * amp))
    glow.setColorAt(1.0, col(main, 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(glow))
    p.drawEllipse(QRectF(cx - rs * 2.6, cy - rs * 2.6, rs * 5.2, rs * 5.2))

    # light on the platform
    p.save()
    p.translate(cx, py)
    p.scale(1.0, 0.20)
    pg = QRadialGradient(0, 0, rs * 1.9)
    pg.setColorAt(0.0, col(main, 150 + 80 * amp))
    pg.setColorAt(1.0, col(main, 0))
    p.setBrush(QBrush(pg))
    p.drawEllipse(QRectF(-rs * 1.9, -rs * 1.9, rs * 3.8, rs * 3.8))
    p.restore()

    # platform rings (perspective ellipses)
    p.setBrush(Qt.BrushStyle.NoBrush)
    for k, (f, a, w) in enumerate(((1.15, 255, 2.4), (1.55, 120, 1.3),
                                   (1.95, 70, 1.1), (2.3, 36, 1.0))):
        rx = rs * f
        ry = rx * 0.20
        if k == 0:
            p.setPen(QPen(col(main, 55 + 60 * amp), 8))
            p.drawEllipse(QRectF(cx - rx, py - ry, rx * 2, ry * 2))
        p.setPen(QPen(col(main, a), w))
        p.drawEllipse(QRectF(cx - rx, py - ry, rx * 2, ry * 2))
    # a bright arc travelling around the inner ring
    rx = rs * 1.15
    p.setPen(QPen(col(acc, 235), 2.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    p.drawArc(QRectF(cx - rx, py - rx * .2, rx * 2, rx * .4),
              int(((t * 70) % 360) * 16), 70 * 16)

    # beam from platform up to the sphere
    beam = QLinearGradient(0, py, 0, cy + rs)
    beam.setColorAt(0.0, col(main, 70 + 40 * amp))
    beam.setColorAt(1.0, col(main, 0))
    poly = QPolygonF([QPointF(cx - rs * .55, py), QPointF(cx + rs * .55, py),
                      QPointF(cx + rs * .30, cy + rs * .85), QPointF(cx - rs * .30, cy + rs * .85)])
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(beam))
    p.drawPolygon(poly)

    # sphere body
    body = QRadialGradient(cx - rs * .32, cy - rs * .38, rs * 1.5)
    body.setColorAt(0.0, col(main.lighter(165), 235))
    body.setColorAt(0.45, col(main, 150))
    body.setColorAt(1.0, QColor(10, 24, 80, 235))
    p.setBrush(QBrush(body))
    p.drawEllipse(QRectF(cx - rs, cy - rs, rs * 2, rs * 2))

    # clip drawing to the sphere for the globe detail
    clip = QPainterPath()
    clip.addEllipse(QRectF(cx - rs, cy - rs, rs * 2, rs * 2))
    p.save()
    p.setClipPath(clip)

    # faint meridians / parallels
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(QColor(255, 255, 255, 30), 1))
    for k in range(6):
        ang = t * 0.35 + k * math.pi / 6
        w = abs(math.cos(ang)) * rs
        p.drawEllipse(QRectF(cx - w, cy - rs, w * 2, rs * 2))
    for lat in (-0.62, -0.31, 0.0, 0.31, 0.62):
        yy = math.sin(lat) * rs
        half = math.cos(lat) * rs
        p.drawEllipse(QRectF(cx - half, cy - yy - half * .13, half * 2, half * .26))

    # dotted continents, rotated in 3D
    X, Y, Z, land = _globe_points()
    a = t * 0.35
    ca, sa = math.cos(a), math.sin(a)
    xr = X * ca + Z * sa
    zr = -X * sa + Z * ca
    tilt = 0.32
    yr = Y * math.cos(tilt) - zr * math.sin(tilt)
    zz = Y * math.sin(tilt) + zr * math.cos(tilt)
    front = zz > 0.02
    sx = cx + xr * rs * 0.985
    sy = cy - yr * rs * 0.985
    for mask, alpha, wid in ((front & land & (zz > .55), 245, 3.0),
                             (front & land & (zz <= .55), 160, 2.3),
                             (front & ~land & (zz > .3), 70, 1.5)):
        if not mask.any():
            continue
        pts = QPolygonF([QPointF(float(a_), float(b_)) for a_, b_ in zip(sx[mask], sy[mask])])
        p.setPen(QPen(QColor(210, 240, 255, alpha), wid, Qt.PenStyle.SolidLine,
                      Qt.PenCapStyle.RoundCap))
        p.drawPoints(pts)
    p.restore()

    # rim light
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(col(main.lighter(150), 55 + 50 * amp), 9))
    p.drawEllipse(QRectF(cx - rs, cy - rs, rs * 2, rs * 2))
    p.setPen(QPen(col(main.lighter(165), 235), 1.8))
    p.drawEllipse(QRectF(cx - rs, cy - rs, rs * 2, rs * 2))
    p.setPen(QPen(QColor(255, 255, 255, 120), 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    p.drawArc(QRectF(cx - rs * .9, cy - rs * .9, rs * 1.8, rs * 1.8), 105 * 16, 50 * 16)

    # tilted orbit rings with a satellite
    for tilt_deg, kx, ky, a_main, spd in ((-20, 1.50, .34, 210, 1.0), (16, 1.95, .50, 90, -0.55)):
        p.save()
        p.translate(cx, cy)
        p.rotate(tilt_deg)
        er = QRectF(-rs * kx, -rs * ky, rs * kx * 2, rs * ky * 2)
        p.setPen(QPen(col(acc, 34), 1))
        p.drawEllipse(er)
        p.setPen(QPen(col(acc, a_main), 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawArc(er, int(((t * 40 * spd) % 360) * 16), 150 * 16)
        if spd > 0:
            phi = t * 1.1
            sxp, syp = math.cos(phi) * rs * kx, math.sin(phi) * rs * ky
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(col(acc, 70))
            p.drawEllipse(QPointF(sxp, syp), 7, 7)
            p.setBrush(QColor(255, 255, 255, 240))
            p.drawEllipse(QPointF(sxp, syp), 3, 3)
        p.restore()

    # the voice, as spikes around the sphere — real audio level only
    n, ring = 72, rs * 1.12
    spikes = []
    for i in range(n):
        ang = math.radians(i * (360.0 / n))
        c_, s_ = math.cos(ang), math.sin(ang)
        wob = 0.5 + 0.5 * math.sin(t * 2.3 + i * 0.42)
        idle = 0.012 + 0.008 * math.sin(t * 1.2 + i * 0.7)
        h = rs * (idle + (amp * 0.34 * wob if live else 0.0))
        spikes.append(QLineF(cx + c_ * ring, cy + s_ * ring,
                             cx + c_ * (ring + h), cy + s_ * (ring + h)))
    p.setPen(QPen(col(acc if live else main, 90 + 150 * amp), 1.6))
    p.drawLines(spikes)
