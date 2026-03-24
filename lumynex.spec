# -*- mode: python ; coding: utf-8 -*-
#
# Lumynex PyInstaller spec
#
# Build:   pyinstaller lumynex.spec
# Output:  dist/Lumynex.exe   (single-file, UAC requireAdministrator)
#
# Prerequisites:
#   pip install pyinstaller
#   python assets/generate_icon.py   (creates assets/icon.ico)

import sys
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

# Collect all pywin32 / wmi sub-modules (they use dynamic imports)
hidden_imports = (
    collect_submodules("win32com") +
    collect_submodules("win32") +
    ["win32gui", "win32con", "wmi", "pythoncom", "pywintypes"]
)

a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=[],
    datas=[
        ("assets/styles.qss", "assets"),
        ("assets/icon.ico",   "assets"),
        ("config/defaults.json", "config"),
    ],
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "numpy", "scipy"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="Lumynex",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,            # no console window
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets/icon.ico",
    uac_admin=True,           # UAC requireAdministrator
    manifest="lumynex.manifest",
    version=None,
)
