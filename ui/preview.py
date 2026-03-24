"""
UI Preview — Fluent Windows Control Center
Dashboard layout: icon sidebar · top bar · 3-section content
Run with: python -m ui.preview
"""
import sys
import os
import math

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QLabel, QPushButton, QFrame, QScrollArea, QTextEdit,
    QTableWidget, QTableWidgetItem, QHeaderView, QSizePolicy,
    QCheckBox, QSpinBox, QGridLayout,
)
from PyQt5.QtCore import Qt, QSize, QRectF, QPointF, QPoint, QPropertyAnimation, QEasingCurve, QTimer
from PyQt5.QtGui import (
    QFont, QColor, QPainter, QPen, QConicalGradient,
    QLinearGradient, QBrush, QPainterPath, QTransform,
)
from PyQt5.QtWidgets import QGraphicsDropShadowEffect


# ── Floating sidebar label (tooltip) ───────────────────────

class SidebarFloatingLabel(QLabel):
    """A floating pill label that appears to the right of the sidebar on hover."""

    def __init__(self, parent):
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

    def show_next_to(self, btn: "SidebarNavButton", text: str):
        self._hide_timer.stop()
        self.setText(text)
        self.adjustSize()
        # position: right edge of sidebar + 8px gap, vertically centred on button
        global_pos = btn.mapToGlobal(QPoint(0, 0))
        x = global_pos.x() + btn.width() + 8
        y = global_pos.y() + (btn.height() - self.height()) // 2
        self.move(x, y)
        self.show()
        self.raise_()

    def schedule_hide(self):
        self._hide_timer.start(120)


class SidebarNavButton(QPushButton):
    """Icon-only nav button that shows a floating name label on hover."""

    def __init__(self, icon: str, name: str, active: bool = False, parent=None):
        super().__init__(icon, parent)
        self._name = name
        self.setObjectName("NavButton")
        self.setProperty("active", "true" if active else "false")
        self.setFlat(True)
        self.style().unpolish(self)
        self.style().polish(self)
        self._label: SidebarFloatingLabel | None = None

    def set_floating_label(self, label: SidebarFloatingLabel):
        self._label = label

    def enterEvent(self, event):
        if self._label:
            self._label.show_next_to(self, self._name)
        super().enterEvent(event)

    def leaveEvent(self, event):
        if self._label:
            self._label.schedule_hide()
        super().leaveEvent(event)


# ── helpers ────────────────────────────────────────────────

def load_stylesheet() -> str:
    base = os.path.dirname(os.path.dirname(__file__))
    with open(os.path.join(base, "assets", "styles.qss"), encoding="utf-8") as f:
        return f.read()


def shadow(blur=20, dy=3, alpha=90, purple=False) -> QGraphicsDropShadowEffect:
    fx = QGraphicsDropShadowEffect()
    fx.setBlurRadius(blur)
    fx.setOffset(0, dy)
    fx.setColor(QColor(91, 63, 191, 28) if purple else QColor(15, 13, 26, alpha))
    return fx


def hline() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.HLine)
    return f


def section_header(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("SectionHeader")
    return lbl


def kv(key: str, value: str, style="DataValue") -> QWidget:
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
        lay.addWidget(w)
    return f


# ── Lumynex logo symbol ──────────────────────────────────────

class LumynexSymbol(QWidget):
    """
    Draws the Lumynex logo mark:
      - Rounded diamond (square rotated 45°) with purple→blue gradient fill
      - Two semi-transparent ribbon bands creating an interlocked depth effect
      - 4-pointed sparkle at the centre
    """

    def __init__(self, size: int = 44, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setAttribute(Qt.WA_TranslucentBackground)

    def paintEvent(self, _):
        import math
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)

        w, h   = float(self.width()), float(self.height())
        cx, cy = w / 2, h / 2

        # ── Diamond clip path (rounded square rotated 45°) ───
        sq = w * 0.70          # inner square side
        r  = sq * 0.20         # corner radius
        xf = QTransform()
        xf.translate(cx, cy)
        xf.rotate(45)
        xf.translate(-cx, -cy)

        rect_sq = QRectF(cx - sq / 2, cy - sq / 2, sq, sq)
        diamond_path = QPainterPath()
        diamond_path.addRoundedRect(rect_sq, r, r)
        diamond = xf.map(diamond_path)

        # ── Base gradient fill ────────────────────────────────
        grad = QLinearGradient(w * 0.08, h * 0.08, w * 0.92, h * 0.92)
        grad.setColorAt(0.00, QColor("#B39DFA"))  # light violet top-left
        grad.setColorAt(0.45, QColor("#8B5CF6"))  # core purple
        grad.setColorAt(1.00, QColor("#5BA8F5"))  # sky blue bottom-right
        p.fillPath(diamond, QBrush(grad))

        # ── Ribbon bands (clipped inside diamond) ────────────
        p.setClipPath(diamond)

        band_pen_w = w * 0.22
        arc_r      = w * 0.30

        # Band 1 — top-left ribbon (lighter, in front)
        p.setPen(QPen(QColor(255, 255, 255, 50), band_pen_w, Qt.SolidLine, Qt.RoundCap))
        arc_rect1 = QRectF(cx - arc_r - w * 0.04,
                            cy - arc_r - w * 0.04,
                            arc_r * 2, arc_r * 2)
        p.drawArc(arc_rect1, 45 * 16, 180 * 16)   # left semicircle

        # Band 2 — bottom-right ribbon (darker, behind)
        p.setPen(QPen(QColor(0, 0, 40, 35), band_pen_w, Qt.SolidLine, Qt.RoundCap))
        arc_rect2 = QRectF(cx - arc_r + w * 0.04,
                            cy - arc_r + w * 0.04,
                            arc_r * 2, arc_r * 2)
        p.drawArc(arc_rect2, 225 * 16, 180 * 16)  # right semicircle

        p.setClipping(False)

        # ── 4-pointed sparkle at centre ───────────────────────
        long_ray  = w * 0.16
        short_ray = w * 0.07

        # Main cross (N-S-E-W)
        p.setPen(QPen(QColor(255, 255, 255, 245), 1.4, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(cx, cy - long_ray),  QPointF(cx, cy + long_ray))
        p.drawLine(QPointF(cx - long_ray, cy),  QPointF(cx + long_ray, cy))

        # Diagonal cross (shorter)
        p.setPen(QPen(QColor(255, 255, 255, 140), 0.9, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(cx - short_ray, cy - short_ray),
                   QPointF(cx + short_ray, cy + short_ray))
        p.drawLine(QPointF(cx + short_ray, cy - short_ray),
                   QPointF(cx - short_ray, cy + short_ray))

        # Centre dot
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 255))
        p.drawEllipse(QPointF(cx, cy), 1.6, 1.6)

        p.end()


# ── Circular score ring ─────────────────────────────────────

class ScoreRing(QWidget):
    """Draws an arc ring with gradient fill showing a score 0–100."""

    def __init__(self, score: int = 76, parent=None):
        super().__init__(parent)
        self.score = score
        self.setFixedSize(160, 160)
        self.setAttribute(Qt.WA_TranslucentBackground)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        size = min(self.width(), self.height())
        margin = 12
        rect = QRectF(margin, margin, size - 2 * margin, size - 2 * margin)
        pen_w = 10

        # track ring — light purple on white
        p.setPen(QPen(QColor(202, 191, 238, 120), pen_w, Qt.SolidLine, Qt.RoundCap))
        p.drawArc(rect, 225 * 16, -270 * 16)

        # gradient arc — deep purple to mid purple
        sweep = int(-270 * self.score / 100)
        grad = QConicalGradient(rect.center(), 225)
        grad.setColorAt(0.0, QColor("#8B5CF6"))
        grad.setColorAt(1.0, QColor("#60A5FA"))
        p.setPen(QPen(QBrush(grad), pen_w, Qt.SolidLine, Qt.RoundCap))
        p.drawArc(rect, 225 * 16, sweep * 16)

        # score number — dark on white
        p.setPen(QColor("#0F0D1A"))
        p.setFont(QFont("Segoe UI Variable Display", 26, QFont.Bold))
        p.drawText(rect, Qt.AlignCenter, str(self.score))

        p.end()


# ── Main window ─────────────────────────────────────────────

class PreviewWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Lumynex")
        self.resize(1060, 730)
        self.setMinimumSize(860, 560)

        root = QWidget()
        root_lay = QHBoxLayout(root)
        root_lay.setContentsMargins(0, 0, 0, 0)
        root_lay.setSpacing(0)

        # ── Icon Sidebar ───────────────────────────────────
        sidebar = QWidget()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(68)
        sb = QVBoxLayout(sidebar)
        sb.setContentsMargins(0, 0, 0, 0)
        sb.setSpacing(4)

        logo = LumynexSymbol(size=44)
        logo_wrapper = QWidget()
        logo_wrapper.setStyleSheet("background: transparent;")
        logo_wrapper.setFixedHeight(60)
        lw = QVBoxLayout(logo_wrapper)
        lw.setContentsMargins(0, 8, 0, 8)
        lw.addWidget(logo, alignment=Qt.AlignCenter)
        sb.addWidget(logo_wrapper)
        sb.addSpacing(4)

        # Shared floating label — parented to None so it floats as a tooltip
        floating_label = SidebarFloatingLabel(None)

        nav_items = [
            ("◈", "Dashboard",       True),
            ("⬡", "Hardware",        False),
            ("✦", "Recommendations", False),
            ("↺", "Fix Display",     False),
            ("⚙", "Settings",        False),
        ]
        for icon, name, active in nav_items:
            btn = SidebarNavButton(icon, name, active)
            btn.set_floating_label(floating_label)
            wrapper = QWidget()
            wrapper.setStyleSheet("background:transparent;")
            wl = QHBoxLayout(wrapper)
            wl.setContentsMargins(0, 0, 0, 0)
            wl.addWidget(btn, alignment=Qt.AlignCenter)
            sb.addWidget(wrapper)

        sb.addStretch()
        root_lay.addWidget(sidebar)

        # ── Right panel ────────────────────────────────────
        right = QWidget()
        right.setObjectName("ContentArea")
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(0, 0, 0, 0)
        right_lay.setSpacing(0)

        # ── Top Bar ────────────────────────────────────────
        topbar = QWidget()
        topbar.setObjectName("TopBar")
        topbar.setFixedHeight(52)
        tb = QHBoxLayout(topbar)
        tb.setContentsMargins(24, 0, 16, 0)
        tb.setSpacing(12)

        name_block = QVBoxLayout()
        name_block.setSpacing(0)
        app_name = QLabel("Lumynex")
        app_name.setObjectName("AppTitle")
        name_block.addWidget(app_name)
        tb.addLayout(name_block)

        tb.addStretch()

        from PyQt5.QtWidgets import QLineEdit
        search = QLineEdit()
        search.setObjectName("SearchBox")
        search.setPlaceholderText("🔍  Search settings…")
        search.setFixedWidth(210)
        tb.addWidget(search)

        for icon in ["↺", "⚙"]:
            btn = QPushButton(icon)
            btn.setObjectName("TopBarIcon")
            tb.addWidget(btn)

        right_lay.addWidget(topbar)
        right_lay.addWidget(hline())

        # ── Scrollable Content ─────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        content = QWidget()
        content.setObjectName("ContentArea")
        lay = QVBoxLayout(content)
        lay.setContentsMargins(28, 8, 28, 32)
        lay.setSpacing(0)
        lay.setAlignment(Qt.AlignTop)

        # ══ SECTION 1: System Snapshot ═════════════════════
        lay.addWidget(section_header("System Snapshot"))

        snap_row = QHBoxLayout()
        snap_row.setSpacing(12)

        def snap_card(icon, title, big_value, sub, badge_text, badge_type):
            icon_lbl = QLabel(icon)
            icon_lbl.setObjectName("CardIcon")
            title_lbl = QLabel(title)
            title_lbl.setObjectName("CardTitle")
            val_lbl = QLabel(big_value)
            val_lbl.setObjectName("CardValue")
            sub_lbl = QLabel(sub)
            sub_lbl.setObjectName("CardSubValue")
            badge = QLabel(badge_text)
            badge.setObjectName("CardBadge")
            badge.setProperty("type", badge_type)
            badge.style().unpolish(badge)
            badge.style().polish(badge)
            badge_row = QWidget()
            badge_row.setStyleSheet("background:transparent;")
            br = QHBoxLayout(badge_row)
            br.setContentsMargins(0, 4, 0, 0)
            br.addWidget(badge)
            br.addStretch()
            c = card([icon_lbl, title_lbl, val_lbl, sub_lbl, badge_row])
            return c

        gpu_card = snap_card("🖥", "GPU", "RTX 3050", "NVIDIA  ·  6 GB VRAM", "Good", "good")
        cpu_card = snap_card("⚙", "CPU", "i5-13450HX", "10 cores  ·  16 threads", "Performance", "accent")
        disp_card = snap_card("◈", "Primary Display", "2560×1440", "180 Hz  ·  Scale 100%", "Optimal", "good")

        snap_row.addWidget(gpu_card)
        snap_row.addWidget(cpu_card)
        snap_row.addWidget(disp_card)
        lay.addLayout(snap_row)

        # ══ SECTION 2: System Understanding ════════════════
        lay.addWidget(section_header("System Understanding"))

        insight_row = QHBoxLayout()
        insight_row.setSpacing(12)

        # Left: Optimization Score
        score_frame = QFrame()
        score_frame.setObjectName("Card")
        score_frame.setProperty("state", "accent")
        score_frame.style().unpolish(score_frame)
        score_frame.style().polish(score_frame)
        score_frame.setGraphicsEffect(shadow(24, 4, 60, purple=True))
        score_frame.setFixedWidth(230)
        sf_lay = QVBoxLayout(score_frame)
        sf_lay.setContentsMargins(20, 20, 20, 20)
        sf_lay.setSpacing(8)

        score_title = QLabel("Display Optimization Score")
        score_title.setObjectName("CardTitle")
        score_title.setWordWrap(True)
        sf_lay.addWidget(score_title)

        ring = ScoreRing(76)
        sf_lay.addWidget(ring, alignment=Qt.AlignCenter)

        breakdown_label = QLabel("ISSUES DETECTED")
        breakdown_label.setObjectName("ScoreLabel")
        sf_lay.addWidget(breakdown_label)

        for issue in [
            "Resolution mismatch on DISPLAY5",
            "Refresh rate not optimal",
            "Scaling inconsistency",
        ]:
            row_w = QWidget()
            row_w.setStyleSheet("background:transparent;")
            rl = QHBoxLayout(row_w)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.setSpacing(4)
            dot = QLabel("•")
            dot.setObjectName("ScoreBreakdownDot")
            txt = QLabel(issue)
            txt.setObjectName("ScoreBreakdownItem")
            rl.addWidget(dot)
            rl.addWidget(txt)
            rl.addStretch()
            sf_lay.addWidget(row_w)

        sf_lay.addStretch()
        insight_row.addWidget(score_frame)

        # Right: Connected Displays table
        disp_frame = QFrame()
        disp_frame.setObjectName("Card")
        disp_frame.setGraphicsEffect(shadow())
        df_lay = QVBoxLayout(disp_frame)
        df_lay.setContentsMargins(20, 18, 20, 20)
        df_lay.setSpacing(10)

        tbl_title = QLabel("Connected Displays")
        tbl_title.setObjectName("CardTitle")
        df_lay.addWidget(tbl_title)

        tbl = QTableWidget(2, 4)
        tbl.setHorizontalHeaderLabels(["Display", "Resolution", "Refresh Rate", "Status"])
        tbl.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        tbl.verticalHeader().setVisible(False)
        tbl.setShowGrid(False)
        tbl.setAlternatingRowColors(True)
        tbl.setMinimumHeight(110)

        rows_data = [
            ("Dell P2422H  (HDMI)", "1080 × 1920", "60 Hz",  "✓ Active"),
            ("Generic PnP  [Primary]", "2560 × 1440", "180 Hz", "✓ Active"),
        ]
        for r, rd in enumerate(rows_data):
            for c, val in enumerate(rd):
                item = QTableWidgetItem(val)
                tbl.setItem(r, c, item)

        df_lay.addWidget(tbl)
        insight_row.addWidget(disp_frame, stretch=1)
        lay.addLayout(insight_row)

        # ══ SECTION 3: Recommendation Engine ═══════════════
        lay.addWidget(section_header("Recommended Settings"))

        rec_header = QLabel("Recommended Settings for Your Setup")
        rec_header.setObjectName("RecommendationHeader")
        lay.addWidget(rec_header)

        rec_sub = QLabel(
            "Based on your NVIDIA RTX 3050 (high-end) and connected displays, "
            "these settings will give you the best performance."
        )
        rec_sub.setObjectName("RecommendationSub")
        rec_sub.setWordWrap(True)
        lay.addWidget(rec_sub)

        rec_cards_row = QHBoxLayout()
        rec_cards_row.setSpacing(12)

        rec1 = card([
            *[kv(k, v, s) for k, v, s in [
                ("Display",     "DISPLAY6  (Primary)", "DataValue"),
                ("Resolution",  "2560 × 1440",         "DataValueMatch"),
                ("Refresh",     "180 Hz",               "DataValueHighlight"),
                ("Scale",       "100%",                 "DataValueMatch"),
                ("Bit Depth",   "32 bpp",               "DataValueMatch"),
            ]],
        ], state="ok")
        rec_cards_row.addWidget(rec1)

        rec2_items = [
            kv("Display",    "DISPLAY5  (Dell P2422H)", "DataValue"),
            kv("Resolution", "1080 × 1920",              "DataValueMatch"),
            kv("Refresh",    "60 Hz",                    "DataValueMismatch"),
            kv("Scale",      "100%",                     "DataValueMatch"),
            kv("Bit Depth",  "32 bpp",                   "DataValueMatch"),
        ]
        warn_note = QLabel("⚠  Refresh rate not at recommended value")
        warn_note.setObjectName("ScoreBreakdownDot")
        warn_note.setWordWrap(True)
        rec2 = card(rec2_items + [warn_note], state="warning")
        rec_cards_row.addWidget(rec2)

        lay.addLayout(rec_cards_row)
        lay.addSpacing(16)

        # Action buttons
        action_row = QHBoxLayout()
        action_row.setSpacing(10)

        apply_btn = QPushButton("✓  Apply Settings")
        apply_btn.setObjectName("ApplyButton")
        apply_btn.setGraphicsEffect(shadow(28, 4, 55))

        fix_btn = QPushButton("↺  Fix Display")
        fix_btn.setObjectName("FixButton")

        cancel_btn = QPushButton("Cancel")
        disabled_btn = QPushButton("Applying…")
        disabled_btn.setDisabled(True)

        for b in [apply_btn, fix_btn, cancel_btn, disabled_btn]:
            action_row.addWidget(b)
        action_row.addStretch()
        lay.addLayout(action_row)
        lay.addSpacing(4)

        # ── Status feedback ────────────────────────────────
        lay.addWidget(section_header("Status"))

        for state, text in [
            ("idle",    "Ready — no operation in progress"),
            ("running", "→  Applying settings to DISPLAY6…"),
            ("success", "✓  All settings applied successfully  ·  validation passed"),
            ("error",   "✕  Apply failed on DISPLAY5  ·  rolled back to previous configuration"),
        ]:
            sb_w = QLabel(text)
            sb_w.setObjectName("StatusBox")
            sb_w.setProperty("state", state)
            sb_w.style().unpolish(sb_w)
            sb_w.style().polish(sb_w)
            sb_w.setWordWrap(True)
            lay.addWidget(sb_w)
            lay.addSpacing(4)

        # ── Status badges ──────────────────────────────────
        lay.addWidget(section_header("Status Badges"))
        badge_row = QHBoxLayout()
        badge_row.setSpacing(8)
        for state, label in [
            ("normal",   "● All displays nominal"),
            ("warning",  "⚠ Mismatch detected"),
            ("applying", "↻ Applying settings"),
            ("error",    "✕ Rollback occurred"),
        ]:
            b = QLabel(label)
            b.setObjectName("StatusBadge")
            b.setProperty("state", state)
            b.style().unpolish(b)
            b.style().polish(b)
            badge_row.addWidget(b)
        badge_row.addStretch()
        lay.addLayout(badge_row)

        # ── Reset History ──────────────────────────────────
        lay.addWidget(section_header("Reset History"))
        hist = QTableWidget(3, 4)
        hist.setHorizontalHeaderLabels(["Timestamp", "Type", "Display", "Result"])
        hist.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        hist.verticalHeader().setVisible(False)
        hist.setMaximumHeight(122)
        hist.setShowGrid(False)
        hist.setAlternatingRowColors(True)
        for r, rd in enumerate([
            ("2026-03-22  19:56", "Soft Reset", "DISPLAY6", "✓ Success"),
            ("2026-03-22  18:30", "Apply",      "DISPLAY5", "✓ Success"),
            ("2026-03-21  09:12", "Apply",      "DISPLAY6", "↩ Rollback"),
        ]):
            for c, val in enumerate(rd):
                hist.setItem(r, c, QTableWidgetItem(val))
        lay.addWidget(hist)

        # ── Event Log ──────────────────────────────────────
        lay.addWidget(section_header("Event Log"))
        log = QTextEdit()
        log.setObjectName("LogViewer")
        log.setReadOnly(True)
        log.setMaximumHeight(88)
        log.setPlainText(
            "2026-03-22 19:56:33  [INFO ]  hardware: snapshot collected\n"
            "2026-03-22 19:56:35  [INFO ]  hardware: 2 gpu(s), 2 monitor(s) found\n"
            "2026-03-22 20:02:30  [INFO ]  display_config: applied DISPLAY6 2560x1440@180hz\n"
            "2026-03-22 20:02:30  [INFO ]  display_config: validation passed\n"
            "2026-03-22 20:02:30  [DEBUG]  persistence: settings saved to user_settings.json"
        )
        lay.addWidget(log)
        lay.addStretch()

        scroll.setWidget(content)
        right_lay.addWidget(scroll)
        root_lay.addWidget(right)

        self.setCentralWidget(root)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet(load_stylesheet())
    win = PreviewWindow()
    win.show()
    sys.exit(app.exec_())
