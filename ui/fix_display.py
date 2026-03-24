"""
Fix Display Screen — one-click soft reset with real-time status feedback.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QScrollArea,
)

from ui.widgets import section_header, shadow

if TYPE_CHECKING:
    from ui.main_window import MainWindow


class FixDisplayScreen(QWidget):

    def __init__(self, main_window: "MainWindow", parent=None):
        super().__init__(parent)
        self._mw = main_window
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        content = QWidget()
        content.setObjectName("ContentArea")
        lay = QVBoxLayout(content)
        lay.setContentsMargins(28, 8, 28, 32)
        lay.setSpacing(0)
        lay.setAlignment(Qt.AlignTop)

        lay.addWidget(section_header("Fix Display"))

        # Description
        desc = QLabel(
            "Having display issues? Flickering, wrong resolution after sleep, or a blank screen?\n\n"
            "Soft Reset forces Windows to reapply your display settings and refresh the "
            "display driver — without touching any cables. On hybrid GPU systems (e.g. "
            "Intel + NVIDIA Optimus) the safe reapply method is used automatically.\n\n"
            "Requires Administrator privileges."
        )
        desc.setObjectName("RecommendationSub")
        desc.setWordWrap(True)
        lay.addWidget(desc)
        lay.addSpacing(24)

        # Admin required note (shown when not admin)
        self._admin_note = QLabel(
            "⚠  Administrator privileges required. Restart Lumynex as Administrator to enable Soft Reset."
        )
        self._admin_note.setObjectName("StatusBox")
        self._admin_note.setProperty("state", "idle")
        self._admin_note.setWordWrap(True)
        self._admin_note.setVisible(False)
        lay.addWidget(self._admin_note)
        lay.addSpacing(12)

        # Reset button (centred)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._reset_btn = QPushButton("Soft Reset")
        self._reset_btn.setObjectName("SoftResetButton")
        self._reset_btn.setGraphicsEffect(shadow(28, 4, 55))
        self._reset_btn.clicked.connect(self._mw.on_soft_reset)
        btn_row.addWidget(self._reset_btn)
        btn_row.addStretch()
        lay.addLayout(btn_row)
        lay.addSpacing(28)

        # Status area
        lay.addWidget(section_header("Status"))
        self._status_box = QLabel("Idle. No reset has been run this session.")
        self._status_box.setObjectName("StatusBox")
        self._status_box.setProperty("state", "idle")
        self._status_box.setWordWrap(True)
        lay.addWidget(self._status_box)
        lay.addSpacing(14)

        # Metadata row
        meta_row = QHBoxLayout()
        meta_row.setSpacing(24)

        last_lbl = QLabel("Last reset:")
        last_lbl.setObjectName("DataKey")
        last_lbl.setFixedWidth(80)
        self._last_reset_val = QLabel("Never")
        self._last_reset_val.setObjectName("DataValue")

        method_lbl = QLabel("Method:")
        method_lbl.setObjectName("DataKey")
        method_lbl.setFixedWidth(60)
        self._method_val = QLabel("—")
        self._method_val.setObjectName("DataValue")

        meta_row.addWidget(last_lbl)
        meta_row.addWidget(self._last_reset_val)
        meta_row.addSpacing(20)
        meta_row.addWidget(method_lbl)
        meta_row.addWidget(self._method_val)
        meta_row.addStretch()
        lay.addLayout(meta_row)
        lay.addStretch()

        scroll.setWidget(content)
        root.addWidget(scroll)

    # ── Public API called by MainWindow ────────────────────────────────────

    def set_admin_mode(self, is_admin: bool) -> None:
        """Call once after build to lock down buttons when not running as admin."""
        if not is_admin:
            self._reset_btn.setEnabled(False)
            self._admin_note.setVisible(True)
        else:
            self._reset_btn.setEnabled(True)
            self._admin_note.setVisible(False)

    def set_status(self, text: str, state: str = "idle") -> None:
        """state: 'idle' | 'running' | 'success' | 'error'"""
        self._status_box.setText(text)
        self._status_box.setProperty("state", state)
        self._status_box.style().unpolish(self._status_box)
        self._status_box.style().polish(self._status_box)

    def set_running(self, running: bool) -> None:
        # Only toggle if admin; non-admin button stays disabled always
        if self._mw.is_admin:
            self._reset_btn.setEnabled(not running)
        if running:
            self._reset_btn.setText("Resetting…")
        else:
            self._reset_btn.setText("Soft Reset")

    def set_last_reset(self, timestamp: str, method: str) -> None:
        self._last_reset_val.setText(timestamp)
        self._method_val.setText(method)

    def refresh(self) -> None:
        """Called when screen becomes visible — load last reset from history."""
        from utils.persistence import get_reset_history
        history = get_reset_history(limit=1)
        resets = [e for e in history if e.get("type") == "RESET"]
        if resets:
            last = resets[-1]
            method = last.get("extra", {}).get("method", "Unknown")
            self.set_last_reset(last.get("ts", "?"), method)
