"""
Hardware Info Screen — full read-out of detected hardware. Read-only.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QScrollArea,
)

from ui.widgets import section_header, kv, card

if TYPE_CHECKING:
    from ui.main_window import MainWindow


class HardwareScreen(QWidget):

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

    def refresh(self) -> None:
        mw = self._mw
        if mw.snapshot is None:
            return

        while self._lay.count():
            item = self._lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        snap = mw.snapshot
        cfgs = mw.monitor_configs

        # ── GPU section ───────────────────────────────────────────────────
        self._lay.addWidget(section_header("GPU"))

        gpu_children = []
        for gpu in snap.gpus:
            vram = f"{gpu.vram_mb // 1024} GB" if gpu.vram_mb > 0 else "Shared / unknown"
            rows = [
                kv("Name",   gpu.name),
                kv("Vendor", gpu.vendor),
                kv("VRAM",   vram),
            ]
            for r in rows:
                gpu_children.append(r)
            from ui.widgets import hline
            gpu_children.append(hline())

        if gpu_children and hasattr(gpu_children[-1], 'frameShape'):
            gpu_children.pop()   # remove trailing divider

        self._lay.addWidget(card(gpu_children))

        # ── CPU section ───────────────────────────────────────────────────
        self._lay.addWidget(section_header("CPU"))

        cpu = snap.cpu
        cpu_card = card([
            kv("Name",            cpu.name if cpu else "Unknown"),
            kv("Cores",           str(cpu.cores) if cpu else "?"),
            kv("Logical (threads)", str(cpu.logical_processors) if cpu else "?"),
        ])
        self._lay.addWidget(cpu_card)

        # ── Monitors section ──────────────────────────────────────────────
        self._lay.addWidget(section_header("Monitors"))

        for mon in snap.monitors:
            cfg = cfgs.get(mon.device_name)

            orientation = "Portrait" if cfg and cfg.width < cfg.height else "Landscape"
            primary_str = "Yes" if mon.is_primary else "No"
            res_str     = f"{cfg.width} x {cfg.height}" if cfg else "?"
            hz_str      = f"{cfg.refresh_rate} Hz" if cfg else "?"
            bpp_str     = f"{cfg.bits_per_pixel} bpp" if cfg else "?"
            scale_str   = f"{mon.scale_factor}%" if hasattr(mon, 'scale_factor') else "100%"
            modes_str   = f"{len(mon.supported_modes)} modes" if mon.supported_modes else "?"

            header_lbl = QLabel(f"{mon.device_name}{'  [PRIMARY]' if mon.is_primary else ''}")
            header_lbl.setObjectName("CardTitle")

            mon_card = card([
                header_lbl,
                kv("Resolution",       res_str),
                kv("Refresh rate",     hz_str),
                kv("Bit depth",        bpp_str),
                kv("Orientation",      orientation),
                kv("Scale",            scale_str),
                kv("Primary",          primary_str),
                kv("Supported modes",  modes_str),
            ])
            self._lay.addWidget(mon_card)

        # ── Refresh button ────────────────────────────────────────────────
        self._lay.addSpacing(8)
        row = QHBoxLayout()
        btn = QPushButton("Refresh Hardware Data")
        btn.clicked.connect(self._mw.refresh_data)
        row.addWidget(btn)
        row.addStretch()
        self._lay.addLayout(row)
        self._lay.addStretch()
