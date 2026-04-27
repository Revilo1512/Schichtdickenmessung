"""
Centralized colors, fonts and reusable stylesheet snippets.

All inline ``setStyleSheet`` calls in the UI go through these helpers so
that color and border decisions live in one place. Avoid hard-coding
hex literals anywhere else.
"""

from __future__ import annotations

from PyQt6.QtCore    import Qt, QPoint, QRect, QSize
from PyQt6.QtGui     import QFont
from PyQt6.QtWidgets import QLayout, QSizePolicy, QStyle


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


# ---------------------------------------------------------------------------
# FlowLayout — children wrap to the next row when the parent gets narrower.
# Used for filter bars so they remain usable at small window widths.
# ---------------------------------------------------------------------------

class FlowLayout(QLayout):
    """Re-implementation of Qt's classic FlowLayout example."""

    def __init__(self, parent=None, margin=0, h_spacing=8, v_spacing=8):
        super().__init__(parent)
        if parent is not None:
            self.setContentsMargins(margin, margin, margin, margin)
        self._h_space = h_spacing
        self._v_space = v_spacing
        self._items: list = []

    def __del__(self):
        item = self.takeAt(0)
        while item:
            item = self.takeAt(0)

    def addItem(self, item):
        self._items.append(item)

    def horizontalSpacing(self) -> int:
        if self._h_space >= 0:
            return self._h_space
        return self._smart_spacing(QStyle.PixelMetric.PM_LayoutHorizontalSpacing)

    def verticalSpacing(self) -> int:
        if self._v_space >= 0:
            return self._v_space
        return self._smart_spacing(QStyle.PixelMetric.PM_LayoutVerticalSpacing)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index: int):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self) -> QSize:
        return self.minimumSize()

    def minimumSize(self) -> QSize:
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(),
                      margins.top()  + margins.bottom())
        return size

    def _do_layout(self, rect: QRect, test_only: bool) -> int:
        margins = self.contentsMargins()
        effective = rect.adjusted(margins.left(), margins.top(),
                                  -margins.right(), -margins.bottom())
        x = effective.x()
        y = effective.y()
        line_height = 0

        for item in self._items:
            widget = item.widget()
            space_x = self.horizontalSpacing()
            space_y = self.verticalSpacing()
            if widget is not None:
                style = widget.style()
                if self._h_space < 0:
                    space_x = style.layoutSpacing(
                        QSizePolicy.ControlType.PushButton,
                        QSizePolicy.ControlType.PushButton,
                        Qt.Orientation.Horizontal,
                    )
                if self._v_space < 0:
                    space_y = style.layoutSpacing(
                        QSizePolicy.ControlType.PushButton,
                        QSizePolicy.ControlType.PushButton,
                        Qt.Orientation.Vertical,
                    )

            next_x = x + item.sizeHint().width() + space_x
            if next_x - space_x > effective.right() and line_height > 0:
                x = effective.x()
                y = y + line_height + space_y
                next_x = x + item.sizeHint().width() + space_x
                line_height = 0

            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))

            x = next_x
            line_height = max(line_height, item.sizeHint().height())

        return y + line_height - rect.y() + margins.bottom()

    def _smart_spacing(self, pm: QStyle.PixelMetric) -> int:
        parent = self.parent()
        if parent is None:
            return -1
        if parent.isWidgetType():
            return parent.style().pixelMetric(pm, None, parent)
        return parent.spacing()