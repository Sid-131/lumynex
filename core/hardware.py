"""
Hardware Detection Module
Detects GPU, CPU, and all connected monitors.
All public functions return plain dicts — no external state.
"""
import ctypes
import ctypes.wintypes as wt
from dataclasses import dataclass, field, asdict
from typing import List, Optional
from utils.logger import setup_logger

log = setup_logger("lumynex.hardware")

# ─────────────────────────────────────────────────────────────────────────────
# Data classes
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class GPUInfo:
    name: str
    vram_mb: int           # 0 if unknown
    vendor: str            # "NVIDIA" | "AMD" | "Intel" | "Unknown"
    driver_version: str = ""


@dataclass
class CPUInfo:
    name: str
    cores: int
    logical_processors: int


@dataclass
class DisplayMode:
    width: int
    height: int
    refresh_rate: int
    bits_per_pixel: int


@dataclass
class MonitorInfo:
    device_name: str       # e.g. \\.\DISPLAY1
    friendly_name: str
    monitor_id: str        # adapter + monitor string used as stable key
    is_primary: bool
    current_width: int
    current_height: int
    current_refresh_rate: int
    current_bpp: int
    hdr_supported: bool
    dpi_x: int
    dpi_y: int
    scale_factor: int      # percent, e.g. 125
    supported_modes: List[DisplayMode] = field(default_factory=list)


@dataclass
class HardwareSnapshot:
    gpus: List[GPUInfo]
    cpu: Optional[CPUInfo]
    monitors: List[MonitorInfo]


# ─────────────────────────────────────────────────────────────────────────────
# GPU detection via WMI
# ─────────────────────────────────────────────────────────────────────────────

_VENDOR_ORDER = {"NVIDIA": 0, "AMD": 1, "Unknown": 2, "Intel": 3}


def _get_vram_from_registry(gpu_name: str) -> int:
    """
    Read dedicated VRAM from the display adapter class registry key.
    Reliable for discrete GPUs on Optimus/hybrid laptops where WMI returns 0.
    Returns VRAM in MB, or 0 if not found.
    """
    import winreg
    KEY = r"SYSTEM\ControlSet001\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, KEY) as parent:
            i = 0
            while True:
                try:
                    sub_name = winreg.EnumKey(parent, i)
                    i += 1
                    if sub_name == "Properties":
                        continue
                    with winreg.OpenKey(parent, sub_name) as sub:
                        try:
                            desc, _ = winreg.QueryValueEx(sub, "DriverDesc")
                        except OSError:
                            continue
                        # Loose match: either name contains desc substring or vice versa
                        if (gpu_name.lower() not in desc.lower() and
                                desc.lower() not in gpu_name.lower()):
                            continue
                        for val in ("HardwareInformation.qwMemorySize",
                                    "HardwareInformation.MemorySize"):
                            try:
                                vram_bytes, _ = winreg.QueryValueEx(sub, val)
                                if isinstance(vram_bytes, int) and vram_bytes > 0:
                                    return vram_bytes // (1024 * 1024)
                            except OSError:
                                pass
                except OSError:
                    break
    except Exception as exc:
        log.debug("Registry VRAM lookup failed: %s", exc)
    return 0


def _detect_gpus() -> List[GPUInfo]:
    gpus: List[GPUInfo] = []
    try:
        import wmi  # type: ignore
        c = wmi.WMI()
        for gpu in c.Win32_VideoController():
            name = gpu.Name or "Unknown GPU"
            vram = 0
            try:
                vram = int(gpu.AdapterRAM or 0) // (1024 * 1024)
            except Exception:
                pass

            vendor = "Unknown"
            name_lower = name.lower()
            if "nvidia" in name_lower or "geforce" in name_lower or "quadro" in name_lower or "rtx" in name_lower or "gtx" in name_lower:
                vendor = "NVIDIA"
            elif "amd" in name_lower or "radeon" in name_lower or "rx " in name_lower:
                vendor = "AMD"
            elif "intel" in name_lower or "uhd" in name_lower or "iris" in name_lower or "hd graphics" in name_lower:
                vendor = "Intel"

            # WMI AdapterRAM is unreliable for discrete GPUs on Optimus/hybrid laptops.
            # Fall back to registry for NVIDIA/AMD when WMI reports < 512 MB.
            if vendor in ("NVIDIA", "AMD") and vram < 512:
                reg_vram = _get_vram_from_registry(name)
                if reg_vram > vram:
                    log.debug("VRAM from registry for %s: %d MB (WMI reported %d MB)", name, reg_vram, vram)
                    vram = reg_vram

            driver = gpu.DriverVersion or ""
            gpus.append(GPUInfo(name=name, vram_mb=vram, vendor=vendor, driver_version=driver))
    except Exception as e:
        log.warning(f"WMI GPU detection failed: {e}")

    if not gpus:
        log.warning("No GPU detected via WMI.")
        return gpus

    # Sort: discrete GPUs (NVIDIA > AMD) before integrated (Intel) so snap.gpus[0]
    # is always the best available GPU, not the integrated one.
    gpus.sort(key=lambda g: _VENDOR_ORDER.get(g.vendor, 2))
    return gpus


# ─────────────────────────────────────────────────────────────────────────────
# CPU detection via WMI
# ─────────────────────────────────────────────────────────────────────────────

def _detect_cpu() -> Optional[CPUInfo]:
    try:
        import wmi  # type: ignore
        c = wmi.WMI()
        procs = c.Win32_Processor()
        if procs:
            p = procs[0]
            name = p.Name.strip() if p.Name else "Unknown CPU"
            cores = int(p.NumberOfCores or 1)
            logical = int(p.NumberOfLogicalProcessors or cores)
            return CPUInfo(name=name, cores=cores, logical_processors=logical)
    except Exception as e:
        log.warning(f"WMI CPU detection failed: {e}")
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Monitor detection via Win32 APIs
# ─────────────────────────────────────────────────────────────────────────────

# Structures
class DEVMODEW(ctypes.Structure):
    _fields_ = [
        ("dmDeviceName",      ctypes.c_wchar * 32),
        ("dmSpecVersion",     wt.WORD),
        ("dmDriverVersion",   wt.WORD),
        ("dmSize",            wt.WORD),
        ("dmDriverExtra",     wt.WORD),
        ("dmFields",          wt.DWORD),
        ("dmPositionX",       ctypes.c_long),
        ("dmPositionY",       ctypes.c_long),
        ("dmDisplayOrientation", wt.DWORD),
        ("dmDisplayFixedOutput", wt.DWORD),
        ("dmColor",           wt.SHORT),
        ("dmDuplex",          wt.SHORT),
        ("dmYResolution",     wt.SHORT),
        ("dmTTOption",        wt.SHORT),
        ("dmCollate",         wt.SHORT),
        ("dmFormName",        ctypes.c_wchar * 32),
        ("dmLogPixels",       wt.WORD),
        ("dmBitsPerPel",      wt.DWORD),
        ("dmPelsWidth",       wt.DWORD),
        ("dmPelsHeight",      wt.DWORD),
        ("dmDisplayFlags",    wt.DWORD),
        ("dmDisplayFrequency", wt.DWORD),
        ("dmICMMethod",       wt.DWORD),
        ("dmICMIntent",       wt.DWORD),
        ("dmMediaType",       wt.DWORD),
        ("dmDitherType",      wt.DWORD),
        ("dmReserved1",       wt.DWORD),
        ("dmReserved2",       wt.DWORD),
        ("dmPanningWidth",    wt.DWORD),
        ("dmPanningHeight",   wt.DWORD),
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


DISPLAY_DEVICE_ACTIVE        = 0x00000001
DISPLAY_DEVICE_PRIMARY_DEVICE = 0x00000004
ENUM_CURRENT_SETTINGS        = -1

user32 = ctypes.windll.user32
shcore = None
try:
    shcore = ctypes.windll.shcore
except Exception:
    pass


def _get_dpi_for_monitor(hmonitor) -> tuple:
    """Return (dpi_x, dpi_y). Falls back to system DPI if shcore unavailable."""
    if shcore:
        dpi_x = ctypes.c_uint(0)
        dpi_y = ctypes.c_uint(0)
        try:
            MDT_EFFECTIVE_DPI = 0
            shcore.GetDpiForMonitor(hmonitor, MDT_EFFECTIVE_DPI, ctypes.byref(dpi_x), ctypes.byref(dpi_y))
            return dpi_x.value, dpi_y.value
        except Exception:
            pass
    # Fallback: system DPI via GetDeviceCaps
    try:
        hdc = user32.GetDC(None)
        LOGPIXELSX = 88
        LOGPIXELSY = 90
        dx = ctypes.windll.gdi32.GetDeviceCaps(hdc, LOGPIXELSX)
        dy = ctypes.windll.gdi32.GetDeviceCaps(hdc, LOGPIXELSY)
        user32.ReleaseDC(None, hdc)
        return dx, dy
    except Exception:
        return 96, 96


def _build_hmonitor_map() -> dict:
    """Build a map from device_name (lower) → HMONITOR."""
    hmon_map = {}

    class MONITORINFOEXW(ctypes.Structure):
        _fields_ = [
            ("cbSize",     wt.DWORD),
            ("rcMonitor",  wt.RECT),
            ("rcWork",     wt.RECT),
            ("dwFlags",    wt.DWORD),
            ("szDevice",   ctypes.c_wchar * 32),
        ]

    monitors_found = []

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HMONITOR, wt.HDC, ctypes.POINTER(wt.RECT), ctypes.c_long)
    def _cb(hmonitor, hdc, lprect, lparam):
        info = MONITORINFOEXW()
        info.cbSize = ctypes.sizeof(MONITORINFOEXW)
        user32.GetMonitorInfoW(hmonitor, ctypes.byref(info))
        monitors_found.append((info.szDevice.lower(), hmonitor))
        return True

    user32.EnumDisplayMonitors(None, None, _cb, 0)
    for dev, hm in monitors_found:
        hmon_map[dev] = hm
    return hmon_map


def _enum_supported_modes(device_name: str) -> List[DisplayMode]:
    modes = []
    seen = set()
    dm = DEVMODEW()
    dm.dmSize = ctypes.sizeof(DEVMODEW)
    i = 0
    while user32.EnumDisplaySettingsW(device_name, i, ctypes.byref(dm)):
        key = (dm.dmPelsWidth, dm.dmPelsHeight, dm.dmDisplayFrequency, dm.dmBitsPerPel)
        if key not in seen:
            seen.add(key)
            modes.append(DisplayMode(
                width=dm.dmPelsWidth,
                height=dm.dmPelsHeight,
                refresh_rate=dm.dmDisplayFrequency,
                bits_per_pixel=dm.dmBitsPerPel,
            ))
        i += 1
    # Sort by resolution desc, then refresh rate desc
    modes.sort(key=lambda m: (m.width * m.height, m.refresh_rate), reverse=True)
    return modes


def _detect_monitors() -> List[MonitorInfo]:
    monitors: List[MonitorInfo] = []
    hmon_map = _build_hmonitor_map()

    dd = DISPLAY_DEVICEW()
    dd.cb = ctypes.sizeof(DISPLAY_DEVICEW)
    i = 0

    while user32.EnumDisplayDevicesW(None, i, ctypes.byref(dd), 0):
        i += 1
        if not (dd.StateFlags & DISPLAY_DEVICE_ACTIVE):
            continue

        device_name = dd.DeviceName  # e.g. \\.\DISPLAY1
        is_primary = bool(dd.StateFlags & DISPLAY_DEVICE_PRIMARY_DEVICE)

        # Get friendly monitor name from second-level enumeration
        friendly_name = dd.DeviceString or device_name
        mon_dd = DISPLAY_DEVICEW()
        mon_dd.cb = ctypes.sizeof(DISPLAY_DEVICEW)
        if user32.EnumDisplayDevicesW(device_name, 0, ctypes.byref(mon_dd), 0):
            if mon_dd.DeviceString:
                friendly_name = mon_dd.DeviceString

        # Current settings
        cur = DEVMODEW()
        cur.dmSize = ctypes.sizeof(DEVMODEW)
        if not user32.EnumDisplaySettingsW(device_name, ENUM_CURRENT_SETTINGS, ctypes.byref(cur)):
            log.warning(f"Could not read current settings for {device_name}")
            continue

        # DPI / scale
        hmonitor = hmon_map.get(device_name.lower())
        dpi_x, dpi_y = _get_dpi_for_monitor(hmonitor) if hmonitor else (96, 96)
        scale = round((dpi_x / 96.0) * 100)

        # HDR: basic check via WMI (Win32_VideoController AdvancedColorSupported is not directly available;
        # we use a registry hint or default to False — proper HDR detection requires DXGI which needs a compiled DLL)
        hdr = _check_hdr_registry(device_name)

        supported_modes = _enum_supported_modes(device_name)

        monitors.append(MonitorInfo(
            device_name=device_name,
            friendly_name=friendly_name,
            monitor_id=mon_dd.DeviceID or device_name,
            is_primary=is_primary,
            current_width=cur.dmPelsWidth,
            current_height=cur.dmPelsHeight,
            current_refresh_rate=cur.dmDisplayFrequency,
            current_bpp=cur.dmBitsPerPel,
            hdr_supported=hdr,
            dpi_x=dpi_x,
            dpi_y=dpi_y,
            scale_factor=scale,
            supported_modes=supported_modes,
        ))

    return monitors


def _check_hdr_registry(device_name: str) -> bool:
    """
    Best-effort HDR detection via Windows registry.
    Returns True if HDR appears enabled for any display path.
    """
    try:
        import winreg
        key_path = r"SYSTEM\CurrentControlSet\Control\GraphicsDrivers\SceneChangeDetect"
        # Simpler approach: check DisplayHDRStatus via Win32 API hint
        # For a real check, use IDXGIOutput6::GetDesc1 — that requires a native DLL.
        # We'll check if Windows Color Space hint key exists as a proxy.
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r"SOFTWARE\Microsoft\Windows\CurrentVersion\VideoSettings") as k:
            val, _ = winreg.QueryValueEx(k, "EnableHDRForPlayback")
            return bool(val)
    except Exception:
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def get_hardware_snapshot() -> HardwareSnapshot:
    """Collect GPU, CPU, and monitor data. Returns a HardwareSnapshot."""
    log.info("Collecting hardware snapshot...")
    gpus = _detect_gpus()
    cpu = _detect_cpu()
    monitors = _detect_monitors()
    log.info(f"Detected {len(gpus)} GPU(s), {len(monitors)} monitor(s).")
    return HardwareSnapshot(gpus=gpus, cpu=cpu, monitors=monitors)


def snapshot_to_dict(snapshot: HardwareSnapshot) -> dict:
    """Convert HardwareSnapshot to a plain serialisable dict."""
    return asdict(snapshot)


# ─────────────────────────────────────────────────────────────────────────────
# Quick self-test when run directly
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import json
    snap = get_hardware_snapshot()
    data = snapshot_to_dict(snap)

    print("\n=== GPU(s) ===")
    for g in data["gpus"]:
        print(f"  {g['name']}  |  VRAM: {g['vram_mb']} MB  |  Vendor: {g['vendor']}  |  Driver: {g['driver_version']}")

    print("\n=== CPU ===")
    if data["cpu"]:
        c = data["cpu"]
        print(f"  {c['name']}  |  Cores: {c['cores']}  |  Logical: {c['logical_processors']}")
    else:
        print("  Not detected")

    print("\n=== Monitors ===")
    for m in data["monitors"]:
        top3 = [f"{md['width']}x{md['height']}@{md['refresh_rate']}" for md in m['supported_modes'][:3]]
        print(
            f"  [{m['device_name']}] {m['friendly_name']}\n"
            f"    Current:  {m['current_width']}x{m['current_height']} @ {m['current_refresh_rate']} Hz  {m['current_bpp']} bpp\n"
            f"    DPI:      {m['dpi_x']} x {m['dpi_y']}  (scale {m['scale_factor']}%)\n"
            f"    Primary:  {m['is_primary']}   HDR: {m['hdr_supported']}\n"
            f"    Modes:    {len(m['supported_modes'])} supported  (top 3: {top3})"
        )
