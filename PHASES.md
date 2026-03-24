# AutoDisplay AI – Development Phases

---

## Phase 1 — Project Scaffold & Admin Foundation
**Goal:** Runnable shell with correct folder structure and admin handling in place.

**Tasks:**
- Create folder structure (`core/`, `ui/`, `utils/`, `config/`, `assets/`)
- `main.py` — app entry point with PyQt app init
- `utils/admin_check.py` — detect admin; offer UAC re-launch or read-only mode
- `utils/logger.py` — configure Python logging (file + console)
- `requirements.txt` — pin `pywin32`, `PyQt5` or `PySide6`
- `config/defaults.json` — placeholder default settings

**Exit Criteria:** App launches, correctly detects admin state, offers re-launch, logs to file.

---

## Phase 2 — Hardware Detection
**Goal:** Reliably enumerate GPU, CPU, and all connected monitors.

**Tasks:**
- `core/hardware.py`
  - WMI query for GPU (name, VRAM, vendor) and CPU (name, cores)
  - `EnumDisplayDevices` + `EnumDisplaySettings` for monitors (resolution, refresh rate, HDR, DPI, primary flag)
- Unit-testable output: return plain dicts/dataclasses

**Exit Criteria:** Running `hardware.py` directly prints accurate GPU, CPU, and per-monitor specs on the dev machine.

---

## Phase 3 — Display Config Manager
**Goal:** Safe read / validate / apply / rollback cycle for display settings.

**Tasks:**
- `core/display_config.py`
  - `get_current_config(monitor_id)` — snapshot current settings
  - `test_config(monitor_id, settings)` — `CDS_TEST` validation
  - `apply_config(monitor_id, settings)` — `ChangeDisplaySettingsEx`
  - `rollback(monitor_id, snapshot)` — restore on failure
  - `get_all_monitors()` — enumerate connected monitors
  - `set_primary(monitor_id)`

**Exit Criteria:** Can change resolution on a test monitor and roll back cleanly without a display outage.

---

## Phase 4 — Recommendation Engine
**Goal:** Produce per-monitor recommended settings from hardware data.

**Tasks:**
- `core/recommender.py`
  - GPU tier classification (low / mid / high by VRAM + vendor)
  - Per-monitor rule logic (resolution, refresh rate, scaling caps)
  - Battery/power state detection → cap refresh rate at 60 Hz on battery
  - Multi-monitor conflict detection (clone mode mismatch)
  - Return structured recommendations dict

**Exit Criteria:** Given mock hardware data, engine returns correct recommendations for low-end, high-end, and multi-monitor scenarios.

---

## Phase 5 — Persistence Layer
**Goal:** User preferences and event log survive restarts.

**Tasks:**
- `utils/persistence.py`
  - `load_settings()` / `save_settings(data)` — read/write `config/user_settings.json`
  - `log_event(type, detail)` — append timestamped entries
- Monitor identity: key settings by EDID / monitor ID so prefs survive reconnects

**Exit Criteria:** Settings saved on one run are loaded correctly on the next; event log grows correctly.

---

## Phase 6 — Soft Reset Engine
**Goal:** Disable/enable display adapter programmatically to fix display issues.

**Tasks:**
- `core/reset_engine.py`
  - Method 1 (primary): `SetupDiSetClassInstallParams` + `SetupDiCallClassInstaller` via `ctypes`
  - Method 2 (fallback): reapply current config via `ChangeDisplaySettingsEx`
  - Full execution flow: snapshot → disable → wait 2 s → enable → wait 1 s → reapply → validate → rollback on failure

**Exit Criteria:** One-click soft reset cycles the display adapter and restores settings without a system reboot; fallback works if SetupAPI fails.

---

## Phase 7 — Event Listener (Real-Time Monitoring)
**Goal:** Detect display changes and trigger corrective action automatically.

**Tasks:**
- `core/monitor.py`
  - Primary: `WM_DISPLAYCHANGE` message loop via `win32gui`
  - Fallback: 5-second polling loop
  - Debounce: 5-second cooldown after a reset; 500 ms debounce on events
  - On mismatch: evaluate → trigger soft reset → reapply → log

**Exit Criteria:** Plugging/unplugging a monitor triggers detection within 1 second; rapid events do not cause an infinite reset loop.

---

## Phase 8 — UI Layer
**Goal:** Full desktop GUI wiring all core modules together.

**Screens (in build order):**

1. **Dashboard** (`ui/dashboard.py`) — system summary, current vs. recommended, status badge
2. **Hardware Info** (`ui/hardware_view.py`) — GPU, CPU, monitor specs
3. **Recommendations** (`ui/recommendations.py`) — per-monitor suggestions + Apply button
4. **Fix Display** (`ui/fix_display.py`) — one-click soft reset + status feedback
5. **Settings** (`ui/settings_view.py`) — auto-apply toggle, reset history, log viewer

**UI States:** Normal / Warning / Applying (spinner, buttons disabled) / Error (rollback shown)

**Exit Criteria:** All screens render correctly; Apply triggers the Phase 3 flow; Fix Display triggers the Phase 6 flow; settings persist via Phase 5.

---

## Phase 9 — Integration & Edge Case Hardening
**Goal:** Wire everything together; handle the documented edge cases.

**Tasks:**
- Full end-to-end flow from `main.py` (admin → load prefs → detect → recommend → show dashboard → event loop)
- Edge case coverage:
  - Unsupported resolution rejected before apply
  - Mid-apply failure → rollback
  - Soft reset debounce prevents feedback loop
  - Clone mode conflict flagged in UI
  - NVIDIA/AMD control panel override detection + user warning
  - Laptop lid close/open treated as unplug/replug
  - No-admin read-only mode works fully

**Exit Criteria:** All edge cases from `ARCHITECTURE.md` handled; no uncaught exceptions in normal use.

---

## Phase 10 — Polish & Release Prep
**Goal:** Shippable MVP.

**Tasks:**
- `assets/styles.qss` — consistent PyQt stylesheet
- `assets/icon.ico` — app icon; taskbar tray icon
- PyInstaller build → single `.exe` with UAC manifest (`requireAdministrator`)
- Installer or portable zip
- Basic smoke test checklist (single monitor, dual monitor, no-admin mode)
- Update `README.md` with install and usage instructions

**Exit Criteria:** `.exe` runs on a clean Windows 11 machine without Python installed; all MVP features work.

---

## Scope Deferred (Post-MVP)

| Feature | Why Deferred |
|---|---|
| ML/AI optimization | Needs usage data first |
| Cloud sync | Requires backend infra |
| Game Mode / Battery Saver profiles | Nice-to-have UX |
| Advanced scaling control | Complex API surface |

---

## Phase Summary

| Phase | Deliverable | Depends On |
|---|---|---|
| 1 | Scaffold + admin | — |
| 2 | Hardware detection | 1 |
| 3 | Display config manager | 1 |
| 4 | Recommendation engine | 2, 3 |
| 5 | Persistence | 1 |
| 6 | Soft reset engine | 3 |
| 7 | Event listener | 3, 6 |
| 8 | UI | 2, 3, 4, 5, 6 |
| 9 | Integration & hardening | All |
| 10 | Polish & release | All |
