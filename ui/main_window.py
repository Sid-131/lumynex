"""
Main Window — sidebar nav + stacked content area + background workers.
Owns all application state: hardware snapshot, recommendations, monitor configs.
All core operations (apply, reset, refresh) run on QThread workers so the UI
never freezes. Screens are notified via signals.
"""
from __future__ import annotations

import os
from typing import Dict, List, Optional

from PyQt5.QtCore import Qt, QThread, pyqtSignal, QObject
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QLabel, QPushButton, QStackedWidget, QLineEdit,
    QApplication, QMessageBox,
)

from ui.widgets import (
    LumynexSymbol, SidebarNavButton, SidebarFloatingLabel,
    hline, load_stylesheet, shadow,
)
from utils.logger import setup_logger
from utils.persistence import log_event, load_settings

log = setup_logger("lumynex.main_window")


# ── Background workers ─────────────────────────────────────────────────────

class _HardwareWorker(QThread):
    done = pyqtSignal(object, object)   # (HardwareSnapshot, dict[mon_id -> DisplaySettings])
    error = pyqtSignal(str)

    def run(self):
        # WMI requires COM to be initialised on each thread (critical in frozen exe)
        try:
            import pythoncom
            pythoncom.CoInitialize()
        except Exception:
            pass
        try:
            from core.hardware import get_hardware_snapshot
            from core.display_config import get_all_monitors, get_current_config
            snap = get_hardware_snapshot()
            cfgs = {}
            for mon_id in get_all_monitors():
                cfg = get_current_config(mon_id)
                if cfg:
                    cfgs[mon_id] = cfg
            self.done.emit(snap, cfgs)
        except Exception as exc:
            log.error("Hardware worker error: %s", exc)
            self.error.emit(str(exc))
        finally:
            try:
                import pythoncom
                pythoncom.CoUninitialize()
            except Exception:
                pass


class _RecommendWorker(QThread):
    done = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, snapshot, cfgs):
        super().__init__()
        self._snap = snapshot
        self._cfgs = cfgs

    def run(self):
        try:
            from core.recommender import recommend, MonitorInfo, GpuInfo
            gpus = [GpuInfo(name=g.name, vram_mb=g.vram_mb, vendor=g.vendor)
                    for g in self._snap.gpus]
            monitors = []
            for mon in self._snap.monitors:
                cfg = self._cfgs.get(mon.device_name)
                if not cfg:
                    continue
                modes = [(m.width, m.height, m.refresh_rate) for m in (mon.supported_modes or [])]
                monitors.append(MonitorInfo(
                    monitor_id      = mon.device_name,
                    current_width   = cfg.width,
                    current_height  = cfg.height,
                    current_refresh = cfg.refresh_rate,
                    current_scale   = getattr(mon, 'scale_factor', 100),
                    bit_depth       = cfg.bits_per_pixel,
                    is_primary      = mon.is_primary,
                    supported_modes = modes,
                ))
            recs = recommend(monitors, gpus)
            self.done.emit(recs)
        except Exception as exc:
            log.error("Recommend worker error: %s", exc)
            self.error.emit(str(exc))


class _ApplyWorker(QThread):
    progress = pyqtSignal(str)
    done     = pyqtSignal(bool, str)   # success, message

    def __init__(self, recs, cfgs):
        super().__init__()
        self._recs = recs
        self._cfgs = cfgs

    def run(self):
        from core.display_config import apply_config, rollback, DisplaySettings

        snapshots = {mon_id: cfg for mon_id, cfg in self._cfgs.items()}
        all_ok = True

        for rec in self._recs:
            cfg = self._cfgs.get(rec.monitor_id)
            if not cfg:
                continue
            target = DisplaySettings(
                device_name    = rec.monitor_id,
                width          = rec.recommended_width,
                height         = rec.recommended_height,
                refresh_rate   = rec.recommended_refresh,
                bits_per_pixel = rec.bit_depth,
                position_x     = cfg.position_x,
                position_y     = cfg.position_y,
            )
            self.progress.emit(f"Applying {rec.monitor_id}...")
            result = apply_config(target)
            if result.success:
                self.progress.emit(f"  {rec.monitor_id} OK")
                log_event("APPLY", f"Applied {rec.recommended_width}x{rec.recommended_height}"
                          f"@{rec.recommended_refresh}Hz", monitor_id=rec.monitor_id)
            else:
                self.progress.emit(f"  {rec.monitor_id} FAILED: {result.message}")
                log.warning("Apply failed on %s: %s — rolling back", rec.monitor_id, result.message)
                if rec.monitor_id in snapshots:
                    rollback(snapshots[rec.monitor_id])
                    log_event("ROLLBACK", f"Rolled back {rec.monitor_id}: {result.message}",
                              monitor_id=rec.monitor_id)
                all_ok = False

        msg = "All settings applied." if all_ok else "Some settings failed — rolled back."
        self.done.emit(all_ok, msg)


class _ResetWorker(QThread):
    progress = pyqtSignal(str)
    done     = pyqtSignal(object)   # ResetResult

    def __init__(self, target_settings=None):
        super().__init__()
        self._target_settings = target_settings  # Dict[str, DisplaySettings] or None

    def run(self):
        # WMI (_has_hybrid_gpus) requires COM to be initialised on each thread
        try:
            import pythoncom
            pythoncom.CoInitialize()
        except Exception:
            pass
        try:
            from core.reset_engine import soft_reset
            result = soft_reset(
                target_settings=self._target_settings,
                progress_cb=self.progress.emit,
            )
            self.done.emit(result)
        except Exception as exc:
            log.error("ResetWorker unhandled exception: %s", exc)
            from core.reset_engine import ResetResult
            self.done.emit(ResetResult(success=False, method="None", error=str(exc)))
        finally:
            try:
                import pythoncom
                pythoncom.CoUninitialize()
            except Exception:
                pass


# ── Main Window ────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):

    # ── Application state ──────────────────────────────────────────────────
    snapshot          = None   # HardwareSnapshot
    recommendations   = []     # List[Recommendation]
    monitor_configs   = {}     # Dict[str, DisplaySettings]

    def __init__(self, is_admin: bool = False):
        super().__init__()
        self.is_admin = is_admin
        self.setWindowTitle("Lumynex")
        self.resize(1060, 730)
        self.setMinimumSize(860, 560)

        # Worker refs (kept to avoid GC)
        self._hw_worker:    Optional[_HardwareWorker]   = None
        self._rec_worker:   Optional[_RecommendWorker]  = None
        self._apply_worker: Optional[_ApplyWorker]      = None
        self._reset_worker: Optional[_ResetWorker]      = None

        self._build_ui()
        self._apply_admin_mode()
        self._start_monitor()

        # Load data on startup
        self.refresh_data()

    # ── UI build ───────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QWidget()
        root_lay = QHBoxLayout(root)
        root_lay.setContentsMargins(0, 0, 0, 0)
        root_lay.setSpacing(0)

        # Sidebar
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

        floating_label = SidebarFloatingLabel(None)

        nav_defs = [
            ("◈", "Dashboard"),
            ("⬡", "Hardware"),
            ("✦", "Recommendations"),
            ("↺", "Fix Display"),
            ("⚙", "Settings"),
        ]
        self._nav_btns: List[SidebarNavButton] = []
        for i, (icon, name) in enumerate(nav_defs):
            btn = SidebarNavButton(icon, name, active=(i == 0))
            btn.set_floating_label(floating_label)
            btn.clicked.connect(lambda _, idx=i: self.navigate_to(idx))
            wrapper = QWidget()
            wrapper.setStyleSheet("background:transparent;")
            wl = QHBoxLayout(wrapper)
            wl.setContentsMargins(0, 0, 0, 0)
            wl.addWidget(btn, alignment=Qt.AlignCenter)
            sb.addWidget(wrapper)
            self._nav_btns.append(btn)

        sb.addStretch()
        root_lay.addWidget(sidebar)

        # Right panel
        right = QWidget()
        right.setObjectName("ContentArea")
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(0, 0, 0, 0)
        right_lay.setSpacing(0)

        # Top bar
        topbar = QWidget()
        topbar.setObjectName("TopBar")
        topbar.setFixedHeight(52)
        tb = QHBoxLayout(topbar)
        tb.setContentsMargins(24, 0, 16, 0)
        tb.setSpacing(12)

        app_name = QLabel("Lumynex")
        app_name.setObjectName("AppTitle")
        tb.addWidget(app_name)
        tb.addStretch()

        search = QLineEdit()
        search.setObjectName("SearchBox")
        search.setPlaceholderText("Search settings...")
        search.setFixedWidth(210)
        tb.addWidget(search)

        # Read-only mode badge shown next to status when not admin
        if not self.is_admin:
            readonly_lbl = QLabel("Read-Only")
            readonly_lbl.setObjectName("StatusBadge")
            readonly_lbl.setProperty("state", "warning")
            readonly_lbl.style().unpolish(readonly_lbl)
            readonly_lbl.style().polish(readonly_lbl)
            readonly_lbl.setToolTip("Running without Administrator privileges.\n"
                                    "Restart as Administrator to apply settings.")
            tb.addWidget(readonly_lbl)

        self._status_badge = QLabel("● Loading")
        self._status_badge.setObjectName("StatusBadge")
        self._status_badge.setProperty("state", "applying")
        self._status_badge.style().unpolish(self._status_badge)
        self._status_badge.style().polish(self._status_badge)
        tb.addWidget(self._status_badge)

        right_lay.addWidget(topbar)
        right_lay.addWidget(hline())

        # Screen switcher
        self._stack = QStackedWidget()
        right_lay.addWidget(self._stack)

        # Import screens lazily to avoid circular imports at build time
        from ui.dashboard       import DashboardScreen
        from ui.hardware_view   import HardwareScreen
        from ui.recommendations import RecommendationsScreen
        from ui.fix_display     import FixDisplayScreen
        from ui.settings_view   import SettingsScreen

        self._screens = [
            DashboardScreen(self),
            HardwareScreen(self),
            RecommendationsScreen(self),
            FixDisplayScreen(self),
            SettingsScreen(self),
        ]
        for s in self._screens:
            self._stack.addWidget(s)

        root_lay.addWidget(right)
        self.setCentralWidget(root)

    # ── Navigation ─────────────────────────────────────────────────────────

    def navigate_to(self, idx: int) -> None:
        for i, btn in enumerate(self._nav_btns):
            btn.set_active(i == idx)
        self._stack.setCurrentIndex(idx)
        screen = self._screens[idx]
        if hasattr(screen, "refresh"):
            screen.refresh()

    # ── Status badge ───────────────────────────────────────────────────────

    def _set_badge(self, text: str, state: str) -> None:
        self._status_badge.setText(text)
        self._status_badge.setProperty("state", state)
        self._status_badge.style().unpolish(self._status_badge)
        self._status_badge.style().polish(self._status_badge)

    # ── Admin mode enforcement ─────────────────────────────────────────────

    def _apply_admin_mode(self) -> None:
        """Propagate admin/read-only state to all screens after they are built."""
        # Disable apply buttons on all capable screens when not admin
        self.set_apply_enabled(True)   # guard in set_apply_enabled checks is_admin

        # Tell FixDisplayScreen about admin state
        from ui.fix_display import FixDisplayScreen
        for s in self._screens:
            if isinstance(s, FixDisplayScreen):
                s.set_admin_mode(self.is_admin)

    def set_apply_enabled(self, enabled: bool) -> None:
        """
        Enable or disable all apply/action buttons across screens.
        Non-admin users always get False regardless of the enabled argument.
        """
        effective = enabled and self.is_admin
        for s in self._screens:
            if hasattr(s, "set_apply_enabled"):
                s.set_apply_enabled(effective)

    # ── Busy guard ─────────────────────────────────────────────────────────

    def _is_busy(self) -> bool:
        return (
            (self._apply_worker is not None and self._apply_worker.isRunning()) or
            (self._reset_worker is not None and self._reset_worker.isRunning())
        )

    # ── Display monitor ────────────────────────────────────────────────────

    def _start_monitor(self) -> None:
        from core.monitor import DisplayMonitorThread
        settings = load_settings()
        poll_s = float(settings.get("polling_interval_seconds", 5))
        self._display_monitor = DisplayMonitorThread(poll_interval_s=poll_s, parent=self)
        self._display_monitor.changed.connect(self._on_display_changed)
        self._display_monitor.start()

    def _on_display_changed(self) -> None:
        log.info("Display change detected — refreshing data")
        log_event("INFO", "Display change detected; refreshing hardware data")
        self._set_badge("Refreshing...", "applying")
        self.refresh_data()

    # ── Data refresh ───────────────────────────────────────────────────────

    def refresh_data(self) -> None:
        """Load hardware snapshot + recommendations in background."""
        self._set_badge("Loading...", "applying")
        self._hw_worker = _HardwareWorker()
        self._hw_worker.done.connect(self._on_hardware_loaded)
        self._hw_worker.error.connect(self._on_hw_error)
        self._hw_worker.start()

    def _on_hardware_loaded(self, snap, cfgs: dict) -> None:
        self.snapshot       = snap
        self.monitor_configs = cfgs
        log.info("Hardware loaded: %d GPU(s), %d monitor(s)", len(snap.gpus), len(snap.monitors))

        self._rec_worker = _RecommendWorker(snap, cfgs)
        self._rec_worker.done.connect(self._on_recs_loaded)
        self._rec_worker.error.connect(self._on_hw_error)
        self._rec_worker.start()

    def _on_recs_loaded(self, recs: list) -> None:
        self.recommendations = recs

        # Determine badge state
        all_match = all(
            self.monitor_configs.get(r.monitor_id) and
            r.recommended_width   == self.monitor_configs[r.monitor_id].width and
            r.recommended_height  == self.monitor_configs[r.monitor_id].height and
            r.recommended_refresh == self.monitor_configs[r.monitor_id].refresh_rate
            for r in recs
        )
        if all_match:
            self._set_badge("● Normal", "normal")
        else:
            self._set_badge("! Mismatch", "warning")

        # Refresh current screen
        current = self._stack.currentWidget()
        if hasattr(current, "refresh"):
            current.refresh()

        # Auto-apply if configured (admin only)
        if self.is_admin:
            settings = load_settings()
            if settings.get("auto_apply_on_startup") and not all_match:
                log.info("Auto-apply on startup triggered")
                self.on_apply_all()

    def _on_hw_error(self, msg: str) -> None:
        self._set_badge("! Error", "error")
        log.error("Hardware/recommend error: %s", msg)

    # ── Apply ──────────────────────────────────────────────────────────────

    def on_apply_all(self) -> None:
        if not self.is_admin:
            self._show_admin_required("apply display settings")
            return
        if not self.recommendations or not self.monitor_configs:
            return
        self._start_apply(self.recommendations)

    def on_apply_single(self, rec) -> None:
        if not self.is_admin:
            self._show_admin_required("apply display settings")
            return
        self._start_apply([rec])

    def _start_apply(self, recs: list) -> None:
        if self._is_busy():
            log.warning("Apply requested while operation is in progress — ignoring")
            return
        self._set_badge("Applying...", "applying")
        self.set_apply_enabled(False)
        self._apply_worker = _ApplyWorker(recs, self.monitor_configs)
        self._apply_worker.progress.connect(self._on_apply_progress)
        self._apply_worker.done.connect(self._on_apply_done)
        self._apply_worker.start()

    def _on_apply_progress(self, msg: str) -> None:
        log.debug("[apply] %s", msg)

    def _on_apply_done(self, success: bool, message: str) -> None:
        self._apply_worker = None   # clear ref so _is_busy() doesn't see stale thread
        self.set_apply_enabled(True)   # guard checks is_admin
        if success:
            self._set_badge("● Normal", "normal")
        else:
            self._set_badge("! Error", "error")
            self._show_apply_error(message)
        log.info("Apply done: success=%s — %s", success, message)
        # Re-read display config to update state
        self.refresh_data()

    def _show_apply_error(self, message: str) -> None:
        """Show an error dialog; include GPU override hint for NVIDIA/AMD users."""
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Settings Not Applied")

        if "Restart" in message:
            msg_box.setIcon(QMessageBox.Information)
            msg_box.setText("A system restart is required for the display changes to take effect.")
        else:
            text = f"Could not apply settings: {message}"
            # GPU control panel override hint
            if self.snapshot and self.snapshot.gpus:
                vendor = self.snapshot.gpus[0].vendor.upper()
                if vendor == "NVIDIA":
                    text += ("\n\nTip: If settings keep reverting, open NVIDIA Control Panel → "
                             "Display → Change Resolution and ensure it is not overriding system settings.")
                elif vendor == "AMD":
                    text += ("\n\nTip: If settings keep reverting, open AMD Software (Adrenalin) → "
                             "Display and ensure custom resolution overrides are not active.")
            msg_box.setIcon(QMessageBox.Warning)
            msg_box.setText(text)

        msg_box.exec_()

    # ── Soft Reset ─────────────────────────────────────────────────────────

    def on_soft_reset(self) -> None:
        if not self.is_admin:
            self._show_admin_required("perform a soft reset")
            return

        from ui.fix_display import FixDisplayScreen
        fix_screen = next((s for s in self._screens if isinstance(s, FixDisplayScreen)), None)

        if self._is_busy():
            log.warning("Reset requested while operation is in progress — ignoring")
            if fix_screen:
                fix_screen.set_status("Another operation is in progress — please wait…", "running")
            return

        if fix_screen:
            fix_screen.set_running(True)
            fix_screen.set_status("Starting soft reset…", "running")

        # Build target settings from recommendations so soft reset restores the
        # correct resolution/refresh, not whatever Windows currently has (which
        # may already be wrong).  Falls back to current settings if no data yet.
        target_settings = None
        if self.recommendations and self.monitor_configs:
            from core.display_config import DisplaySettings
            target_settings = {}
            for rec in self.recommendations:
                cfg = self.monitor_configs.get(rec.monitor_id)
                if cfg:
                    target_settings[rec.monitor_id] = DisplaySettings(
                        device_name    = rec.monitor_id,
                        width          = rec.recommended_width,
                        height         = rec.recommended_height,
                        refresh_rate   = rec.recommended_refresh,
                        bits_per_pixel = rec.bit_depth,
                        position_x     = cfg.position_x,
                        position_y     = cfg.position_y,
                    )

        # Arm cooldown BEFORE the worker starts so WM_DISPLAYCHANGE events fired
        # by ChangeDisplaySettingsEx during the reset are suppressed immediately.
        if hasattr(self, "_display_monitor"):
            self._display_monitor.notify_reset_done()

        self._set_badge("Resetting...", "applying")
        self.set_apply_enabled(False)
        self._reset_worker = _ResetWorker(target_settings=target_settings)
        self._reset_worker.progress.connect(self._on_reset_progress)
        self._reset_worker.done.connect(self._on_reset_done)
        self._reset_worker.start()

    def _on_reset_progress(self, msg: str) -> None:
        from ui.fix_display import FixDisplayScreen
        fix_screen = next((s for s in self._screens if isinstance(s, FixDisplayScreen)), None)
        if fix_screen:
            fix_screen.set_status(msg, "running")

    def _on_reset_done(self, result) -> None:
        from ui.fix_display import FixDisplayScreen
        fix_screen = next((s for s in self._screens if isinstance(s, FixDisplayScreen)), None)

        self._reset_worker = None   # clear ref so _is_busy() never sees stale thread
        self.set_apply_enabled(True)   # guard checks is_admin

        if result.success:
            self._set_badge("● Normal", "normal")
            if fix_screen:
                fix_screen.set_status(
                    f"Soft reset completed successfully (method: {result.method}, "
                    f"{result.duration_ms} ms).", "success"
                )
                fix_screen.set_last_reset(_now_str(), result.method)
        else:
            self._set_badge("! Error", "error")
            if fix_screen:
                fix_screen.set_status(
                    f"Reset failed: {result.error}. "
                    f"Rollback: {'ok' if result.rollback_ok else 'FAILED'}.", "error"
                )

        if fix_screen:
            fix_screen.set_running(False)

        self.refresh_data()

    # ── Admin required dialog ──────────────────────────────────────────────

    def _show_admin_required(self, action: str) -> None:
        msg = QMessageBox(self)
        msg.setWindowTitle("Administrator Required")
        msg.setIcon(QMessageBox.Warning)
        msg.setText(
            f"You need Administrator privileges to {action}.\n\n"
            "Please restart Lumynex as Administrator."
        )
        msg.exec_()

    # ── Cleanup ────────────────────────────────────────────────────────────

    def closeEvent(self, event) -> None:
        if hasattr(self, "_display_monitor"):
            self._display_monitor.stop()
        super().closeEvent(event)


def _now_str() -> str:
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
