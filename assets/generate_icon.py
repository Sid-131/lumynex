"""
Icon Generator — run once before building with PyInstaller.
Renders the LumynexSymbol widget to a pixmap and saves it as assets/icon.ico.

Usage:
    python assets/generate_icon.py
"""
import os
import sys

# Make sure the project root is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QIcon, QPixmap
from PyQt5.QtCore import Qt

app = QApplication.instance() or QApplication(sys.argv)

from ui.widgets import LumynexSymbol

sizes = [16, 24, 32, 48, 64, 128, 256]
icon = QIcon()

for size in sizes:
    widget = LumynexSymbol(size=size)
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    widget.render(pixmap)
    icon.addPixmap(pixmap)

out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")

# Save all sizes as ICO using the largest pixmap as the main image
largest = QPixmap(256, 256)
largest.fill(Qt.transparent)
LumynexSymbol(size=256).render(largest)
largest.save(out_path, "ICO")

print(f"Icon saved: {out_path}")
