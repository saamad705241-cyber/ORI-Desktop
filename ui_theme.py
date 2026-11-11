"""ORI terminal-HUD palette: deep black, phosphor green, and restrained amber."""
from __future__ import annotations
import platform
from PyQt6.QtGui import QColor

_OS = platform.system()
UI_FONT = {"Windows": "Cascadia Mono", "Darwin": "Menlo"}.get(_OS, "DejaVu Sans Mono")

class C:
    BG        = "#020604"
    PANEL     = "#06120b"
    PANEL2    = "#081a10"
    BORDER    = "#123b25"
    BORDER_B  = "#238451"
    BORDER_A  = "#195d37"
    PRI       = "#43ff91"       # phosphor green
    PRI_DIM   = "#23985a"
    PRI_GHO   = "#092315"
    ACC       = "#ffc35a"       # restrained amber accent
    ACC2      = "#d0ff78"
    GREEN     = "#6dffab"
    GREEN_D   = "#25995e"
    RED       = "#ff5964"
    MUTED_C   = "#ff5964"
    TEXT      = "#c8f4d6"
    TEXT_DIM  = "#528567"
    TEXT_MED  = "#8fcba4"
    WHITE     = "#e8fff0"
    DARK      = "#010402"
    BAR_BG    = "#07130b"


def qcol(h: str, a: int = 255) -> QColor:
    c = QColor(h)
    c.setAlpha(a)
    return c
