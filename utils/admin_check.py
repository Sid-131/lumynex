import ctypes
import sys
import os
from utils.logger import log


def is_admin() -> bool:
    """Return True if the current process has Administrator privileges."""
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def relaunch_as_admin() -> None:
    """Re-launch the current process with UAC elevation and exit this instance."""
    log.info("Requesting UAC elevation — re-launching as Administrator.")
    script = os.path.abspath(sys.argv[0])
    params = " ".join(sys.argv[1:])
    # ShellExecuteW with 'runas' triggers UAC prompt
    ret = ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, f'"{script}" {params}', None, 1)
    if ret <= 32:
        log.error(f"UAC re-launch failed (ShellExecute returned {ret}).")
    sys.exit(0)


def check_admin_or_prompt(app=None) -> bool:
    """
    Check admin status. If not admin:
      - With a Qt app available: show a dialog offering to re-launch or continue read-only.
      - Without Qt: log a warning and return False (read-only mode).

    Returns True if running as admin, False for read-only mode.
    """
    if is_admin():
        log.info("Running with Administrator privileges.")
        return True

    log.warning("Not running as Administrator. Some features will be unavailable.")

    if app is not None:
        try:
            from PyQt5.QtWidgets import QMessageBox, QPushButton
            msg = QMessageBox()
            msg.setWindowTitle("Lumynex — Privileges Required")
            msg.setText(
                "Administrator privileges are required to change display settings "
                "and perform soft resets.\n\nWhat would you like to do?"
            )
            msg.setIcon(QMessageBox.Warning)
            restart_btn = msg.addButton("Restart as Administrator", QMessageBox.AcceptRole)
            readonly_btn = msg.addButton("Continue (Read-Only)", QMessageBox.RejectRole)  # noqa: F841
            msg.exec_()

            if msg.clickedButton() == restart_btn:
                relaunch_as_admin()
        except ImportError:
            log.warning("PyQt5 not available — skipping UAC dialog, falling back to read-only mode.")

    return False  # read-only mode
