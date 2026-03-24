"""
Display Config Manager
Read, validate, apply, and rollback display settings using Windows APIs.
All operations are safe — CDS_TEST is always called before applying.
"""
import ctypes
import ctypes.wintypes as wt
from dataclasses import dataclass, asdict
from typing import Optional, List
from utils.logger import setup_logger

log = setup_logger("lumynex.display_config")

# ─────────────────────────────────────────────────────────────────────────────
# Windows constants
# ─────────────────────────────────────────────────────────────────────────────

ENUM_CURRENT_SETTINGS       = -1
ENUM_REGISTRY_SETTINGS      = -2

CDS_TEST                    = 0x00000002
CDS_UPDATEREGISTRY          = 0x00000001
CDS_NORESET                 = 0x10000000
CDS_RESET                   = 0x40000000

DISP_CHANGE_SUCCESSFUL      = 0
DISP_CHANGE_RESTART         = 1
DISP_CHANGE_FAILED          = -1
DISP_CHANGE_BADMODE         = -2
DISP_CHANGE_NOTUPDATED      = -3
DISP_CHANGE_BADFLAGS        = -4
DISP_CHANGE_BADPARAM        = -5
DISP_CHANGE_BADDUALVIEW     = -6

# dmFields flags
DM_PELSWIDTH                = 0x00080000
DM_PELSHEIGHT               = 0x00100000
DM_DISPLAYFREQUENCY         = 0x00400000
DM_BITSPERPEL               = 0x00040000
DM_POSITION                 = 0x00000020
DM_DISPLAYFLAGS             = 0x00000200

DISPLAY_DEVICE_ACTIVE        = 0x00000001
DISPLAY_DEVICE_PRIMARY_DEVICE = 0x00000004

user32 = ctypes.windll.user32


# ─────────────────────────────────────────────────────────────────────────────
# Structures
# ─────────────────────────────────────────────────────────────────────────────

class DEVMODEW(ctypes.Structure):
    _fields_ = [
        ("dmDeviceName",         ctypes.c_wchar * 32),
        ("dmSpecVersion",        wt.WORD),
        ("dmDriverVersion",      wt.WORD),
        ("dmSize",               wt.WORD),
        ("dmDriverExtra",        wt.WORD),
        ("dmFields",             wt.DWORD),
        ("dmPositionX",          ctypes.c_long),
        ("dmPositionY",          ctypes.c_long),
        ("dmDisplayOrientation", wt.DWORD),
        ("dmDisplayFixedOutput", wt.DWORD),
        ("dmColor",              wt.SHORT),
        ("dmDuplex",             wt.SHORT),
        ("dmYResolution",        wt.SHORT),
        ("dmTTOption",           wt.SHORT),
        ("dmCollate",            wt.SHORT),
        ("dmFormName",           ctypes.c_wchar * 32),
        ("dmLogPixels",          wt.WORD),
        ("dmBitsPerPel",         wt.DWORD),
        ("dmPelsWidth",          wt.DWORD),
        ("dmPelsHeight",         wt.DWORD),
        ("dmDisplayFlags",       wt.DWORD),
        ("dmDisplayFrequency",   wt.DWORD),
        ("dmICMMethod",          wt.DWORD),
        ("dmICMIntent",          wt.DWORD),
        ("dmMediaType",          wt.DWORD),
        ("dmDitherType",         wt.DWORD),
        ("dmReserved1",          wt.DWORD),
        ("dmReserved2",          wt.DWORD),
        ("dmPanningWidth",       wt.DWORD),
        ("dmPanningHeight",      wt.DWORD),
    ]


class DISPLAY_DEVICEW(ctypes.Structure):
    _fields_ = [
        ("cb",           wt.DWORD),
        ("DeviceName",   ctypes.c_wchar * 32),
        ("DeviceString", ctypes.c_wchar * 128),
        ("StateFlags",   wt.DWORD),
        ("DeviceID",     ctypes.c_wchar * 128),
        ("DeviceKey",    ctypes.c_wchar * 128),
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Data classes
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class DisplaySettings:
    device_name: str     # e.g. \\.\DISPLAY1
    width: int
    height: int
    refresh_rate: int
    bits_per_pixel: int
    position_x: int = 0
    position_y: int = 0


@dataclass
class ApplyResult:
    success: bool
    code: int            # raw DISP_CHANGE_* value
    message: str
    rolled_back: bool = False


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _disp_change_message(code: int) -> str:
    return {
        DISP_CHANGE_SUCCESSFUL: "Success",
        DISP_CHANGE_RESTART:    "Restart required",
        DISP_CHANGE_FAILED:     "General failure",
        DISP_CHANGE_BADMODE:    "Mode not supported",
        DISP_CHANGE_NOTUPDATED: "Registry not updated",
        DISP_CHANGE_BADFLAGS:   "Bad flags",
        DISP_CHANGE_BADPARAM:   "Bad parameter",
        DISP_CHANGE_BADDUALVIEW: "Bad dual-view",
    }.get(code, f"Unknown code {code}")


def _read_devmode(device_name: str, mode_index=ENUM_CURRENT_SETTINGS) -> Optional[DEVMODEW]:
    dm = DEVMODEW()
    dm.dmSize = ctypes.sizeof(DEVMODEW)
    if user32.EnumDisplaySettingsW(device_name, mode_index, ctypes.byref(dm)):
        return dm
    return None


def _settings_to_devmode(s: DisplaySettings) -> DEVMODEW:
    dm = DEVMODEW()
    dm.dmSize = ctypes.sizeof(DEVMODEW)
    dm.dmFields = DM_PELSWIDTH | DM_PELSHEIGHT | DM_DISPLAYFREQUENCY | DM_BITSPERPEL | DM_POSITION
    dm.dmPelsWidth = s.width
    dm.dmPelsHeight = s.height
    dm.dmDisplayFrequency = s.refresh_rate
    dm.dmBitsPerPel = s.bits_per_pixel
    dm.dmPositionX = s.position_x
    dm.dmPositionY = s.position_y
    return dm


def _devmode_to_settings(device_name: str, dm: DEVMODEW) -> DisplaySettings:
    return DisplaySettings(
        device_name=device_name,
        width=dm.dmPelsWidth,
        height=dm.dmPelsHeight,
        refresh_rate=dm.dmDisplayFrequency,
        bits_per_pixel=dm.dmBitsPerPel,
        position_x=dm.dmPositionX,
        position_y=dm.dmPositionY,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def get_all_monitors() -> List[str]:
    """Return device names of all active monitors, e.g. ['\\\\.\\ DISPLAY1', ...]."""
    result = []
    dd = DISPLAY_DEVICEW()
    dd.cb = ctypes.sizeof(DISPLAY_DEVICEW)
    i = 0
    while user32.EnumDisplayDevicesW(None, i, ctypes.byref(dd), 0):
        if dd.StateFlags & DISPLAY_DEVICE_ACTIVE:
            result.append(dd.DeviceName)
        i += 1
    return result


def get_current_config(device_name: str) -> Optional[DisplaySettings]:
    """Snapshot the current display settings for a monitor."""
    dm = _read_devmode(device_name, ENUM_CURRENT_SETTINGS)
    if dm is None:
        log.error(f"get_current_config: could not read settings for {device_name}")
        return None
    s = _devmode_to_settings(device_name, dm)
    log.debug(f"Snapshot {device_name}: {s.width}x{s.height}@{s.refresh_rate}Hz bpp={s.bits_per_pixel}")
    return s


def test_config(settings: DisplaySettings) -> bool:
    """
    Validate settings via CDS_TEST without applying them.
    Returns True if the mode is supported.
    """
    dm = _settings_to_devmode(settings)
    code = user32.ChangeDisplaySettingsExW(settings.device_name, ctypes.byref(dm), None, CDS_TEST, None)
    ok = (code == DISP_CHANGE_SUCCESSFUL)
    log.debug(f"test_config {settings.device_name} {settings.width}x{settings.height}@{settings.refresh_rate}: "
              f"{'OK' if ok else 'REJECTED'} ({_disp_change_message(code)})")
    return ok


def apply_config(settings: DisplaySettings, save_to_registry: bool = True) -> ApplyResult:
    """
    Apply display settings with a test-first safety check.
    On failure, returns a failed ApplyResult — caller must decide to rollback.
    """
    # 1. Test first
    if not test_config(settings):
        return ApplyResult(success=False, code=DISP_CHANGE_BADMODE,
                           message=f"Mode {settings.width}x{settings.height}@{settings.refresh_rate} not supported")

    # 2. Apply
    dm = _settings_to_devmode(settings)
    flags = CDS_UPDATEREGISTRY if save_to_registry else 0
    code = user32.ChangeDisplaySettingsExW(settings.device_name, ctypes.byref(dm), None, flags, None)

    if code == DISP_CHANGE_SUCCESSFUL:
        log.info(f"Applied {settings.device_name}: {settings.width}x{settings.height}@{settings.refresh_rate}Hz")
        return ApplyResult(success=True, code=code, message="Success")

    msg = _disp_change_message(code)
    log.error(f"apply_config failed for {settings.device_name}: {msg} (code {code})")
    return ApplyResult(success=False, code=code, message=msg)


def rollback(snapshot: DisplaySettings) -> ApplyResult:
    """Restore a previously captured snapshot."""
    log.warning(f"Rolling back {snapshot.device_name} to "
                f"{snapshot.width}x{snapshot.height}@{snapshot.refresh_rate}Hz")
    result = apply_config(snapshot, save_to_registry=True)
    result.rolled_back = True
    if result.success:
        log.info(f"Rollback successful for {snapshot.device_name}")
    else:
        log.error(f"Rollback FAILED for {snapshot.device_name}: {result.message}")
    return result


def safe_apply(device_name: str, new_settings: DisplaySettings) -> ApplyResult:
    """
    Full safe-apply flow:
      snapshot → test → apply → validate → rollback on failure

    This is the primary entry point for changing display settings.
    """
    # 1. Snapshot current state
    snapshot = get_current_config(device_name)
    if snapshot is None:
        return ApplyResult(success=False, code=-1, message="Could not read current config for snapshot")

    # 2. Apply (test is done inside apply_config)
    result = apply_config(new_settings)
    if not result.success:
        return result

    # 3. Validate — re-read and confirm the settings stuck
    actual = get_current_config(device_name)
    if actual and actual.width == new_settings.width and actual.height == new_settings.height \
            and actual.refresh_rate == new_settings.refresh_rate:
        log.info(f"Validation passed for {device_name}")
        return result

    # 4. Validation failed — rollback
    log.warning(f"Validation failed for {device_name} — applied settings did not match. Rolling back.")
    rb = rollback(snapshot)
    rb.success = False
    rb.message = "Settings applied but validation failed; rolled back to previous config"
    return rb


def set_primary(device_name: str) -> ApplyResult:
    """
    Set a monitor as the primary display.
    Moves it to position (0, 0) and triggers a full display reconfiguration.
    """
    current = get_current_config(device_name)
    if current is None:
        return ApplyResult(success=False, code=-1, message=f"Cannot read config for {device_name}")

    dm = _read_devmode(device_name, ENUM_CURRENT_SETTINGS)
    if dm is None:
        return ApplyResult(success=False, code=-1, message=f"EnumDisplaySettings failed for {device_name}")

    dm.dmFields |= DM_POSITION
    dm.dmPositionX = 0
    dm.dmPositionY = 0

    flags = CDS_UPDATEREGISTRY | CDS_NORESET
    code = user32.ChangeDisplaySettingsExW(device_name, ctypes.byref(dm), None, flags, None)

    if code == DISP_CHANGE_SUCCESSFUL:
        # Commit all pending changes
        user32.ChangeDisplaySettingsExW(None, None, None, 0, None)
        log.info(f"Set primary display: {device_name}")
        return ApplyResult(success=True, code=code, message="Primary display set")

    msg = _disp_change_message(code)
    log.error(f"set_primary failed for {device_name}: {msg}")
    return ApplyResult(success=False, code=code, message=msg)


# ─────────────────────────────────────────────────────────────────────────────
# Self-test when run directly
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=== Display Config Manager — Self-Test ===\n")

    monitors = get_all_monitors()
    print(f"Active monitors: {monitors}\n")

    for dev in monitors:
        cfg = get_current_config(dev)
        if not cfg:
            print(f"  {dev}: could not read config")
            continue

        print(f"[{dev}]")
        print(f"  Current: {cfg.width}x{cfg.height} @ {cfg.refresh_rate} Hz  {cfg.bits_per_pixel} bpp")
        print(f"  Position: ({cfg.position_x}, {cfg.position_y})")

        # Test: validate the current settings (must always pass)
        ok = test_config(cfg)
        print(f"  test_config (current settings): {'PASS' if ok else 'FAIL'}")

        # Test: validate a deliberately bad mode (should fail)
        bad = DisplaySettings(device_name=dev, width=1234, height=567,
                              refresh_rate=999, bits_per_pixel=32)
        bad_ok = test_config(bad)
        print(f"  test_config (bad 1234x567@999): {'unexpected PASS' if bad_ok else 'REJECTED (expected)'}")
        print()
