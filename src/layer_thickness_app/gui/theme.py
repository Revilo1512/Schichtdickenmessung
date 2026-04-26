"""
Centralized colors, fonts and reusable stylesheet snippets.

All inline ``setStyleSheet`` calls in the UI go through these helpers so
that color and border decisions live in one place. Avoid hard-coding
hex literals anywhere else.
"""

from __future__ import annotations

from PyQt6.QtGui import QFont


# ---------------------------------------------------------------------------
# Semantic colors
# ---------------------------------------------------------------------------

COLOR_SUCCESS = "#00b050"
COLOR_WARN    = "#e0a500"
COLOR_ERROR   = "#e04141"
COLOR_ACCENT  = "#0078d4"
COLOR_MUTED   = "gray"
COLOR_LIVE    = "#5a9bd4"

# Faint border used for "card" frames — semi-transparent so it works in
# both light and dark themes without re-loading.
BORDER_FAINT = "rgba(128, 128, 128, 0.25)"

# Image preview placeholder background. Kept dark in both themes because
# it represents an empty camera frame and reads as a viewport.
PREVIEW_BG     = "#2E2E2E"
PREVIEW_FG     = "white"
PREVIEW_BORDER = "#555"


# ---------------------------------------------------------------------------
# Fonts
# ---------------------------------------------------------------------------

def header_font(point_size: int = 10, bold: bool = True) -> QFont:
    f = QFont()
    f.setBold(bold)
    f.setPointSize(point_size)
    return f


def hint_font(point_size: int = 8) -> QFont:
    f = QFont()
    f.setPointSize(point_size)
    return f


def title_font(point_size: int = 18, bold: bool = True) -> QFont:
    f = QFont()
    f.setBold(bold)
    f.setPointSize(point_size)
    return f


# ---------------------------------------------------------------------------
# Stylesheet snippets — applied via ``QFrame.setStyleSheet`` etc.
# ---------------------------------------------------------------------------

def card_style(object_name: str | None = None) -> str:
    """
    Card-style border + radius for QFrame. Pass ``object_name`` to scope
    the rule so labels inside the frame don't inherit the border.
    """
    selector = f"QFrame#{object_name}" if object_name else "QFrame"
    return (
        f"{selector} {{"
        f"  background-color: transparent;"
        f"  border: 1px solid {BORDER_FAINT};"
        f"  border-radius: 8px;"
        f"}}"
    )


def image_preview_style() -> str:
    return (
        f"background-color: {PREVIEW_BG};"
        f" color: {PREVIEW_FG};"
        f" border: 1px solid {PREVIEW_BORDER};"
        f" border-radius: 4px;"
    )


def muted_label_style() -> str:
    return f"color: {COLOR_MUTED};"


def live_label_style() -> str:
    return f"color: {COLOR_LIVE};"


def status_label_style(state: str) -> str:
    """
    Returns a stylesheet for a status label.
    ``state`` is one of: ``ok``, ``warn``, ``error``, ``muted``.
    """
    color = {
        "ok":     COLOR_SUCCESS,
        "warn":   COLOR_WARN,
        "error":  COLOR_ERROR,
        "muted":  COLOR_MUTED,
    }.get(state, COLOR_MUTED)
    return f"font-weight: bold; color: {color};"


def borderless_style() -> str:
    """For labels nested inside cards so they don't inherit the border."""
    return "border: none;"


def quality_color(r_squared: float) -> str:
    """Color a numeric quality indicator (R², capability index, ...)."""
    if r_squared >= 0.95:
        return COLOR_SUCCESS
    if r_squared >= 0.80:
        return COLOR_WARN
    return COLOR_ERROR