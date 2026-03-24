"""
Dashboard Screen — at-a-glance system state.
Shows GPU/CPU/display summary cards, score ring, and primary action buttons.
Data is injected by MainWindow after background load; refresh() re-renders.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List, Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QScrollArea, QTableWidget,
    QTableWidgetItem, QHeaderView,
)

from ui.widgets import section_header, shadow, kv, card, ScoreRing, hline

if TYPE_CHECKING:
    from ui.main_window import MainWindow


class DashboardScreen(QWidget):

    def __init__(self, main_window: "MainWindow", parent=None):
        super().__init__(parent)
        self._mw = main_window
        self._score_ring: Optional[ScoreRing] = None
        self._apply_enabled: bool = True
        self._apply_btn: Optional[QPushButton] = None
        self._build()

    # ── Build ──────────────────────────────────────────────────────────────

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        self._content = QWidget()
        self._content.setObjectName("ContentArea")
        self._content.setMinimumWidth(680)   # 3 × 200px cards + margins + spacing
        self._lay = QVBoxLayout(self._content)
        self._lay.setContentsMargins(28, 8, 28, 32)
        self._lay.setSpacing(0)
        self._lay.setAlignment(Qt.AlignTop)

        self._render_placeholder()

        scroll.setWidget(self._content)
        root.addWidget(scroll)

    def _render_placeholder(self) -> None:
        lbl = QLabel("Loading hardware data…")
        lbl.setObjectName("SectionSubheader")
        lbl.setAlignment(Qt.AlignCenter)
        self._lay.addWidget(lbl)

    # ── Public API ─────────────────────────────────────────────────────────

    def set_apply_enabled(self, enabled: bool) -> None:
        """Enable/disable the Apply Recommendations button."""
        self._apply_enabled = enabled
        if self._apply_btn is not None:
            self._apply_btn.setEnabled(enabled)

    def refresh(self) -> None:
        """Called by MainWindow after data is loaded or on screen switch."""
        mw = self._mw
        if mw.snapshot is None:
            return

        # Clear existing content and button ref
        self._apply_btn = None
        while self._lay.count():
            item = self._lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        snap   = mw.snapshot
        recs   = mw.recommendations
        cfgs   = mw.monitor_configs

        # ── Section 1: System Snapshot ────────────────────────────────────
        self._lay.addWidget(section_header("System Snapshot"))

        snap_row = QHBoxLayout()
        snap_row.setSpacing(12)

        # GPU card
        best_gpu = snap.gpus[0] if snap.gpus else None
        gpu_name  = best_gpu.name if best_gpu else "Unknown"
        gpu_vram  = f"{best_gpu.vram_mb // 1024} GB VRAM" if best_gpu and best_gpu.vram_mb > 0 else "Shared VRAM"
        gpu_badge = "good" if best_gpu and best_gpu.vram_mb >= 4096 else "limited"
        snap_row.addWidget(self._snap_card("GPU", gpu_name, gpu_vram, "Detected", gpu_badge), stretch=1)

        # CPU card
        cpu = snap.cpu
        cpu_threads = f"{cpu.cores} cores  {cpu.logical_processors} threads" if cpu else "Unknown"
        snap_row.addWidget(self._snap_card("CPU", cpu.name if cpu else "Unknown", cpu_threads, "Detected", "accent"), stretch=1)

        # Primary display card
        primary_mon = next((m for m in snap.monitors if m.is_primary), None)
        if primary_mon:
            cfg = cfgs.get(primary_mon.device_name)
            if cfg:
                disp_val = f"{cfg.width}x{cfg.height}"
                disp_sub = f"{cfg.refresh_rate} Hz  Scale {primary_mon.scale_factor}%"
            else:
                disp_val = primary_mon.device_name
                disp_sub = ""
        else:
            disp_val = "No primary"
            disp_sub = ""
            cfg = None

        # Check if primary display matches its recommendation
        rec_match = True
        if primary_mon and recs:
            rec = next((r for r in recs if r.monitor_id == primary_mon.device_name), None)
            if rec and cfg:
                rec_match = (
                    rec.recommended_width  == cfg.width and
                    rec.recommended_height == cfg.height and
                    rec.recommended_refresh == cfg.refresh_rate
                )
        disp_badge = "good" if rec_match else "limited"
        snap_row.addWidget(self._snap_card("Primary Display", disp_val, disp_sub, "Optimal" if rec_match else "Mismatch", disp_badge), stretch=1)

        self._lay.addLayout(snap_row)

        # ── Section 2: System Understanding ──────────────────────────────
        self._lay.addWidget(section_header("System Understanding"))

        insight_row = QHBoxLayout()
        insight_row.setSpacing(12)

        # Score ring
        mismatches = []
        for r in recs:
            cfg = cfgs.get(r.monitor_id)
            if cfg:
                if r.recommended_width  != cfg.width:        mismatches.append(f"Resolution mismatch on {r.monitor_id}")
                if r.recommended_refresh != cfg.refresh_rate: mismatches.append(f"Refresh mismatch on {r.monitor_id}")

        issue_count = len(mismatches)
        score = max(10, 100 - issue_count * 12)

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

        self._score_ring = ScoreRing(score)
        sf_lay.addWidget(self._score_ring, alignment=Qt.AlignCenter)

        issues_lbl = QLabel("ALL GOOD" if not mismatches else "ISSUES DETECTED")
        issues_lbl.setObjectName("ScoreLabel")
        sf_lay.addWidget(issues_lbl)

        for issue in (mismatches[:3] if mismatches else ["All settings optimal"]):
            row_w = QWidget()
            row_w.setStyleSheet("background:transparent;")
            rl = QHBoxLayout(row_w)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.setSpacing(4)
            dot = QLabel("o")
            dot.setObjectName("ScoreBreakdownDot")
            txt = QLabel(issue)
            txt.setObjectName("ScoreBreakdownItem")
            rl.addWidget(dot)
            rl.addWidget(txt)
            rl.addStretch()
            sf_lay.addWidget(row_w)

        sf_lay.addStretch()
        insight_row.addWidget(score_frame)

        # Connected displays table
        disp_frame = QFrame()
        disp_frame.setObjectName("Card")
        disp_frame.setGraphicsEffect(shadow())
        df_lay = QVBoxLayout(disp_frame)
        df_lay.setContentsMargins(20, 18, 20, 20)
        df_lay.setSpacing(10)

        tbl_title = QLabel("Connected Displays")
        tbl_title.setObjectName("CardTitle")
        df_lay.addWidget(tbl_title)

        tbl = QTableWidget(len(snap.monitors), 4)
        tbl.setHorizontalHeaderLabels(["Display", "Resolution", "Refresh Rate", "Status"])
        tbl.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        tbl.verticalHeader().setVisible(False)
        tbl.setShowGrid(False)
        tbl.setAlternatingRowColors(True)
        tbl.setMinimumHeight(40 + len(snap.monitors) * 38)

        for i, mon in enumerate(snap.monitors):
            cfg = cfgs.get(mon.device_name)
            name_str = f"{mon.device_name}{'  [Primary]' if mon.is_primary else ''}"
            res_str  = f"{cfg.width} x {cfg.height}" if cfg else "?"
            hz_str   = f"{cfg.refresh_rate} Hz" if cfg else "?"

            rec = next((r for r in recs if r.monitor_id == mon.device_name), None)
            status = "Active"
            if rec and cfg:
                all_match = (rec.recommended_width == cfg.width and
                             rec.recommended_height == cfg.height and
                             rec.recommended_refresh == cfg.refresh_rate)
                status = "OK" if all_match else "Mismatch"

            for j, val in enumerate([name_str, res_str, hz_str, status]):
                item = QTableWidgetItem(val)
                tbl.setItem(i, j, item)

        df_lay.addWidget(tbl)
        insight_row.addWidget(disp_frame, stretch=1)
        self._lay.addLayout(insight_row)

        # ── Section 3: Quick Actions ──────────────────────────────────────
        self._lay.addWidget(section_header("Actions"))

        # Non-admin note
        if not mw.is_admin:
            note = QLabel("⚠  Read-Only Mode — Restart as Administrator to apply settings.")
            note.setObjectName("ReasonText")
            self._lay.addWidget(note)
            self._lay.addSpacing(8)

        action_row = QHBoxLayout()
        action_row.setSpacing(10)

        self._apply_btn = QPushButton("Apply Recommendations")
        self._apply_btn.setObjectName("ApplyButton")
        self._apply_btn.setGraphicsEffect(shadow(28, 4, 55))
        self._apply_btn.setEnabled(self._apply_enabled)
        self._apply_btn.clicked.connect(self._mw.on_apply_all)

        fix_btn = QPushButton("Fix Display")
        fix_btn.setObjectName("FixButton")
        fix_btn.clicked.connect(lambda: self._mw.navigate_to(3))  # Fix Display = index 3

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._mw.refresh_data)

        for b in [self._apply_btn, fix_btn, refresh_btn]:
            action_row.addWidget(b)
        action_row.addStretch()
        self._lay.addLayout(action_row)
        self._lay.addStretch()

    # ── Internal card builder ──────────────────────────────────────────────

    def _snap_card(self, title: str, value: str, sub: str, badge_text: str, badge_type: str) -> QFrame:
        title_lbl = QLabel(title)
        title_lbl.setObjectName("CardTitle")
        val_lbl = QLabel(value)
        val_lbl.setObjectName("CardValue")
        val_lbl.setWordWrap(True)
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
        f = card([title_lbl, val_lbl, sub_lbl, badge_row])
        f.setMinimumWidth(200)
        return f
