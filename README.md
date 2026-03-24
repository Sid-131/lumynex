# Lumynex

**Lumynex** is a Windows desktop utility that detects your GPU and connected monitors, generates optimal display settings, and lets you apply them or reset your display with one click.

---

## Features

| Feature | Description |
|---|---|
| **Hardware Detection** | GPU (name, VRAM, vendor via WMI + registry fallback), CPU, and all connected monitors |
| **Smart Recommendations** | Per-monitor optimal resolution, refresh rate, and bit depth based on GPU tier and supported modes |
| **One-Click Apply** | Test-first apply with automatic rollback on failure |
| **Soft Reset** | Cycles the discrete GPU adapter (NVIDIA/AMD only — Intel is never touched) to fix flickering, blank screens, or wrong resolution |
| **Hybrid GPU Safe** | Detects Optimus (Intel + NVIDIA) laptops and only cycles the discrete adapter, never the Intel display controller |
| **Real-Time Monitoring** | WM_DISPLAYCHANGE message loop + polling fallback — detects plug/unplug within 1 second |
| **Event Log** | Timestamped log of every apply, reset, and rollback |
| **Read-Only Mode** | Full UI accessible without admin rights; apply/reset require elevation |

---

## Requirements

- Windows 10 / 11 (64-bit)
- Administrator privileges for apply and soft reset
- Python 3.10+ only if running from source

---

## Using the EXE (Recommended)

1. Download `Lumynex.exe` from `dist/`
2. Double-click to run — Windows will prompt for UAC elevation
3. Accept the prompt to get full functionality (apply + reset)

> If you decline UAC, the app opens in **Read-Only** mode — you can view recommendations but not apply them.

---

## Running from Source

```bat
pip install -r requirements.txt
python main.py
```

For apply/reset to work, run as Administrator:

```bat
:: Right-click Command Prompt → "Run as administrator"
python main.py
```

---

## Building the EXE

```bat
build.bat
```

Or manually:

```bat
python assets\generate_icon.py
python -m PyInstaller lumynex.spec --noconfirm
```

Output: `dist\Lumynex.exe`

The exe is a single portable file — no Python required. It embeds a UAC manifest (`requireAdministrator`) so Windows always prompts for elevation on launch.

---

## Screens

### Dashboard
System snapshot showing GPU, CPU, primary display, and a health score. Quick-access Apply button.

### Hardware
Full specs — GPU name, VRAM, vendor, CPU cores/speed, and per-monitor details including all supported modes.

### Recommendations
Side-by-side Current vs Recommended for every connected monitor. Buttons are greyed out with "Already Optimal" when settings are already correct.

### Fix Display
**Soft Reset** — one click cycles the discrete GPU adapter:
- Screen goes blank for ~2 seconds then returns
- Fixes: wrong resolution after sleep/wake, flickering, display not detected after cable plug
- Safe on hybrid GPU laptops — Intel adapter is never disabled

### Settings
Polling interval, auto-apply toggle, event log viewer, and reset history.

---

## Project Structure

```
autodisplay-ai/
├── main.py                   Entry point + admin check
├── build.bat                 One-command build script
├── lumynex.spec              PyInstaller spec
├── lumynex.manifest          UAC requireAdministrator manifest
├── requirements.txt
│
├── core/
│   ├── hardware.py           GPU/CPU/monitor detection (WMI + Win32 + registry)
│   ├── display_config.py     Read / test / apply / rollback display settings
│   ├── recommender.py        Per-monitor recommendation engine
│   ├── reset_engine.py       Soft reset — SetupAPI adapter cycle + reapply fallback
│   └── monitor.py            WM_DISPLAYCHANGE listener + polling fallback
│
├── ui/
│   ├── main_window.py        Main window, background workers, app state
│   ├── dashboard.py          System snapshot + score ring + quick actions
│   ├── hardware_view.py      Detailed GPU / CPU / monitor specs
│   ├── recommendations.py    Current vs Recommended per monitor
│   ├── fix_display.py        Soft reset screen
│   ├── settings_view.py      Preferences + event log + reset history
│   └── widgets.py            Shared widgets, stylesheet loader, Lumynex logo
│
├── utils/
│   ├── admin_check.py        Admin detection + UAC re-launch dialog
│   ├── logger.py             Rotating file + console logger
│   ├── paths.py              Frozen/source path resolution for assets and data
│   └── persistence.py        Thread-safe settings and event log I/O
│
├── assets/
│   ├── styles.qss            PyQt5 stylesheet (dark white + purple/cyan)
│   ├── icon.ico              App icon
│   └── generate_icon.py      Generates icon.ico from LumynexSymbol
│
└── config/
    ├── defaults.json         Default settings (bundled in exe)
    ├── user_settings.json    User overrides (written next to exe at runtime)
    ├── event_log.jsonl       Full event log
    └── reset_history.jsonl   Apply / reset / rollback history
```

---

## How Soft Reset Works

1. Enumerates display adapters via SetupAPI
2. **Skips Intel / Microsoft Basic Display** — only cycles NVIDIA or AMD adapters
3. Disables the discrete adapter → waits 2 seconds → re-enables it
4. Windows automatically restores display settings after re-enable
5. If no discrete adapter is found → falls back to `ChangeDisplaySettingsEx` reapply

This design means Soft Reset is safe on any laptop with Intel + NVIDIA Optimus, as the Intel controller (which drives the physical display outputs) stays running throughout.

---

## Notes

- **Display IDs may change** after an adapter cycle. This is normal Windows behavior — the app handles it automatically.
- **VRAM detection** uses a registry fallback (`HardwareInformation.qwMemorySize`) when WMI reports 0 MB, which happens on some Optimus laptops.
- **User data** (settings, logs) is stored next to the exe when running frozen, or in the project root when running from source.

---

## License

MIT
