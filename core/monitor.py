"""
Phase 7 — Event Listener (Real-Time Display Monitor)

Primary  : WM_DISPLAYCHANGE message loop via win32gui (hidden window)
Fallback : 5-second polling loop (compares monitor config hashes)
Debounce : 500 ms — rapid events collapsed into one dispatch
Cooldown : 5 s after any soft reset — prevents feedback loops

Usage
-----
    mon = DisplayMonitorThread(on_change=my_callback)
    mon.start()
    ...
    mon.notify_reset_done()   # call after every soft reset
    mon.stop()
"""

from __future__ import annotations

import hashlib
import threading
import time
from typing import Callable, Optional

from PyQt5.QtCore import QThread, pyqtSignal

from core.display_config import get_all_monitors, get_current_config
from utils.logger import setup_logger
from utils.persistence import log_event

log = setup_logger("lumynex.monitor")

# Timing constants
POLL_INTERVAL_S  = 5.0     # polling fallback interval
DEBOUNCE_S       = 0.5     # collapse rapid events
COOLDOWN_S       = 5.0     # silence after a soft reset


# ── Config hash helper ─────────────────────────────────────────────────────

def _config_hash() -> str:
    """Return a short hash of all monitors' current resolution/refresh."""
    parts = []
    try:
        for mon_id in get_all_monitors():
            cfg = get_current_config(mon_id)
            if cfg:
                parts.append(f"{mon_id}:{cfg.width}x{cfg.height}@{cfg.refresh_rate}")
    except Exception as exc:
        log.debug("config_hash error: %s", exc)
    return hashlib.md5("|".join(sorted(parts)).encode()).hexdigest()[:12]


# ── WM_DISPLAYCHANGE message window ───────────────────────────────────────

def _run_win32_message_loop(fire_cb: Callable, stop_flag: threading.Event) -> None:
    """
    Creates a hidden window and pumps Windows messages.
    Calls fire_cb() each time WM_DISPLAYCHANGE arrives.
    Exits when stop_flag is set.
    """
    try:
        import win32con
        import win32gui
    except ImportError:
        log.warning("pywin32 not available — win32 message loop unavailable")
        return

    WM_DISPLAYCHANGE = 0x007E
    CLASS_NAME = "LumynexMonitorWindow"

    def wndproc(hwnd, msg, wparam, lparam):
        if msg == WM_DISPLAYCHANGE:
            log.debug("WM_DISPLAYCHANGE received (depth=%d, w=%d, h=%d)",
                      wparam, lparam & 0xFFFF, (lparam >> 16) & 0xFFFF)
            fire_cb()
        elif msg == win32con.WM_DESTROY:
            win32gui.PostQuitMessage(0)
        return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)

    try:
        wc = win32gui.WNDCLASS()
        wc.lpszClassName = CLASS_NAME
        wc.lpfnWndProc   = wndproc
        atom = win32gui.RegisterClass(wc)
        hwnd = win32gui.CreateWindow(
            atom, CLASS_NAME, 0,
            0, 0, 0, 0,        # position + size — invisible
            0, 0, wc.hInstance, None
        )
        log.info("WM_DISPLAYCHANGE message loop started (hwnd=%s)", hwnd)

        # Pump messages until stop_flag is set
        while not stop_flag.is_set():
            if win32gui.PumpWaitingMessages():
                break
            time.sleep(0.05)

        win32gui.DestroyWindow(hwnd)
        win32gui.UnregisterClass(CLASS_NAME, wc.hInstance)
    except Exception as exc:
        log.warning("win32 message loop error: %s", exc)


# ── Main monitor thread ────────────────────────────────────────────────────

class DisplayMonitorThread(QThread):
    """
    Background thread that detects display changes and emits `changed`.
    Runs both the win32 message listener and the polling fallback.
    """

    changed = pyqtSignal()   # emitted on the Qt event loop — safe to connect to UI slots

    def __init__(
        self,
        poll_interval_s: float = POLL_INTERVAL_S,
        debounce_s: float      = DEBOUNCE_S,
        cooldown_s: float      = COOLDOWN_S,
        parent=None,
    ):
        super().__init__(parent)
        self._poll_interval = poll_interval_s
        self._debounce      = debounce_s
        self._cooldown      = cooldown_s

        self._stop_flag     = threading.Event()
        self._last_reset    = 0.0        # monotonic timestamp of last reset
        self._last_event    = 0.0        # for debounce
        self._debounce_timer: Optional[threading.Timer] = None
        self._lock          = threading.Lock()

        self._win32_thread: Optional[threading.Thread] = None

    # ── Public API ─────────────────────────────────────────────────────────

    def notify_reset_done(self) -> None:
        """Call this after every soft reset to arm the cooldown."""
        with self._lock:
            self._last_reset = time.monotonic()
        log.debug("Cooldown armed for %.1f s", self._cooldown)

    def stop(self) -> None:
        """Signal the thread to stop, then wait."""
        self._stop_flag.set()
        if self._debounce_timer:
            self._debounce_timer.cancel()
        self.quit()
        self.wait(3000)

    # ── Thread body ────────────────────────────────────────────────────────

    def run(self) -> None:
        log.info("DisplayMonitorThread starting")

        # Start win32 message loop in a daemon thread
        self._win32_thread = threading.Thread(
            target=_run_win32_message_loop,
            args=(self._fire_change, self._stop_flag),
            daemon=True,
            name="lumynex-win32-msgs",
        )
        self._win32_thread.start()

        # Polling fallback loop (also catches driver-level changes that skip WM_DISPLAYCHANGE)
        self._polling_loop()

        log.info("DisplayMonitorThread stopped")

    def _polling_loop(self) -> None:
        last_hash = _config_hash()
        log.debug("Polling baseline hash: %s", last_hash)

        while not self._stop_flag.is_set():
            time.sleep(self._poll_interval)
            if self._stop_flag.is_set():
                break
            try:
                current = _config_hash()
                if current != last_hash:
                    log.info("Polling detected config change: %s -> %s", last_hash, current)
                    last_hash = current
                    self._fire_change()
                else:
                    last_hash = current   # keep fresh
            except Exception as exc:
                log.debug("Polling hash error: %s", exc)

    # ── Debounce + cooldown ────────────────────────────────────────────────

    def _fire_change(self) -> None:
        """Called from either the win32 thread or the polling loop."""
        with self._lock:
            now = time.monotonic()
            since_reset = now - self._last_reset
            if since_reset < self._cooldown:
                log.debug(
                    "Display change suppressed (cooldown %.1f/%.1f s)",
                    since_reset, self._cooldown
                )
                return

            self._last_event = now
            if self._debounce_timer and self._debounce_timer.is_alive():
                self._debounce_timer.cancel()

            self._debounce_timer = threading.Timer(self._debounce, self._dispatch)
            self._debounce_timer.daemon = True
            self._debounce_timer.start()

    def _dispatch(self) -> None:
        """Runs after debounce delay; emits the Qt signal."""
        log.info("Display change event dispatched")
        log_event("INFO", "Display change detected by monitor thread")
        self.changed.emit()   # Qt signal — crosses to main thread safely


# ── Convenience factory ────────────────────────────────────────────────────

def make_monitor(
    on_change: Optional[Callable] = None,
    poll_interval_s: float = POLL_INTERVAL_S,
    debounce_s: float      = DEBOUNCE_S,
    cooldown_s: float      = COOLDOWN_S,
    parent=None,
) -> DisplayMonitorThread:
    """
    Create and wire a DisplayMonitorThread.
    If *on_change* is a plain callable, it is connected to the `changed` signal.
    """
    mon = DisplayMonitorThread(poll_interval_s, debounce_s, cooldown_s, parent)
    if on_change is not None:
        mon.changed.connect(on_change)
    return mon
