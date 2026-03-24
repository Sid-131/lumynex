"""
Lumynex — Entry Point
"""
import sys
import json
import os

from utils.logger import setup_logger, LOG_FILE
from utils.admin_check import check_admin_or_prompt

log = setup_logger("lumynex.main")


def load_defaults() -> dict:
    path = os.path.join(os.path.dirname(__file__), "config", "defaults.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log.warning(f"Could not load defaults.json: {e}")
        return {}


def main():
    log.info("Lumynex starting...")
    log.info(f"Log file: {LOG_FILE}")

    # ── Qt Application ────────────────────────────────────────────────────────
    try:
        from PyQt5.QtWidgets import QApplication
    except ImportError:
        log.error("PyQt5 is not installed. Run: pip install -r requirements.txt")
        sys.exit(1)

    app = QApplication(sys.argv)
    app.setApplicationName("Lumynex")

    # ── Admin check ───────────────────────────────────────────────────────────
    is_admin = check_admin_or_prompt(app)
    mode = "full" if is_admin else "read-only"
    log.info(f"Running in {mode} mode.")

    # ── Load defaults ─────────────────────────────────────────────────────────
    defaults = load_defaults()
    log.debug(f"Loaded defaults: {defaults}")

    # ── Load stylesheet ───────────────────────────────────────────────────────
    from ui.widgets import load_stylesheet
    app.setStyleSheet(load_stylesheet())

    # ── Launch main window ────────────────────────────────────────────────────
    from ui.main_window import MainWindow
    window = MainWindow(is_admin=is_admin)
    window.setWindowTitle(f"Lumynex  [{mode} mode]")
    window.show()

    log.info("Main window shown. Entering Qt event loop.")
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
