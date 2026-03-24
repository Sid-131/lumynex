# AutoDisplay AI — UI Design Spec

---

## Design Philosophy
Modern Windows system utility. Dark theme, dense layout, no decorative fluff.
Inspired by HWiNFO64, MSI Afterburner, and Windows 11 Settings.

---

## Color Palette

| Token            | Hex       | Usage                                 |
|------------------|-----------|---------------------------------------|
| `bg-base`        | `#0f0f0f` | App background                        |
| `bg-surface`     | `#1a1a1a` | Cards, panels                         |
| `bg-elevated`    | `#242424` | Hover states, input backgrounds       |
| `bg-border`      | `#2e2e2e` | Dividers, card borders                |
| `text-primary`   | `#f0f0f0` | Main labels, headings                 |
| `text-secondary` | `#888888` | Sublabels, metadata                   |
| `text-muted`     | `#555555` | Disabled text, placeholders           |
| `accent`         | `#4f9eff` | Buttons, links, highlights            |
| `accent-hover`   | `#6db3ff` | Button hover                          |
| `status-ok`      | `#3ecf8e` | Normal state badge                    |
| `status-warn`    | `#f5a623` | Warning state badge                   |
| `status-error`   | `#f05252` | Error state badge                     |
| `status-apply`   | `#4f9eff` | Applying state badge                  |

---

## Typography

| Role         | Font                      | Size | Weight |
|--------------|---------------------------|------|--------|
| App title    | Segoe UI                  | 13px | 600    |
| Screen title | Segoe UI                  | 11px | 600    |
| Body         | Segoe UI                  | 10px | 400    |
| Monospace    | Consolas / Cascadia Code  | 10px | 400    |
| Badge label  | Segoe UI                  | 9px  | 700    |

---

## Navigation Structure

**Left sidebar** — fixed 200px wide, icon + label nav items.

```
┌──────────────────────────────────────────────┐
│  AutoDisplay AI              [status badge]  │
├──────────┬───────────────────────────────────┤
│ Sidebar  │  Content Area                     │
│          │                                   │
│ Dashboard│                                   │
│ Hardware │                                   │
│ Recs     │                                   │
│ Fix      │                                   │
│ Settings │                                   │
│          │                                   │
│          │                                   │
└──────────┴───────────────────────────────────┘
```

Window size: **960 × 640** (resizable, min 800×520).

---

## Status Badge Component

Shown in the top-right of the title bar. Pill shape, 8px border-radius.

| State    | Color            | Label       | Animation         |
|----------|------------------|-------------|-------------------|
| Normal   | `status-ok`      | ● NORMAL    | none              |
| Warning  | `status-warn`    | ⚠ MISMATCH  | slow pulse 2s     |
| Applying | `status-apply`   | ↻ APPLYING  | spin icon         |
| Error    | `status-error`   | ✕ ERROR     | none              |

---

## Screen 1 — Dashboard

**Purpose:** At-a-glance system state. First screen on launch.

```
┌─────────────────────────────────────────────────────────┐
│  DASHBOARD                              [● NORMAL]      │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌──────────────────────┐  ┌──────────────────────┐    │
│  │ DISPLAY 5            │  │ DISPLAY 6 (Primary)  │    │
│  │ Dell P2422H          │  │ Generic PnP          │    │
│  │──────────────────────│  │──────────────────────│    │
│  │ Current   1080×1920  │  │ Current  2560×1440   │    │
│  │           @ 60 Hz    │  │          @ 180 Hz    │    │
│  │ Recommended ✓ Match  │  │ Recommended ✓ Match  │    │
│  │                      │  │                      │    │
│  │ Scale: 100%   32bpp  │  │ Scale: 100%  32bpp   │    │
│  └──────────────────────┘  └──────────────────────┘    │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │ GPU   NVIDIA RTX 3050  6 GB     [■■■■■□□] 71%  │   │
│  │ CPU   i5-13450HX  10C/16T                       │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
│  [ Apply Recommendations ]    [ Fix Display ]           │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

**Components:**
- Monitor cards (one per connected display) — highlight in amber if mismatch
- GPU/CPU summary bar at bottom of content
- Two primary action buttons: Apply Recommendations, Fix Display
- Status badge in title bar reflects overall state

---

## Screen 2 — Hardware Info

**Purpose:** Full read-out of detected hardware. Read-only.

```
┌─────────────────────────────────────────────────────────┐
│  HARDWARE INFO                                          │
├─────────────────────────────────────────────────────────┤
│  GPU                                                    │
│  ┌───────────────────────────────────────────────────┐  │
│  │ NVIDIA GeForce RTX 3050 6GB Laptop GPU            │  │
│  │   VRAM  6 GB        Vendor  NVIDIA                │  │
│  │   Driver  32.0.15.9186                            │  │
│  ├───────────────────────────────────────────────────┤  │
│  │ Intel UHD Graphics                                │  │
│  │   VRAM  2 GB (shared)   Vendor  Intel             │  │
│  │   Driver  32.0.101.7026                           │  │
│  └───────────────────────────────────────────────────┘  │
│                                                         │
│  CPU                                                    │
│  ┌───────────────────────────────────────────────────┐  │
│  │ 13th Gen Intel Core i5-13450HX                    │  │
│  │   Cores  10       Logical  16                     │  │
│  └───────────────────────────────────────────────────┘  │
│                                                         │
│  MONITORS                                               │
│  ┌───────────────────────────────────────────────────┐  │
│  │ \\.\DISPLAY5  Dell P2422H (HDMI)                  │  │
│  │   1080×1920 @ 60 Hz   32 bpp   Portrait           │  │
│  │   DPI 96×96   Scale 100%   HDR ✗   Primary ✗      │  │
│  │   37 supported modes                              │  │
│  ├───────────────────────────────────────────────────┤  │
│  │ \\.\DISPLAY6  Generic PnP Monitor  [PRIMARY]      │  │
│  │   2560×1440 @ 180 Hz  32 bpp   Landscape          │  │
│  │   DPI 96×96   Scale 100%   HDR ✗   Primary ✓      │  │
│  │   160 supported modes                             │  │
│  └───────────────────────────────────────────────────┘  │
│                                                         │
│  [ Refresh ]                                            │
└─────────────────────────────────────────────────────────┘
```

**Components:**
- Collapsible section headers (GPU / CPU / Monitors)
- Data rows with label + value pairs
- Refresh button to re-run hardware detection

---

## Screen 3 — Recommendations

**Purpose:** Per-monitor suggested settings with ability to apply.

```
┌─────────────────────────────────────────────────────────┐
│  RECOMMENDATIONS                                        │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  \\.\DISPLAY6  Generic PnP Monitor                      │
│  ┌───────────────────────────────────────────────────┐  │
│  │          Current          Recommended             │  │
│  │  Res     2560×1440        2560×1440  ✓            │  │
│  │  Hz      180              180        ✓            │  │
│  │  Scale   100%             100%       ✓            │  │
│  │  BPP     32               32         ✓            │  │
│  │                                                   │  │
│  │  Reason: High-end GPU, monitor supports max mode  │  │
│  │                           [ Apply This Monitor ]  │  │
│  └───────────────────────────────────────────────────┘  │
│                                                         │
│  \\.\DISPLAY5  Dell P2422H                              │
│  ┌───────────────────────────────────────────────────┐  │
│  │          Current          Recommended             │  │
│  │  Res     1080×1920        1080×1920  ✓            │  │
│  │  Hz      60               60         ✓            │  │
│  │  Scale   100%             100%       ✓            │  │
│  │  BPP     32               32         ✓            │  │
│  │                                                   │  │
│  │  Reason: Max supported mode for this display      │  │
│  │                           [ Apply This Monitor ]  │  │
│  └───────────────────────────────────────────────────┘  │
│                                                         │
│  [ Apply All ]                                          │
└─────────────────────────────────────────────────────────┘
```

**Components:**
- Per-monitor card with current vs recommended two-column table
- Each differing value highlighted in amber, matching values in green with ✓
- Reason string from the recommendation engine
- Per-monitor Apply button + global Apply All
- Buttons disabled and spinner shown during Applying state

---

## Screen 4 — Fix Display

**Purpose:** One-click soft reset. Simple, focused.

```
┌─────────────────────────────────────────────────────────┐
│  FIX DISPLAY                                            │
├─────────────────────────────────────────────────────────┤
│                                                         │
│                                                         │
│        Having display issues? Flickering, wrong         │
│        resolution after sleep, or a blank screen?       │
│                                                         │
│        Soft Reset cycles the display adapter —          │
│        like unplugging and replugging, without          │
│        touching any cables.                             │
│                                                         │
│              ┌─────────────────────────┐               │
│              │   ↺  Soft Reset         │               │
│              └─────────────────────────┘               │
│                                                         │
│        Status ─────────────────────────────────        │
│        ┌─────────────────────────────────────────┐     │
│        │  Idle. No reset has been run.           │     │
│        └─────────────────────────────────────────┘     │
│                                                         │
│        Last reset:  Never                               │
│        Method:      SetupAPI (primary)                  │
│                                                         │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

**Components:**
- Large centered Soft Reset button (disabled during apply, shows spinner)
- Status box — updates in real-time: Idle → Disabling adapter → Waiting → Enabling → Reapplying → Done / Failed
- Last reset timestamp + method used
- On error: status box turns red, shows what failed and whether rollback succeeded

---

## Screen 5 — Settings

**Purpose:** App preferences + event log viewer.

```
┌─────────────────────────────────────────────────────────┐
│  SETTINGS                                               │
├─────────────────────────────────────────────────────────┤
│  Behaviour                                              │
│  ┌───────────────────────────────────────────────────┐  │
│  │  Auto-apply on startup          [ OFF ]  Toggle   │  │
│  │  Notify on mismatch             [ ON  ]  Toggle   │  │
│  │  Polling interval               5 s   [▼]        │  │
│  │  Reset debounce                 5 s   [▼]        │  │
│  └───────────────────────────────────────────────────┘  │
│                                                         │
│  Reset History                                          │
│  ┌───────────────────────────────────────────────────┐  │
│  │  2026-03-22 19:56  Soft Reset  SUCCESS            │  │
│  │  2026-03-22 18:30  Apply       SUCCESS            │  │
│  │  2026-03-21 09:12  Apply       ROLLBACK           │  │
│  └───────────────────────────────────────────────────┘  │
│                                                         │
│  Event Log                                              │
│  ┌───────────────────────────────────────────────────┐  │
│  │  2026-03-22 19:56:33  [INFO]  Hardware snapshot   │  │
│  │  2026-03-22 19:56:35  [INFO]  2 GPUs, 2 monitors  │  │
│  │  2026-03-22 20:02:30  [INFO]  Applied DISPLAY6    │  │
│  └─ monospace, scrollable ─────────────────────────┘  │
│                                                         │
│  [ Clear Log ]     [ Open Log File ]   [ Save Settings]│
└─────────────────────────────────────────────────────────┘
```

**Components:**
- Toggle switches (custom QSS styled)
- Dropdowns for numeric prefs
- Reset history table (timestamp, type, result) — sortable
- Scrollable monospace log viewer (last 200 lines)
- Save Settings writes to `config/user_settings.json`

---

## Sidebar Navigation Spec

```
Width: 200px fixed
Item height: 40px
Active item: left accent bar (4px) + bg-elevated background
Hover: bg-elevated background

Items:
  ■  Dashboard
  ⬡  Hardware
  ★  Recommendations
  ↺  Fix Display
  ⚙  Settings
```

---

## Applying State (global)

When any operation is in progress:
- Status badge → APPLYING (blue, spin icon)
- Active screen's action buttons → disabled + show inline spinner
- Sidebar navigation → still clickable (read-only view of other screens)
- Progress status text updates in real-time on the relevant screen

---

## Error State

When rollback occurs:
- Status badge → ERROR (red)
- Dashboard monitor card for affected display turns red border
- Toast notification (bottom-right, 5s) — "Settings rolled back: [reason]"
- Fix Display status box shows full trace

---
