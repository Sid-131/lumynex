"""
Shared UI widgets and helpers for all Lumynex screens.
Extracted from preview.py so every screen module can import them.
"""
from __future__ import annotations

import math
import os

from utils.paths import bundle_dir
from PyQt5.QtCore import Qt, QRectF, QPointF, QPoint, QTimer
from PyQt5.QtGui import (
    QColor, QPainter, QPen, QConicalGradient,
    QLinearGradient, QBrush, QPainterPath, QTransform, QFont,
)
from PyQt5.QtWidgets import (
    QWidget, QFrame, QLabel, QPushButton,
    QHBoxLayout, QVBoxLayout, QGraphicsDropShadowEffect,
)


# ── Stylesheet loader ──────────────────────────────────────────────────────

def load_stylesheet() -> str:
    path = bundle_dir() / "assets" / "styles.qss"
    with open(path, encoding="utf-8") as f:
        return f.read()


# ── Drop shadow factory ────────────────────────────────────────────────────

def shadow(blur: int = 20, dy: int = 3, alpha: int = 90, purple: bool = False) -> QGraphicsDropShadowEffect:
    fx = QGraphicsDropShadowEffect()
    fx.setBlurRadius(blur)
    fx.setOffset(0, dy)
    fx.setColor(QColor(91, 63, 191, 28) if purple else QColor(15, 13, 26, alpha))
    return fx


# ── Layout helpers ─────────────────────────────────────────────────────────

def hline() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.HLine)
    return f


def section_header(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("SectionHeader")
    return lbl


def kv(key: str, value: str, style: str = "DataValue") -> QWidget:
    w = QWidget()
    w.setStyleSheet("background:transparent;")
    row = QHBoxLayout(w)
    row.setContentsMargins(0, 3, 0, 3)
    row.setSpacing(0)
    k = QLabel(key)
    k.setObjectName("DataKey")
    k.setFixedWidth(120)
    v = QLabel(value)
    v.setObjectName(style)
    row.addWidget(k)
    row.addWidget(v)
    row.addStretch()
    return w


def card(children: list, state: str = "", min_w: int = 0) -> QFrame:
    f = QFrame()
    f.setObjectName("Card")
    if state:
        f.setProperty("state", state)
        f.style().unpolish(f)
        f.style().polish(f)
    if min_w:
        f.setMinimumWidth(min_w)
    f.setGraphicsEffect(shadow())
    lay = QVBoxLayout(f)
    lay.setContentsMargins(20, 18, 20, 20)
    lay.setSpacing(6)
    for w in children:
        if isinstance(w, QWidget):
            lay.addWidget(w)
        else:
            lay.addLayout(w)
    return f


def status_badge(text: str, state: str) -> QLabel:
    b = QLabel(text)
    b.setObjectName("StatusBadge")
    b.setProperty("state", state)
    b.style().unpolish(b)
    b.style().polish(b)
    return b


# ── Lumynex logo symbol ────────────────────────────────────────────────────

class LumynexSymbol(QWidget):
    """Draws the Lumynex logo mark (diamond gradient + ribbon bands + sparkle)."""

    def __init__(self, size: int = 44, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setAttribute(Qt.WA_TranslucentBackground)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)

        w, h   = float(self.width()), float(self.height())
        cx, cy = w / 2, h / 2

        sq = w * 0.70
        r  = sq * 0.20
        xf = QTransform()
        xf.translate(cx, cy)
        xf.rotate(45)
        xf.translate(-cx, -cy)

        rect_sq      = QRectF(cx - sq / 2, cy - sq / 2, sq, sq)
        diamond_path = QPainterPath()
        diamond_path.addRoundedRect(rect_sq, r, r)
        diamond = xf.map(diamond_path)

        grad = QLinearGradient(w * 0.08, h * 0.08, w * 0.92, h * 0.92)
        grad.setColorAt(0.00, QColor("#B39DFA"))
        grad.setColorAt(0.45, QColor("#8B5CF6"))
        grad.setColorAt(1.00, QColor("#5BA8F5"))
        p.fillPath(diamond, QBrush(grad))

        p.setClipPath(diamond)
        band_pen_w = w * 0.22
        arc_r      = w * 0.30

        p.setPen(QPen(QColor(255, 255, 255, 50), band_pen_w, Qt.SolidLine, Qt.RoundCap))
        arc_rect1 = QRectF(cx - arc_r - w * 0.04, cy - arc_r - w * 0.04, arc_r * 2, arc_r * 2)
        p.drawArc(arc_rect1, 45 * 16, 180 * 16)

        p.setPen(QPen(QColor(0, 0, 40, 35), band_pen_w, Qt.SolidLine, Qt.RoundCap))
        arc_rect2 = QRectF(cx - arc_r + w * 0.04, cy - arc_r + w * 0.04, arc_r * 2, arc_r * 2)
        p.drawArc(arc_rect2, 225 * 16, 180 * 16)
        p.setClipping(False)

        long_ray  = w * 0.16
        short_ray = w * 0.07

        p.setPen(QPen(QColor(255, 255, 255, 245), 1.4, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(cx, cy - long_ray),  QPointF(cx, cy + long_ray))
        p.drawLine(QPointF(cx - long_ray, cy),  QPointF(cx + long_ray, cy))

        p.setPen(QPen(QColor(255, 255, 255, 140), 0.9, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(cx - short_ray, cy - short_ray), QPointF(cx + short_ray, cy + short_ray))
        p.drawLine(QPointF(cx + short_ray, cy - short_ray), QPointF(cx - short_ray, cy + short_ray))

        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 255))
        p.drawEllipse(QPointF(cx, cy), 1.6, 1.6)
        p.end()


# ── Score ring ─────────────────────────────────────────────────────────────

class ScoreRing(QWidget):
    """Arc ring with gradient fill showing a score 0-100."""

    def __init__(self, score: int = 76, parent=None):
        super().__init__(parent)
        self.score = score
        self.setFixedSize(160, 160)
        self.setAttribute(Qt.WA_TranslucentBackground)

    def set_score(self, score: int) -> None:
        self.score = score
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        size   = min(self.width(), self.height())
        margin = 12
        rect   = QRectF(margin, margin, size - 2 * margin, size - 2 * margin)
        pen_w  = 10

        p.setPen(QPen(QColor(202, 191, 238, 120), pen_w, Qt.SolidLine, Qt.RoundCap))
        p.drawArc(rect, 225 * 16, -270 * 16)

        sweep = int(-270 * self.score / 100)
        grad  = QConicalGradient(rect.center(), 225)
        grad.setColorAt(0.0, QColor("#8B5CF6"))
        grad.setColorAt(1.0, QColor("#60A5FA"))
        p.setPen(QPen(QBrush(grad), pen_w, Qt.SolidLine, Qt.RoundCap))
        p.drawArc(rect, 225 * 16, sweep * 16)

        p.setPen(QColor("#0F0D1A"))
        p.setFont(QFont("Segoe UI Variable Display", 26, QFont.Bold))
        p.drawText(rect, Qt.AlignCenter, str(self.score))
        p.end()


# ── Floating sidebar tooltip ───────────────────────────────────────────────

class SidebarFloatingLabel(QLabel):
    """Pill label that floats to the right of the sidebar on hover."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SidebarFloatingLabel")
        self.setStyleSheet("""
            QLabel {
                background-color: #1C1929;
                color: #FFFFFF;
                border: 1px solid rgba(91, 63, 191, 0.30);
                border-radius: 8px;
                padding: 6px 14px;
                font-family: 'Segoe UI Variable', 'Segoe UI', sans-serif;
                font-size: 9pt;
                font-weight: 600;
            }
        """)
        self.setWindowFlags(Qt.ToolTip)
        self.hide()

        fx = QGraphicsDropShadowEffect()
        fx.setBlurRadius(22)
        fx.setOffset(3, 2)
        fx.setColor(QColor(0, 0, 0, 100))
        self.setGraphicsEffect(fx)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide)

    def show_next_to(self, btn: "SidebarNavButton", text: str) -> None:
        self._hide_timer.stop()
        self.setText(text)
        self.adjustSize()
        gp = btn.mapToGlobal(QPoint(0, 0))
        self.move(gp.x() + btn.width() + 8, gp.y() + (btn.height() - self.height()) // 2)
        self.show()
        self.raise_()

    def schedule_hide(self) -> None:
        self._hide_timer.start(120)


class SidebarNavButton(QPushButton):
    """Icon nav button that shows a floating name label on hover."""

    def __init__(self, icon: str, name: str, active: bool = False, parent=None):
        super().__init__(icon, parent)
        self._name = name
        self.setObjectName("NavButton")
        self.setProperty("active", "true" if active else "false")
        self.setFlat(True)
        self._label: SidebarFloatingLabel | None = None

    def set_active(self, active: bool) -> None:
        self.setProperty("active", "true" if active else "false")
        self.style().unpolish(self)
        self.style().polish(self)

    def set_floating_label(self, label: SidebarFloatingLabel) -> None:
        self._label = label

    def enterEvent(self, event):
        if self._label:
            self._label.show_next_to(self, self._name)
        super().enterEvent(event)

    def leaveEvent(self, event):
        if self._label:
            self._label.schedule_hide()
        super().leaveEvent(event)
