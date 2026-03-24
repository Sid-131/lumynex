# Lumynex – Architecture

## Product Overview

Lumynex is a Windows desktop application that:

- Detects system hardware (GPU, CPU, displays) via WMI and Win32 APIs
- Recommends optimal display settings per monitor based on GPU tier
- Applies configurations with test-first safety and automatic rollback
- Monitors display state in real-time via WM_DISPLAYCHANGE
- Performs a **soft reset** (disable/re-enable discrete GPU adapter) to fix display issues without touching cables

---

## High-Level Architecture

```
+----------------------+
|   Desktop UI (PyQt5) |
|  main_window.py      |
|  (QThread workers)   |
+----------+-----------+
           |
   --------------------------------
   |        |        |            |
   v        v        v            v
+------+ +------+ +--------+ +--------+
| HW   | | Disp | |Recommend| |Persist |
|detect| |Config| | Engine  | | Layer  |
+------+ +------+ +--------+ +--------+
   |        |        |            |
   --------------------------------
           |
           v
+----------------------+
|  Reset + Monitor     |
|  reset_engine.py     |
|  monitor.py          |
+----------------------+
           |
           v
+----------------------+
| Windows APIs         |
| WMI, Win32, SetupAPI |
| ctypes, pywin32      |
+----------------------+
```

---

## Core Modules

### 1. Hardware Detection (`core/hardware.py`)

**Purpose:** Fetch GPU, CPU, and per-monitor details.

**Data captured:**

- GPU: name, VRAM, vendor (NVIDIA / AMD / Intel)
- CPU: name, core count
- Per monitor: current mode, supported modes, is_primary, scale factor

**Implementation notes:**

- WMI `Win32_VideoController` for GPU list; sorted by `_VENDOR_ORDER` so discrete GPU (NVIDIA > AMD) always comes first
- **VRAM registry fallback** — on Optimus laptops WMI reports 0 MB for the discrete GPU. Fallback reads `HKLM\SYSTEM\ControlSet001\Control\Class\{4d36e968...}\HardwareInformation.qwMemorySize` matched by `DriverDesc`
- `EnumDisplayDevices` + `EnumDisplaySettings` for monitor enumeration and supported mode list

```
GPU sort order: NVIDIA=0, AMD=1, Unknown=2, Intel=3
→ gpus[0] is always the discrete GPU on hybrid systems
```

**APIs:** `win32com.client` (WMI), `ctypes`, `EnumDisplayDevices`, `EnumDisplaySettings`

---

### 2. Display Config Manager (`core/display_config.py`)

**Purpose:** Read, validate, apply, and roll back display settings.

**Key functions:**

- `get_all_monitors()` — enumerate active monitors
- `get_current_config(monitor_id)` — snapshot current DEVMODE
- `apply_config(settings)` — test via `CDS_TEST` then apply with `CDS_UPDATEREGISTRY`
- `rollback(snapshot)` — restore previous DEVMODE

**Safety flow:**

```
snapshot = get_current_config()
result   = apply_config(new_settings)   # internally: CDS_TEST first
if not result.success:
    rollback(snapshot)
    notify user
```

**APIs:** `ChangeDisplaySettingsEx`, `EnumDisplaySettings`, `EnumDisplaySettingsEx`

---

### 3. Recommendation Engine (`core/recommender.py`)

**Purpose:** Suggest optimal settings per monitor based on GPU capability.

**GPU tier classification:**

| Tier | Condition |
|------|-----------|
| `low` | VRAM < 4 GB |
| `mid` | VRAM 4–8 GB |
| `high` | VRAM > 8 GB or NVIDIA/AMD with high VRAM |

**Rule logic:**

```
FOR each monitor:
    IF low-end GPU:
        recommend max supported mode up to 1080p @ 60Hz
    ELIF high-end GPU:
        recommend max resolution + max refresh rate from supported modes
    IF on battery:
        cap refresh rate at 60Hz
    IF multi-monitor and modes mismatch:
        emit conflict warning
```

**Output:** `List[Recommendation]` — per monitor with `recommended_width`, `recommended_height`, `recommended_refresh`, `bit_depth`, `reason`, `conflict`

---

### 4. Soft Reset Engine (`core/reset_engine.py`)

**Purpose:** Fix display issues (flickering, wrong resolution after wake, blank screen) by cycling the discrete GPU adapter — no cable required.

#### Method 1 — SetupAPI adapter cycle (primary)

Enumerates display adapter devices, **filters out Intel and Microsoft Basic Display adapters by name**, then disables and re-enables only discrete (NVIDIA/AMD) adapters.

```
SetupDiGetClassDevsW(GUID_DEVCLASS_DISPLAY)
  → for each device:
      name = SetupDiGetDeviceRegistryPropertyW(SPDRP_DEVICEDESC)
      IF "intel" or "microsoft" in name → SKIP
  → disable remaining devices (DIF_PROPERTYCHANGE / DICS_DISABLE)
  → sleep 2 s
  → enable remaining devices (DIF_PROPERTYCHANGE / DICS_ENABLE)
  → sleep 1 s
  → report SUCCESS immediately
```

**Why skip Intel:** On Optimus laptops (Intel + NVIDIA), the Intel GPU drives the physical display outputs. Disabling Intel cuts power to the screen with no recovery path. Only cycling the discrete adapter is safe.

**Why report success immediately after cycle:** After SetupAPI cycles an adapter, Windows reassigns display IDs. Any settings built before the cycle reference stale IDs — applying them fails. Windows restores display settings automatically on adapter re-enable, so a post-cycle reapply is redundant and error-prone.

#### Method 2 — Reapply fallback

Used when no discrete adapter is found or SetupAPI fails. Re-reads all active monitor IDs fresh (not from snapshot) and re-calls `ChangeDisplaySettingsEx` on each.

#### Execution flow:

```
1. Snapshot current config
2. Enumerate adapters → filter to discrete only (skip Intel/Microsoft)
3. IF discrete adapters found:
     Disable → wait 2s → Enable → wait 1s → SUCCESS
4. ELSE:
     Re-read fresh monitor list
     Reapply current config via ChangeDisplaySettingsEx
     Report success/failure
```

**APIs:** `setupapi.dll` via ctypes — `SetupDiGetClassDevsW`, `SetupDiEnumDeviceInfo`, `SetupDiGetDeviceRegistryPropertyW`, `SetupDiSetClassInstallParamsW`, `SetupDiCallClassInstaller`

---

### 5. Event Listener (`core/monitor.py`)

**Purpose:** Detect display changes in real-time and trigger a data refresh.

**Implementation:**

- **Primary:** Hidden window pumping `WM_DISPLAYCHANGE` via `win32gui` in a daemon thread
- **Fallback:** Polling loop every N seconds (configurable; default 5s) comparing a hash of all monitors' current modes

**Debounce + cooldown:**

```
on WM_DISPLAYCHANGE or poll change:
    IF time_since_last_reset < cooldown_s (default 5s):
        suppress — prevent feedback loop from reset firing changes
    ELSE:
        debounce 500ms → emit changed signal → main window refreshes data
```

`notify_reset_done()` is called **before** the reset worker starts so that `ChangeDisplaySettingsEx` calls during the reset are suppressed immediately.

---

### 6. Persistence Layer (`utils/persistence.py`)

**Purpose:** Thread-safe read/write of settings and event log.

**Files:**

| File | Contents |
|------|----------|
| `config/defaults.json` | Shipped defaults (read-only, bundled in exe) |
| `config/user_settings.json` | User overrides (written next to exe at runtime) |
| `config/event_log.jsonl` | Full timestamped event log |
| `config/reset_history.jsonl` | Apply / reset / rollback events only |

**Path resolution (`utils/paths.py`):**

```python
bundle_dir()  →  sys._MEIPASS  (frozen)  OR  project root (source)
data_dir()    →  exe directory (frozen)  OR  project root (source)
```

This ensures `defaults.json` and `styles.qss` are read from the PyInstaller temp bundle, while writable user data is stored next to the exe — not in the temp dir which is deleted on exit.

---

### 7. Admin Privilege Handler (`utils/admin_check.py`)

**Flow:**

```
On app start:
    ctypes.windll.shell32.IsUserAnAdmin()
    IF True  → full mode (apply + reset enabled)
    IF False → dialog: "Restart as Administrator" or "Continue Read-Only"
               → re-launch via ShellExecuteW("runas") OR read-only mode
```

**UI enforcement:**

- `MainWindow.is_admin` flag propagated to all screens via `set_apply_enabled()` and `set_admin_mode()`
- Apply/reset buttons always disabled for non-admin regardless of any other state
- "Read-Only" badge shown in top bar when not admin

---

### 8. UI Layer (`ui/`)

**Framework:** PyQt5, packaged as single-file exe via PyInstaller

**Background workers (QThread):**

| Worker | Does |
|--------|------|
| `_HardwareWorker` | Runs `get_hardware_snapshot()` + `get_current_config()` for all monitors |
| `_RecommendWorker` | Runs `recommend()` from snapshot data |
| `_ApplyWorker` | Calls `apply_config()` per recommendation; rolls back on failure |
| `_ResetWorker` | Calls `soft_reset()` with optional target settings |

All workers call `pythoncom.CoInitialize()` on their thread before using WMI — required in the frozen exe where COM is not automatically initialised per thread.

**Busy guard:**

`_is_busy()` checks `_apply_worker.isRunning()` and `_reset_worker.isRunning()`. Worker refs are set to `None` immediately in done handlers to prevent false-positive busy state from Qt's thread cleanup race condition.

**Screens:**

| Screen | Purpose |
|--------|---------|
| Dashboard | System snapshot (GPU, CPU, primary display), health score ring, quick Apply |
| Hardware | Full GPU/CPU/monitor specs including all supported modes |
| Recommendations | Current vs Recommended per monitor; "Already Optimal" when settings match |
| Fix Display | Soft Reset with real-time status feedback |
| Settings | Polling interval, auto-apply toggle, event log viewer, reset history |

---

## End-to-End Flow

```
App Start
   ↓
Admin check → UAC prompt or read-only mode
   ↓
Load stylesheet (bundle_dir/assets/styles.qss)
Load settings  (bundle_dir/config/defaults.json + data_dir/config/user_settings.json)
   ↓
_HardwareWorker → GPU (VRAM registry fallback if WMI=0) + monitors
   ↓
_RecommendWorker → per-monitor recommendations
   ↓
Badge: Normal (all match) or Mismatch
Refresh current screen
   ↓
DisplayMonitorThread starts (WM_DISPLAYCHANGE + polling)
   ↓
User clicks Apply                       User clicks Soft Reset
   ↓                                        ↓
_ApplyWorker                            notify_reset_done() → arm cooldown
apply_config (CDS_TEST first)           _ResetWorker
rollback on failure                     SetupAPI discrete-only cycle
refresh data                            OR reapply fallback
   ↓                                        ↓
Save event to event_log.jsonl       Save event to event_log.jsonl
```

---

## Tech Stack

| Layer | Tech |
|-------|------|
| Language | Python 3.10+ |
| UI | PyQt5 |
| System access | pywin32, WMI (`win32com.client`), ctypes |
| Display APIs | `EnumDisplaySettings`, `ChangeDisplaySettingsEx`, SetupAPI |
| Hardware info | WMI + Windows registry (`winreg`) |
| Persistence | JSON / JSONL (stdlib) |
| Logging | Python `logging` with `RotatingFileHandler` |
| Packaging | PyInstaller 6+ (single-file exe, UAC manifest embedded) |

---

## Security / Permissions

- Requires **Administrator privileges** for apply and soft reset
- UAC manifest (`requireAdministrator`) embedded in exe — Windows always prompts on launch
- Read-only mode available without admin (detect + recommend only, no mutations)
- No network access, no telemetry, no external services

---

## Edge Cases

| Scenario | Handling |
|----------|----------|
| Unsupported resolution requested | `CDS_TEST` rejects before apply |
| Apply fails mid-way | Automatic rollback to pre-apply snapshot |
| Soft reset fires WM_DISPLAYCHANGE | 5s cooldown (armed before worker starts) suppresses it |
| Optimus laptop (Intel + NVIDIA) | Intel adapter name-filtered out of SetupAPI cycle |
| Display IDs change after adapter cycle | Cycle reports success immediately; no stale-ID reapply |
| WMI reports 0 MB VRAM (Optimus) | Registry fallback reads `HardwareInformation.qwMemorySize` |
| NVIDIA/AMD control panel override | Warn user in recommendations with vendor-specific tip |
| Worker exception in frozen exe | `done` signal always emitted via `except` block; button never stuck |
| Non-admin user | All mutating buttons blocked; dialog prompts UAC re-launch |
| Writable data in frozen exe | `data_dir()` resolves to exe directory, not temp `_MEIPASS` |

---

## Folder Structure

```
autodisplay-ai/
├── main.py                   Entry point, admin check, app init
├── build.bat                 One-command PyInstaller build
├── lumynex.spec              PyInstaller spec (uac_admin=True, single-file)
├── lumynex.manifest          UAC requireAdministrator XML manifest
├── requirements.txt
│
├── core/
│   ├── hardware.py           GPU/CPU/monitor detection (WMI + registry + Win32)
│   ├── display_config.py     Read / test / apply / rollback display settings
│   ├── recommender.py        Rule-based per-monitor recommendation engine
│   ├── reset_engine.py       SetupAPI discrete-only adapter cycle + reapply fallback
│   └── monitor.py            WM_DISPLAYCHANGE listener + polling + debounce/cooldown
│
├── ui/
│   ├── main_window.py        Main window, QThread workers, app state, busy guard
│   ├── dashboard.py          System snapshot, score ring, quick actions
│   ├── hardware_view.py      Full GPU / CPU / monitor spec view
│   ├── recommendations.py    Current vs Recommended per monitor
│   ├── fix_display.py        Soft reset screen with real-time status
│   ├── settings_view.py      Preferences, event log viewer, reset history
│   └── widgets.py            Shared widgets, stylesheet loader, Lumynex logo
│
├── utils/
│   ├── admin_check.py        IsUserAnAdmin + ShellExecute runas re-launch
│   ├── logger.py             RotatingFileHandler (writes to data_dir/logs/)
│   ├── paths.py              bundle_dir() / data_dir() for frozen vs source
│   └── persistence.py        Thread-safe atomic settings + JSONL event log
│
├── assets/
│   ├── styles.qss            PyQt5 stylesheet (white + purple/cyan theme)
│   ├── icon.ico              App icon (256x256)
│   └── generate_icon.py      Renders LumynexSymbol widget to icon.ico
│
└── config/
    ├── defaults.json         Shipped defaults (bundled read-only in exe)
    ├── user_settings.json    Runtime user overrides (written next to exe)
    ├── event_log.jsonl       Full event log
    └── reset_history.jsonl   Apply / reset / rollback history
```

---

## Key Design Decisions

**Why filter Intel by name instead of skipping SetupAPI on hybrid systems?**
The original design detected hybrid GPUs via WMI and fell back to Reapply entirely (no visible effect). Filtering by adapter name at cycle time achieves safety without losing the visible disable/enable behavior.

**Why report success after adapter cycle without reapplying settings?**
After SetupAPI cycles an adapter, Windows reassigns display IDs. Target settings built before the cycle reference stale IDs — `ChangeDisplaySettingsEx` fails on them. Windows restores settings automatically on adapter re-enable.

**Why arm the monitor cooldown before the reset worker starts?**
`ChangeDisplaySettingsEx` (called inside the worker) fires `WM_DISPLAYCHANGE`. Arming the cooldown first ensures that event is suppressed before it arrives, not after.

**Why null out worker refs in done handlers?**
After a QThread's `run()` returns, `isRunning()` may still return `True` briefly during Qt's internal thread cleanup. Nulling the ref in the `done` handler makes `_is_busy()` return `False` as soon as the operation logically completes, preventing the next button click from being silently ignored.
