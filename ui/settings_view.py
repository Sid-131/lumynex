"""
Settings Screen — app preferences, reset history, and event log viewer.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QCheckBox, QComboBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QTextEdit,
)

from ui.widgets import section_header, card, kv, hline
from utils.persistence import (
    load_settings, save_settings,
    get_event_log, get_reset_history, clear_event_log,
)

if TYPE_CHECKING:
    from ui.main_window import MainWindow

_POLL_OPTIONS   = [3, 5, 10, 15, 30]
_DEBOUNCE_OPTIONS = [3, 5, 10, 15]


class SettingsScreen(QWidget):

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

        settings = load_settings()

        # ── Behaviour ─────────────────────────────────────────────────────
        lay.addWidget(section_header("Behaviour"))

        self._auto_apply_cb = QCheckBox("Auto-apply recommendations on startup")
        self._auto_apply_cb.setChecked(bool(settings.get("auto_apply_on_startup", False)))

        self._notify_cb = QCheckBox("Notify on mismatch")
        self._notify_cb.setChecked(bool(settings.get("notify_on_mismatch", True)))

        poll_row = QHBoxLayout()
        poll_lbl = QLabel("Polling interval")
        poll_lbl.setObjectName("DataKey")
        poll_lbl.setFixedWidth(160)
        self._poll_combo = QComboBox()
        for v in _POLL_OPTIONS:
            self._poll_combo.addItem(f"{v} s", v)
        cur_poll = settings.get("polling_interval_seconds", 5)
        idx = _POLL_OPTIONS.index(cur_poll) if cur_poll in _POLL_OPTIONS else 1
        self._poll_combo.setCurrentIndex(idx)
        self._poll_combo.setFixedWidth(100)
        poll_row.addWidget(poll_lbl)
        poll_row.addWidget(self._poll_combo)
        poll_row.addStretch()

        debounce_row = QHBoxLayout()
        db_lbl = QLabel("Reset debounce")
        db_lbl.setObjectName("DataKey")
        db_lbl.setFixedWidth(160)
        self._debounce_combo = QComboBox()
        for v in _DEBOUNCE_OPTIONS:
            self._debounce_combo.addItem(f"{v} s", v)
        cur_db = settings.get("reset_debounce_seconds", 5)
        idx2 = _DEBOUNCE_OPTIONS.index(cur_db) if cur_db in _DEBOUNCE_OPTIONS else 1
        self._debounce_combo.setCurrentIndex(idx2)
        self._debounce_combo.setFixedWidth(100)
        debounce_row.addWidget(db_lbl)
        debounce_row.addWidget(self._debounce_combo)
        debounce_row.addStretch()

        beh_card_w = QWidget()
        beh_card_w.setStyleSheet("background:transparent;")
        bl = QVBoxLayout(beh_card_w)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(10)
        bl.addWidget(self._auto_apply_cb)
        bl.addWidget(self._notify_cb)
        bl.addLayout(poll_row)
        bl.addLayout(debounce_row)

        lay.addWidget(card([beh_card_w]))

        # ── Reset History ─────────────────────────────────────────────────
        lay.addWidget(section_header("Reset History"))

        self._history_tbl = QTableWidget(0, 4)
        self._history_tbl.setHorizontalHeaderLabels(["Timestamp", "Type", "Monitor", "Result"])
        self._history_tbl.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._history_tbl.verticalHeader().setVisible(False)
        self._history_tbl.setShowGrid(False)
        self._history_tbl.setAlternatingRowColors(True)
        self._history_tbl.setMaximumHeight(160)
        lay.addWidget(self._history_tbl)

        # ── Event Log ─────────────────────────────────────────────────────
        lay.addWidget(section_header("Event Log"))

        self._log_viewer = QTextEdit()
        self._log_viewer.setObjectName("LogViewer")
        self._log_viewer.setReadOnly(True)
        self._log_viewer.setMaximumHeight(160)
        lay.addWidget(self._log_viewer)

        # ── Buttons ───────────────────────────────────────────────────────
        lay.addSpacing(12)
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        save_btn = QPushButton("Save Settings")
        save_btn.setObjectName("ApplyButton")
        save_btn.clicked.connect(self._save)

        clear_btn = QPushButton("Clear Log")
        clear_btn.clicked.connect(self._clear_log)

        log_file_btn = QPushButton("Open Log File")
        log_file_btn.clicked.connect(self._open_log_file)

        for b in [save_btn, clear_btn, log_file_btn]:
            btn_row.addWidget(b)
        btn_row.addStretch()
        lay.addLayout(btn_row)
        lay.addStretch()

        scroll.setWidget(content)
        root.addWidget(scroll)

    # ── Public refresh ─────────────────────────────────────────────────────

    def refresh(self) -> None:
        self._load_history()
        self._load_log()

    # ── Internals ─────────────────────────────────────────────────────────

    def _load_history(self) -> None:
        history = get_reset_history(limit=50)
        self._history_tbl.setRowCount(0)
        for entry in reversed(history):
            row = self._history_tbl.rowCount()
            self._history_tbl.insertRow(row)
            ts      = entry.get("ts", "")[:19].replace("T", "  ")
            etype   = entry.get("type", "")
            monitor = entry.get("monitor", "—")
            result  = "Success" if etype in ("APPLY", "RESET") else "Rollback"
            for col, val in enumerate([ts, etype, monitor, result]):
                self._history_tbl.setItem(row, col, QTableWidgetItem(val))

    def _load_log(self) -> None:
        events = get_event_log(limit=200)
        lines = []
        for e in events:
            ts  = e.get("ts", "")[:19].replace("T", " ")
            lvl = e.get("type", "INFO")
            msg = e.get("msg", "")
            lines.append(f"{ts}  [{lvl:8s}]  {msg}")
        self._log_viewer.setPlainText("\n".join(lines))
        # Scroll to bottom
        sb = self._log_viewer.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _save(self) -> None:
        settings = load_settings()
        settings["auto_apply_on_startup"]   = self._auto_apply_cb.isChecked()
        settings["notify_on_mismatch"]      = self._notify_cb.isChecked()
        settings["polling_interval_seconds"] = self._poll_combo.currentData()
        settings["reset_debounce_seconds"]   = self._debounce_combo.currentData()
        save_settings(settings)

        from utils.persistence import log_event
        log_event("INFO", "Settings saved by user")
        self.refresh()

    def _clear_log(self) -> None:
        clear_event_log()
        self._load_log()

    def _open_log_file(self) -> None:
        import os, subprocess
        from utils.logger import LOG_FILE
        path = os.path.abspath(LOG_FILE)
        if os.path.exists(path):
            subprocess.Popen(["notepad.exe", path])
