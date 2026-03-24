"""
Recommendations Screen — per-monitor current vs recommended settings + Apply.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QFrame,
)

from ui.widgets import section_header, shadow, kv, hline

if TYPE_CHECKING:
    from ui.main_window import MainWindow


class RecommendationsScreen(QWidget):

    def __init__(self, main_window: "MainWindow", parent=None):
        super().__init__(parent)
        self._mw = main_window
        self._apply_enabled: bool = True
        self._current_apply_btns: List[QPushButton] = []
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self._content = QWidget()
        self._content.setObjectName("ContentArea")
        self._lay = QVBoxLayout(self._content)
        self._lay.setContentsMargins(28, 8, 28, 32)
        self._lay.setSpacing(0)
        self._lay.setAlignment(Qt.AlignTop)

        lbl = QLabel("Loading…")
        lbl.setObjectName("SectionSubheader")
        self._lay.addWidget(lbl)

        scroll.setWidget(self._content)
        root.addWidget(scroll)

    # ── Public API ─────────────────────────────────────────────────────────

    def set_apply_enabled(self, enabled: bool) -> None:
        """Enable/disable all apply buttons. Called by MainWindow during operations."""
        self._apply_enabled = enabled
        for btn in self._current_apply_btns:
            btn.setEnabled(enabled)

    def refresh(self) -> None:
        mw = self._mw
        if mw.snapshot is None:
            return

        # Clear layout and button refs
        self._current_apply_btns = []
        while self._lay.count():
            item = self._lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        recs = mw.recommendations
        cfgs = mw.monitor_configs

        if not recs:
            lbl = QLabel("No recommendations available — refresh hardware data first.")
            lbl.setObjectName("SectionSubheader")
            self._lay.addWidget(lbl)
            return

        self._lay.addWidget(section_header("Recommendations"))

        gpu_name = mw.snapshot.gpus[0].name if mw.snapshot.gpus else "Unknown GPU"
        gpu_vendor = mw.snapshot.gpus[0].vendor.upper() if mw.snapshot.gpus else ""
        sub = QLabel(
            f"Based on {gpu_name} and your connected displays, "
            "these settings will give you the best experience."
        )
        sub.setObjectName("RecommendationSub")
        sub.setWordWrap(True)
        self._lay.addWidget(sub)

        # Non-admin warning banner
        if not mw.is_admin:
            warn = QLabel(
                "⚠  Read-Only Mode — Restart Lumynex as Administrator to apply recommendations."
            )
            warn.setObjectName("StatusBox")
            warn.setProperty("state", "idle")
            warn.setWordWrap(True)
            self._lay.addWidget(warn)

        all_match = True

        for rec in recs:
            cfg = cfgs.get(rec.monitor_id)

            res_match  = cfg and rec.recommended_width  == cfg.width and rec.recommended_height == cfg.height
            hz_match   = cfg and rec.recommended_refresh == cfg.refresh_rate
            bpp_match  = cfg and rec.bit_depth == cfg.bits_per_pixel

            if not (res_match and hz_match and bpp_match):
                all_match = False

            card_state = "ok" if (res_match and hz_match and bpp_match) else "warning"

            frame = QFrame()
            frame.setObjectName("Card")
            frame.setProperty("state", card_state)
            frame.style().unpolish(frame)
            frame.style().polish(frame)
            frame.setGraphicsEffect(shadow())
            lay = QVBoxLayout(frame)
            lay.setContentsMargins(20, 18, 20, 20)
            lay.setSpacing(6)

            # Title row
            title_row = QHBoxLayout()
            mon_lbl = QLabel(rec.monitor_id)
            mon_lbl.setObjectName("CardTitle")
            title_row.addWidget(mon_lbl)
            if getattr(next((m for m in mw.snapshot.monitors if m.device_name == rec.monitor_id), None), 'is_primary', False):
                badge = QLabel("Primary")
                badge.setObjectName("PrimaryBadge")
                title_row.addWidget(badge)
            title_row.addStretch()
            title_row_w = QWidget()
            title_row_w.setStyleSheet("background:transparent;")
            QHBoxLayout(title_row_w)
            lay.addLayout(title_row)
            lay.addWidget(hline())

            # Two-column comparison table
            def _row(label: str, current: str, recommended: str, match: bool) -> QWidget:
                w = QWidget()
                w.setStyleSheet("background:transparent;")
                hl = QHBoxLayout(w)
                hl.setContentsMargins(0, 3, 0, 3)
                hl.setSpacing(0)
                lbl_w = QLabel(label)
                lbl_w.setObjectName("DataKey")
                lbl_w.setFixedWidth(80)
                cur_w = QLabel(current)
                cur_w.setObjectName("DataValue")
                cur_w.setFixedWidth(130)
                rec_w = QLabel(recommended)
                rec_w.setObjectName("DataValueMatch" if match else "DataValueMismatch")
                rec_w.setFixedWidth(130)
                tick = QLabel("OK" if match else "!")
                tick.setObjectName("DataValueMatch" if match else "DataValueMismatch")
                tick.setFixedWidth(24)
                hl.addWidget(lbl_w)
                hl.addWidget(cur_w)
                hl.addWidget(rec_w)
                hl.addWidget(tick)
                hl.addStretch()
                return w

            # Column headers
            hdr = QWidget()
            hdr.setStyleSheet("background:transparent;")
            hl = QHBoxLayout(hdr)
            hl.setContentsMargins(0, 0, 0, 4)
            hl.setSpacing(0)
            for lbl_txt, w in [("", 80), ("Current", 130), ("Recommended", 130), ("", 24)]:
                l = QLabel(lbl_txt)
                l.setObjectName("DataKey")
                l.setFixedWidth(w)
                hl.addWidget(l)
            hl.addStretch()
            lay.addWidget(hdr)

            cur_res  = f"{cfg.width}x{cfg.height}"   if cfg else "?"
            rec_res  = f"{rec.recommended_width}x{rec.recommended_height}"
            cur_hz   = f"{cfg.refresh_rate} Hz"       if cfg else "?"
            rec_hz   = f"{rec.recommended_refresh} Hz"
            cur_bpp  = f"{cfg.bits_per_pixel} bpp"    if cfg else "?"
            rec_bpp  = f"{rec.bit_depth} bpp"

            lay.addWidget(_row("Resolution",  cur_res,  rec_res,  res_match))
            lay.addWidget(_row("Refresh",     cur_hz,   rec_hz,   hz_match))
            lay.addWidget(_row("Bit Depth",   cur_bpp,  rec_bpp,  bpp_match))

            reason_lbl = QLabel(f"Reason: {rec.reason}")
            reason_lbl.setObjectName("ReasonText")
            reason_lbl.setWordWrap(True)
            lay.addWidget(reason_lbl)

            if rec.conflict:
                warn_lbl = QLabel(f"Warning: {rec.conflict}")
                warn_lbl.setObjectName("ScoreBreakdownDot")
                warn_lbl.setWordWrap(True)
                lay.addWidget(warn_lbl)

            # GPU control panel override hint (shown when mismatch + discrete GPU)
            if not (res_match and hz_match and bpp_match) and gpu_vendor in ("NVIDIA", "AMD"):
                panel_name = "NVIDIA Control Panel" if gpu_vendor == "NVIDIA" else "AMD Software (Adrenalin)"
                hint_lbl = QLabel(
                    f"Tip: If settings keep reverting after applying, check {panel_name} "
                    "for display overrides."
                )
                hint_lbl.setObjectName("ReasonText")
                hint_lbl.setWordWrap(True)
                lay.addWidget(hint_lbl)

            # Per-monitor apply button — greyed out when already at recommended settings
            already_optimal = bool(res_match and hz_match and bpp_match)
            btn_row = QHBoxLayout()
            btn_row.addStretch()
            apply_btn = QPushButton("Already Optimal" if already_optimal else "Apply This Monitor")
            apply_btn.setObjectName("ApplyButton")
            apply_btn.setEnabled(self._apply_enabled and not already_optimal)
            if not already_optimal:
                _rec_copy = rec
                apply_btn.clicked.connect(lambda _, r=_rec_copy: self._mw.on_apply_single(r))
            btn_row.addWidget(apply_btn)
            lay.addLayout(btn_row)
            if not already_optimal:
                self._current_apply_btns.append(apply_btn)

            self._lay.addWidget(frame)
            self._lay.addSpacing(10)

        # Apply All button — greyed out when every monitor is already optimal
        self._lay.addSpacing(6)
        row = QHBoxLayout()
        apply_all = QPushButton(
            "All Monitors Optimal" if all_match else "Apply All Recommendations"
        )
        apply_all.setObjectName("ApplyButton")
        apply_all.setGraphicsEffect(shadow(28, 4, 55))
        apply_all.setEnabled(self._apply_enabled and not all_match)
        if not all_match:
            apply_all.clicked.connect(self._mw.on_apply_all)
            self._current_apply_btns.append(apply_all)
        row.addWidget(apply_all)
        row.addStretch()
        self._lay.addLayout(row)
        self._lay.addStretch()
        self._current_apply_btns.append(apply_all)
