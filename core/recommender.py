"""
Recommendation Engine
Produces per-monitor optimal display settings from hardware + monitor data.
Pure logic — no Windows API calls. Fully unit-testable with mock data.
"""
import ctypes
from dataclasses import dataclass
from typing import List, Optional
from utils.logger import setup_logger

log = setup_logger("lumynex.recommender")

# ── GPU tier thresholds ────────────────────────────────────────────────────

VRAM_LOW_MB  = 4096   # < 4 GB  → low-end
VRAM_HIGH_MB = 6144   # >= 6 GB → high-end (4–6 GB = mid)


# ── Data structures ────────────────────────────────────────────────────────

@dataclass
class MonitorInfo:
    """Input: what hardware.py / display_config.py know about a monitor."""
    monitor_id: str        # e.g. r"\\.\DISPLAY6"
    current_width: int
    current_height: int
    current_refresh: int
    current_scale: int     # percent, e.g. 100 or 125
    bit_depth: int
    is_primary: bool
    supported_modes: list  # list of (width, height, refresh) tuples


@dataclass
class GpuInfo:
    name: str
    vram_mb: int           # 0 if unknown (e.g. Intel shared)
    vendor: str            # "NVIDIA" / "AMD" / "Intel"


@dataclass
class Recommendation:
    monitor_id: str
    recommended_width: int
    recommended_height: int
    recommended_refresh: int
    recommended_scale: int
    bit_depth: int
    reason: str
    conflict: Optional[str] = None   # warning text if multi-monitor conflict


# ── GPU tier classifier ────────────────────────────────────────────────────

def classify_gpu(gpu: GpuInfo) -> str:
    """Return 'low', 'mid', or 'high' based on VRAM and vendor."""
    if gpu.vendor.upper() == "INTEL":
        return "low"
    # WMI sometimes returns -1 for dedicated VRAM on laptops.
    # Fall back to vendor name heuristics for known high-end product lines.
    if gpu.vram_mb <= 0:
        name_upper = gpu.name.upper()
        if any(k in name_upper for k in ("RTX", "RX 6", "RX 7", "RADEON RX")):
            return "high"
        if any(k in name_upper for k in ("GTX 10", "GTX 16", "GTX 20", "RX 5")):
            return "mid"
        return "low"
    if gpu.vram_mb < VRAM_LOW_MB:
        return "low"
    if gpu.vram_mb >= VRAM_HIGH_MB:
        return "high"
    return "mid"


# ── Power state ────────────────────────────────────────────────────────────

def _is_on_battery() -> bool:
    """Return True if system is running on battery power."""
    try:
        class SYSTEM_POWER_STATUS(ctypes.Structure):
            _fields_ = [
                ("ACLineStatus",        ctypes.c_byte),
                ("BatteryFlag",         ctypes.c_byte),
                ("BatteryLifePercent",  ctypes.c_byte),
                ("Reserved1",           ctypes.c_byte),
                ("BatteryLifeTime",     ctypes.c_ulong),
                ("BatteryFullLifeTime", ctypes.c_ulong),
            ]
        sps = SYSTEM_POWER_STATUS()
        ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(sps))
        return sps.ACLineStatus == 0   # 0 = battery, 1 = AC, 255 = unknown
    except Exception:
        return False


# ── Per-monitor logic ──────────────────────────────────────────────────────

def _best_resolution(monitor: MonitorInfo, max_width: int, max_height: int):
    """
    From supported modes, return the highest resolution that fits within
    max_width x max_height at the monitor's native aspect ratio.
    Returns (width, height) or the monitor's current if nothing better found.
    """
    if not monitor.supported_modes:
        return monitor.current_width, monitor.current_height

    candidates = [
        (w, h) for w, h, _ in monitor.supported_modes
        if w <= max_width and h <= max_height
    ]
    if not candidates:
        return monitor.current_width, monitor.current_height

    return max(candidates, key=lambda wh: wh[0] * wh[1])


def _max_refresh_for_resolution(monitor: MonitorInfo, width: int, height: int) -> int:
    """Return the highest refresh rate supported at the given resolution."""
    rates = [r for w, h, r in monitor.supported_modes if w == width and h == height]
    return max(rates) if rates else monitor.current_refresh


def _recommend_single(
    monitor: MonitorInfo,
    gpu_tier: str,
    on_battery: bool,
) -> Recommendation:
    """Core rule logic for a single monitor."""

    # ── Resolution cap by GPU tier ─────────────────────────
    if gpu_tier == "low":
        target_w, target_h = _best_resolution(monitor, 1920, 1080)
        tier_reason = "low-end GPU (< 4 GB VRAM) — capped at 1080p"
    elif gpu_tier == "mid":
        target_w, target_h = _best_resolution(monitor, 2560, 1440)
        tier_reason = "mid-range GPU — capped at 1440p"
    else:
        # high-end: use monitor's native maximum
        target_w, target_h = _best_resolution(monitor, 99999, 99999)
        tier_reason = "high-end GPU — maximum resolution"

    # ── Refresh rate ───────────────────────────────────────
    max_refresh = _max_refresh_for_resolution(monitor, target_w, target_h)
    if on_battery and max_refresh > 60:
        rec_refresh = 60
        refresh_reason = "battery mode — capped at 60 Hz"
    else:
        rec_refresh = max_refresh
        refresh_reason = f"maximum supported rate at {target_w}×{target_h}"

    # ── Scaling ────────────────────────────────────────────
    # Recommend 100% for high-res monitors; 125% for 1080p on laptop
    if target_w >= 2560:
        rec_scale = 100
    elif target_w == 1920 and monitor.is_primary is False:
        rec_scale = 100
    else:
        rec_scale = monitor.current_scale   # preserve user preference

    reason = f"{tier_reason}; {refresh_reason}"
    log.debug("Recommendation for %s: %dx%d@%dHz scale=%d%% — %s",
              monitor.monitor_id, target_w, target_h, rec_refresh, rec_scale, reason)

    return Recommendation(
        monitor_id=monitor.monitor_id,
        recommended_width=target_w,
        recommended_height=target_h,
        recommended_refresh=rec_refresh,
        recommended_scale=rec_scale,
        bit_depth=monitor.bit_depth or 32,
        reason=reason,
    )


# ── Clone / mirror conflict detection ─────────────────────────────────────

def _detect_clone_conflict(monitors: List[MonitorInfo]) -> Optional[str]:
    """
    If two monitors share the same position (0,0) they may be in clone mode.
    In clone mode all monitors must use a shared compatible resolution.
    Returns a warning string if a potential conflict is detected.
    This is a heuristic — real clone detection needs DISPLAYCONFIG APIs.
    """
    # Check for duplicate resolutions that are drastically different
    res_set = {(m.current_width, m.current_height) for m in monitors}
    if len(res_set) > 1 and len(monitors) > 1:
        # Monitors with very different native resolutions in a multi-display setup
        widths = [m.current_width for m in monitors]
        if max(widths) / min(widths) > 1.5:
            return (
                "Multi-monitor resolution mismatch detected "
                f"({' / '.join(f'{m.current_width}×{m.current_height}' for m in monitors)}). "
                "If using clone/mirror mode, set all displays to the highest shared resolution."
            )
    return None


# ── Public API ─────────────────────────────────────────────────────────────

def recommend(
    monitors: List[MonitorInfo],
    gpus: List[GpuInfo],
    on_battery: Optional[bool] = None,
) -> List[Recommendation]:
    """
    Generate per-monitor recommendations.

    Parameters
    ----------
    monitors : list of MonitorInfo
    gpus     : list of GpuInfo (use the best discrete GPU for tier)
    on_battery : bool or None (auto-detect if None)

    Returns
    -------
    list of Recommendation, one per monitor
    """
    if on_battery is None:
        on_battery = _is_on_battery()

    # Pick the best GPU for classification: prefer discrete (NVIDIA/AMD)
    discrete = [g for g in gpus if g.vendor.upper() in ("NVIDIA", "AMD")]
    best_gpu = max(discrete, key=lambda g: g.vram_mb) if discrete else (gpus[0] if gpus else None)

    if best_gpu is None:
        log.warning("No GPU info provided; defaulting to low-end tier")
        gpu_tier = "low"
    else:
        gpu_tier = classify_gpu(best_gpu)
        log.info("GPU tier: %s (%s, %d MB VRAM)", gpu_tier, best_gpu.name, best_gpu.vram_mb)

    if on_battery:
        log.info("Power state: battery — refresh rate will be capped at 60 Hz")
    else:
        log.info("Power state: AC power")

    recs = [_recommend_single(m, gpu_tier, on_battery) for m in monitors]

    # Attach clone conflict warning to all recs if detected
    conflict = _detect_clone_conflict(monitors)
    if conflict:
        log.warning("Clone conflict: %s", conflict)
        for r in recs:
            r.conflict = conflict

    return recs


# ── CLI test ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from core.hardware import get_hardware_snapshot
    from core.display_config import get_all_monitors, get_current_config

    hw = get_hardware_snapshot()

    # Build GpuInfo list from dataclass attributes
    gpu_list = [
        GpuInfo(name=g.name, vram_mb=g.vram_mb, vendor=g.vendor)
        for g in hw.gpus
    ]

    # Build MonitorInfo list from live display config + hardware snapshot
    monitor_list = []
    for mon_id in get_all_monitors():
        cfg = get_current_config(mon_id)
        hw_mon = next((m for m in hw.monitors if m.device_name == mon_id), None)
        modes = [(m.width, m.height, m.refresh_rate) for m in hw_mon.supported_modes] if hw_mon else []
        monitor_list.append(MonitorInfo(
            monitor_id=mon_id,
            current_width=cfg.width,
            current_height=cfg.height,
            current_refresh=cfg.refresh_rate,
            current_scale=100,
            bit_depth=cfg.bits_per_pixel,
            is_primary=hw_mon.is_primary if hw_mon else False,
            supported_modes=modes,
        ))

    recs = recommend(monitor_list, gpu_list)

    print("\n-- Recommendations ------------------------------------------")
    for r in recs:
        match = (
            r.recommended_width == monitor_list[0].current_width
        )
        print(f"\n  {r.monitor_id}")
        print(f"    Resolution : {r.recommended_width}×{r.recommended_height}")
        print(f"    Refresh    : {r.recommended_refresh} Hz")
        print(f"    Scale      : {r.recommended_scale}%")
        print(f"    Bit depth  : {r.bit_depth} bpp")
        print(f"    Reason     : {r.reason}")
        if r.conflict:
            print(f"    ! Conflict : {r.conflict}")
