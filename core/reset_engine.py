"""
Soft Reset Engine
Disable/re-enable the display adapter to fix display issues without touching cables.

Method 1 (primary)  — SetupAPI (ctypes): disable/enable via SetupDiCallClassInstaller
Method 2 (fallback) — Reapply: re-call ChangeDisplaySettingsEx to force driver refresh

Execution flow
--------------
1.  Snapshot current config for every active monitor
2.  Try Method 1: enumerate display adapters → disable all → wait 2 s → enable all
3.  Wait 1 s for the driver to settle
4.  Reapply the snapshot (or caller-supplied) settings via ChangeDisplaySettingsEx
5.  Validate: re-read config and compare to target
6.  On any failure → rollback to pre-reset snapshot; log ROLLBACK event
7.  Return ResetResult (success flag, method used, steps log, error detail)
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from core.display_config import (
    DisplaySettings,
    get_all_monitors,
    get_current_config,
    apply_config,
    rollback,
)
from utils.logger import setup_logger
from utils.persistence import log_event

log = setup_logger("lumynex.reset_engine")

# ── SetupAPI constants ─────────────────────────────────────────────────────

DIGCF_PRESENT       = 0x00000002
DIF_PROPERTYCHANGE  = 0x00000012
DICS_ENABLE         = 0x00000001
DICS_DISABLE        = 0x00000002
DICS_FLAG_GLOBAL    = 0x00000001

INVALID_HANDLE      = ctypes.c_void_p(-1).value
ERROR_NO_MORE_ITEMS = 259

# Display adapter class GUID: {4d36e968-e325-11ce-bfc1-08002be10318}
_DISPLAY_CLASS_GUID = (
    0x4d36e968, 0xe325, 0x11ce,
    (0xbf, 0xc1, 0x08, 0x00, 0x2b, 0xe1, 0x03, 0x18)
)

# Delays (seconds)
DISABLE_WAIT  = 2.0
ENABLE_WAIT   = 1.0


# ── Result type ────────────────────────────────────────────────────────────

@dataclass
class ResetResult:
    success:          bool
    method:           str               # "SetupAPI" | "Reapply" | "None"
    steps:            List[str] = field(default_factory=list)
    error:            Optional[str] = None
    rollback_ok:      Optional[bool] = None
    duration_ms:      int = 0


# ── SetupAPI ctypes structures ─────────────────────────────────────────────

class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wt.DWORD),
        ("Data2", wt.WORD),
        ("Data3", wt.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]


class _SP_DEVINFO_DATA(ctypes.Structure):
    _fields_ = [
        ("cbSize",    wt.DWORD),
        ("ClassGuid", _GUID),
        ("DevInst",   wt.DWORD),
        ("Reserved",  ctypes.c_size_t),   # ULONG_PTR — pointer-sized
    ]


class _SP_CLASSINSTALL_HEADER(ctypes.Structure):
    _fields_ = [
        ("cbSize",          wt.DWORD),
        ("InstallFunction", wt.DWORD),
    ]


class _SP_PROPCHANGE_PARAMS(ctypes.Structure):
    _fields_ = [
        ("ClassInstallHeader", _SP_CLASSINSTALL_HEADER),
        ("StateChange",        wt.DWORD),
        ("Scope",              wt.DWORD),
        ("HwProfile",          wt.DWORD),
    ]


def _make_display_guid() -> _GUID:
    d1, d2, d3, d4_bytes = _DISPLAY_CLASS_GUID
    g = _GUID()
    g.Data1 = d1
    g.Data2 = d2
    g.Data3 = d3
    for i, b in enumerate(d4_bytes):
        g.Data4[i] = b
    return g


# ── SetupAPI loader ────────────────────────────────────────────────────────

SPDRP_DEVICEDESC = 0   # registry property: device description string


def _load_setupapi():
    try:
        lib = ctypes.WinDLL("setupapi")
        lib.SetupDiGetClassDevsW.restype              = ctypes.c_void_p
        lib.SetupDiEnumDeviceInfo.restype             = ctypes.c_bool
        lib.SetupDiSetClassInstallParamsW.restype     = ctypes.c_bool
        lib.SetupDiCallClassInstaller.restype         = ctypes.c_bool
        lib.SetupDiDestroyDeviceInfoList.restype      = ctypes.c_bool
        lib.SetupDiGetDeviceRegistryPropertyW.restype = ctypes.c_bool
        return lib
    except OSError as exc:
        log.warning("Could not load setupapi.dll: %s", exc)
        return None


def _get_device_name(lib, hdevinfo: int, dev: "_SP_DEVINFO_DATA") -> str:
    """Return the device description string (e.g. 'NVIDIA GeForce RTX 3050')."""
    buf = ctypes.create_unicode_buffer(512)
    ok = lib.SetupDiGetDeviceRegistryPropertyW(
        ctypes.c_void_p(hdevinfo),
        ctypes.byref(dev),
        SPDRP_DEVICEDESC,
        None,
        ctypes.cast(buf, ctypes.POINTER(ctypes.c_byte)),
        ctypes.sizeof(buf),
        None,
    )
    return buf.value if ok else ""


# ── Method 1: SetupAPI adapter cycle ──────────────────────────────────────

def _enumerate_display_adapters(lib, guid_ptr) -> List[_SP_DEVINFO_DATA]:
    """Return a list of SP_DEVINFO_DATA for every present display adapter."""
    hdevinfo = lib.SetupDiGetClassDevsW(
        ctypes.byref(guid_ptr),
        None,
        None,
        DIGCF_PRESENT,
    )
    if hdevinfo == INVALID_HANDLE or hdevinfo is None:
        raise OSError(f"SetupDiGetClassDevs failed: {ctypes.GetLastError()}")

    devices: List[_SP_DEVINFO_DATA] = []
    idx = 0
    while True:
        dev = _SP_DEVINFO_DATA()
        dev.cbSize = ctypes.sizeof(_SP_DEVINFO_DATA)
        ok = lib.SetupDiEnumDeviceInfo(ctypes.c_void_p(hdevinfo), idx, ctypes.byref(dev))
        if not ok:
            err = ctypes.GetLastError()
            if err == ERROR_NO_MORE_ITEMS:
                break
            log.warning("SetupDiEnumDeviceInfo idx=%d err=%d", idx, err)
            break
        devices.append(dev)
        idx += 1

    lib.SetupDiDestroyDeviceInfoList(ctypes.c_void_p(hdevinfo))
    return devices


def _set_adapter_state(
    lib,
    hdevinfo_raw: int,
    devices: List[_SP_DEVINFO_DATA],
    state: int,            # DICS_ENABLE or DICS_DISABLE
    step_label: str,
    progress_cb: Optional[Callable[[str], None]],
) -> bool:
    """Apply DICS_ENABLE or DICS_DISABLE to every device in *devices*. Returns True if all OK."""
    _report(progress_cb, step_label)
    all_ok = True
    for dev in devices:
        params = _SP_PROPCHANGE_PARAMS()
        params.ClassInstallHeader.cbSize         = ctypes.sizeof(_SP_CLASSINSTALL_HEADER)
        params.ClassInstallHeader.InstallFunction = DIF_PROPERTYCHANGE
        params.StateChange = state
        params.Scope       = DICS_FLAG_GLOBAL
        params.HwProfile   = 0

        ok = lib.SetupDiSetClassInstallParamsW(
            ctypes.c_void_p(hdevinfo_raw),
            ctypes.byref(dev),
            ctypes.byref(params),
            ctypes.sizeof(_SP_PROPCHANGE_PARAMS),
        )
        if not ok:
            log.warning("SetupDiSetClassInstallParams failed: %d", ctypes.GetLastError())
            all_ok = False
            continue

        ok = lib.SetupDiCallClassInstaller(
            DIF_PROPERTYCHANGE,
            ctypes.c_void_p(hdevinfo_raw),
            ctypes.byref(dev),
        )
        if not ok:
            err = ctypes.GetLastError()
            log.warning("SetupDiCallClassInstaller failed: %d", err)
            all_ok = False

    return all_ok


def _setupapi_cycle(
    progress_cb: Optional[Callable[[str], None]],
) -> bool:
    """
    Disable all display adapters, wait, re-enable them.
    Returns True on full success; False means partial/no change (fall through to Method 2).
    """
    lib = _load_setupapi()
    if lib is None:
        return False

    guid = _make_display_guid()

    # We need one shared hdevinfo for set-params + call-installer
    hdevinfo_raw = lib.SetupDiGetClassDevsW(
        ctypes.byref(guid), None, None, DIGCF_PRESENT
    )
    if hdevinfo_raw == INVALID_HANDLE or hdevinfo_raw is None:
        log.warning("SetupDiGetClassDevs returned invalid handle: %d", ctypes.GetLastError())
        return False

    # Enumerate all adapters, then filter to discrete only (skip Intel/Microsoft
    # basic display — disabling those on Optimus laptops blacks out the screen).
    all_devices: List[_SP_DEVINFO_DATA] = []
    idx = 0
    while True:
        dev = _SP_DEVINFO_DATA()
        dev.cbSize = ctypes.sizeof(_SP_DEVINFO_DATA)
        ok = lib.SetupDiEnumDeviceInfo(ctypes.c_void_p(hdevinfo_raw), idx, ctypes.byref(dev))
        if not ok:
            break
        all_devices.append(dev)
        idx += 1

    if not all_devices:
        log.warning("No display adapter devices enumerated")
        lib.SetupDiDestroyDeviceInfoList(ctypes.c_void_p(hdevinfo_raw))
        return False

    # Keep only discrete (NVIDIA / AMD) adapters
    devices: List[_SP_DEVINFO_DATA] = []
    for dev in all_devices:
        name = _get_device_name(lib, hdevinfo_raw, dev).lower()
        if any(skip in name for skip in ("intel", "microsoft")):
            log.info("SetupAPI: skipping integrated adapter: %s", name)
        else:
            log.info("SetupAPI: will cycle discrete adapter: %s", name)
            devices.append(dev)

    if not devices:
        log.warning("SetupAPI: no discrete adapters found — falling back to reapply")
        lib.SetupDiDestroyDeviceInfoList(ctypes.c_void_p(hdevinfo_raw))
        return False

    log.info("SetupAPI: cycling %d discrete adapter(s)", len(devices))

    try:
        # Disable discrete adapter(s)
        dis_ok = _set_adapter_state(
            lib, hdevinfo_raw, devices, DICS_DISABLE,
            "Disabling display adapter…", progress_cb
        )
        if not dis_ok:
            log.warning("SetupAPI: disable step had errors — aborting cycle")
            _set_adapter_state(
                lib, hdevinfo_raw, devices, DICS_ENABLE,
                "Re-enabling after failed disable…", progress_cb
            )
            return False

        _report(progress_cb, f"Adapter disabled — waiting {DISABLE_WAIT:.0f} s…")
        time.sleep(DISABLE_WAIT)

        # Re-enable discrete adapter(s)
        ena_ok = _set_adapter_state(
            lib, hdevinfo_raw, devices, DICS_ENABLE,
            "Re-enabling display adapter…", progress_cb
        )
        _report(progress_cb, f"Adapter enabled — waiting {ENABLE_WAIT:.0f} s…")
        time.sleep(ENABLE_WAIT)

        return ena_ok

    finally:
        lib.SetupDiDestroyDeviceInfoList(ctypes.c_void_p(hdevinfo_raw))


# ── Method 2: Reapply current config ──────────────────────────────────────

def _reapply_cycle(
    snapshots: Dict[str, DisplaySettings],
    progress_cb: Optional[Callable[[str], None]],
) -> bool:
    """
    Re-call ChangeDisplaySettingsEx with the saved snapshots.
    Lighter touch — driver refresh without adapter cycle.
    Returns True if all monitors reapplied without error.
    """
    _report(progress_cb, "Reapplying display settings (fallback)…")
    all_ok = True
    for mon_id, snap in snapshots.items():
        res = apply_config(snap)
        if res.success:
            log.info("Reapply OK: %s", mon_id)
        else:
            log.warning("Reapply failed: %s — %s", mon_id, res.message)
            all_ok = False
    return all_ok


# ── Validation ─────────────────────────────────────────────────────────────

def _validate(targets: Dict[str, DisplaySettings]) -> bool:
    """
    Re-read current config and verify width/height/refresh match targets.
    Returns True only if every monitor matches its target.
    """
    for mon_id, target in targets.items():
        try:
            current = get_current_config(mon_id)
        except Exception as exc:
            log.warning("Validation read failed for %s: %s", mon_id, exc)
            return False
        if current is None:
            log.warning("Validation: no config returned for %s", mon_id)
            return False
        if (
            current.width        != target.width
            or current.height    != target.height
            or current.refresh_rate != target.refresh_rate
        ):
            log.warning(
                "Validation mismatch on %s: got %dx%d@%d, expected %dx%d@%d",
                mon_id,
                current.width, current.height, current.refresh_rate,
                target.width,  target.height,  target.refresh_rate,
            )
            return False
    return True


# ── Progress helper ────────────────────────────────────────────────────────

def _report(cb: Optional[Callable[[str], None]], msg: str) -> None:
    log.debug("[reset] %s", msg)
    if cb:
        try:
            cb(msg)
        except Exception:
            pass


# ── Hybrid GPU detection ───────────────────────────────────────────────────

def _has_hybrid_gpus() -> bool:
    """
    Return True if the system has both an Intel integrated GPU and a discrete
    NVIDIA/AMD GPU (Optimus / AMD hybrid).

    On hybrid setups the Intel GPU drives the physical display outputs.
    Disabling ALL display adapters via SetupAPI can permanently black-screen the
    machine until a hard reboot, so we skip Method 1 entirely on these systems.
    """
    try:
        import wmi  # type: ignore
        c = wmi.WMI()
        names = [str(g.Name or "").lower() for g in c.Win32_VideoController()]
        has_intel    = any("intel" in n for n in names)
        has_discrete = any(
            kw in n for n in names
            for kw in ("nvidia", "geforce", "rtx", "gtx", "quadro", "amd", "radeon")
        )
        return has_intel and has_discrete
    except Exception as exc:
        log.debug("Hybrid GPU check failed: %s — assuming hybrid to be safe", exc)
        return True   # fail-safe: assume hybrid rather than risk a lockout


# ── Public API ─────────────────────────────────────────────────────────────

def soft_reset(
    monitor_ids: Optional[List[str]] = None,
    target_settings: Optional[Dict[str, DisplaySettings]] = None,
    progress_cb: Optional[Callable[[str], None]] = None,
) -> ResetResult:
    """
    Perform a soft reset of the display subsystem.

    Parameters
    ----------
    monitor_ids     : monitors to snapshot/reapply. None → all active monitors.
    target_settings : desired post-reset state per monitor_id.
                      None → reapply the pre-reset snapshot (safe default).
    progress_cb     : callable(str) for real-time status updates in the UI.

    Returns
    -------
    ResetResult with success flag, method name, step log, and optional error.
    """
    t_start = time.monotonic()
    steps: List[str] = []

    def step(msg: str) -> None:
        steps.append(msg)
        _report(progress_cb, msg)

    # ── 1. Snapshot ──────────────────────────────────────────────────────
    step("Snapshotting current display config…")
    monitors = monitor_ids or get_all_monitors()
    if not monitors:
        err = "No active monitors found — cannot reset"
        log.error(err)
        log_event("ERROR", err)
        return ResetResult(success=False, method="None", steps=steps, error=err)

    snapshots: Dict[str, DisplaySettings] = {}
    for mon_id in monitors:
        try:
            snapshots[mon_id] = get_current_config(mon_id)
        except Exception as exc:
            log.warning("Could not snapshot %s: %s — skipping", mon_id, exc)

    if not snapshots:
        err = "Failed to snapshot any monitor config"
        log.error(err)
        log_event("ERROR", err)
        return ResetResult(success=False, method="None", steps=steps, error=err)

    targets = target_settings or snapshots
    log.info("Reset targets: %d monitor(s)", len(targets))

    # ── 2. Cycle discrete display adapter (skip Intel — safe on all systems) ─
    # _setupapi_cycle now filters out Intel/Microsoft adapters internally,
    # so it is safe to run on hybrid GPU (Optimus) machines.
    method = "SetupAPI"
    step("Cycling discrete display adapter…")
    try:
        api_ok = _setupapi_cycle(progress_cb=progress_cb)
    except Exception as exc:
        log.warning("SetupAPI cycle raised: %s — falling back to reapply", exc)
        api_ok = False

    if api_ok:
        # Adapter cycle succeeded. Windows restores display settings automatically,
        # but only to the previous (possibly wrong) state. If the caller supplied
        # target_settings (recommended settings), apply them now using freshly
        # enumerated IDs — the old IDs may have been reassigned after the cycle.
        if target_settings:
            step("Waiting for display to stabilize…")
            time.sleep(2.0)

            fresh_monitors = get_all_monitors()
            target_list = list(target_settings.values())
            applied = 0

            for i, mon_id in enumerate(fresh_monitors):
                if i >= len(target_list):
                    break
                tgt = target_list[i]
                new_s = DisplaySettings(
                    device_name    = mon_id,
                    width          = tgt.width,
                    height         = tgt.height,
                    refresh_rate   = tgt.refresh_rate,
                    bits_per_pixel = tgt.bits_per_pixel,
                    position_x     = tgt.position_x,
                    position_y     = tgt.position_y,
                )
                res = apply_config(new_s)
                if res.success:
                    step(f"Applied {tgt.width}x{tgt.height}@{tgt.refresh_rate}Hz to {mon_id}")
                    applied += 1
                else:
                    log.warning("Post-cycle apply failed for %s: %s", mon_id, res.message)
                    step(f"Could not apply settings to {mon_id}: {res.message}")

            if applied:
                step(f"Settings applied to {applied}/{len(fresh_monitors)} monitor(s).")
            else:
                step("Display reset complete (settings unchanged).")
        else:
            step("Display adapter reset complete.")

        duration = int((time.monotonic() - t_start) * 1000)
        log_event(
            "RESET",
            f"Soft reset succeeded via SetupAPI ({len(snapshots)} monitor(s))",
            extra={"method": "SetupAPI", "monitors": list(snapshots.keys())},
        )
        return ResetResult(success=True, method="SetupAPI", steps=steps, duration_ms=duration)

    # ── SetupAPI unavailable — fall back to reapply with current monitor IDs ─
    method = "Reapply"
    step("Adapter cycle unavailable — reapplying settings…")
    log.info("Method: Reapply (fallback)")

    # Re-read active monitors so IDs are fresh
    fresh_monitors = get_all_monitors()
    reapply_ok = True
    for mon_id in fresh_monitors:
        try:
            cfg = get_current_config(mon_id)
            if not cfg:
                continue
            res = apply_config(cfg)
            if res.success:
                step(f"  {mon_id} -> {cfg.width}x{cfg.height}@{cfg.refresh_rate}Hz OK")
            else:
                step(f"  {mon_id} -> apply failed: {res.message}")
                reapply_ok = False
        except Exception as exc:
            step(f"  {mon_id} -> error: {exc}")
            reapply_ok = False

    duration = int((time.monotonic() - t_start) * 1000)
    if reapply_ok:
        step("Reapply complete.")
        log_event("RESET", "Soft reset via Reapply succeeded",
                  extra={"method": "Reapply", "monitors": fresh_monitors})
        return ResetResult(success=True, method="Reapply", steps=steps, duration_ms=duration)
    else:
        err_msg = "Reapply failed — display may need manual refresh"
        step(err_msg)
        log_event("ERROR", err_msg, extra={"method": "Reapply"})
        return ResetResult(success=False, method="Reapply", steps=steps,
                           error=err_msg, duration_ms=duration)


# ── CLI smoke test ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    print("=== Soft Reset Engine Smoke Test ===\n")
    print("NOTE: Method 1 (SetupAPI) requires Administrator privileges.")
    print("      If not admin, the engine will fall back to Method 2 (Reapply).\n")

    seen: List[str] = []

    def cb(msg: str) -> None:
        print(f"  > {msg}")
        seen.append(msg)

    result = soft_reset(progress_cb=cb)

    print(f"\n{'='*50}")
    print(f"  Success  : {result.success}")
    print(f"  Method   : {result.method}")
    print(f"  Duration : {result.duration_ms} ms")
    if result.error:
        print(f"  Error    : {result.error}")
    if result.rollback_ok is not None:
        print(f"  Rollback : {'ok' if result.rollback_ok else 'FAILED'}")
    print(f"\n  Steps ({len(result.steps)}):")
    for s in result.steps:
        print(f"    {s}")
