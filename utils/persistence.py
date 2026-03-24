"""
Persistence Layer
Read/write user settings and event log.  No Windows APIs — fully portable.

Files
-----
config/user_settings.json   — merged user overrides on top of defaults
config/event_log.jsonl      — newline-delimited JSON, one entry per line
config/reset_history.jsonl  — subset of events; only reset/apply operations
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from utils.logger import setup_logger
from utils.paths import bundle_dir, data_dir

log = setup_logger("lumynex.persistence")

# ── Paths ──────────────────────────────────────────────────────────────────

_DEFAULTS_FILE = bundle_dir() / "config" / "defaults.json"
_CONFIG_DIR    = data_dir()   / "config"
_SETTINGS_FILE = _CONFIG_DIR / "user_settings.json"
_EVENT_LOG     = _CONFIG_DIR / "event_log.jsonl"
_RESET_HISTORY = _CONFIG_DIR / "reset_history.jsonl"

# Maximum lines kept in the in-memory event cache (for the log viewer widget)
_EVENT_CACHE_MAX = 500

# ── Module-level state ────────────────────────────────────────────────────

_lock          = threading.Lock()          # guards all file I/O
_event_cache: List[Dict] = []              # in-memory ring buffer


# ── Internal helpers ──────────────────────────────────────────────────────

def _read_json(path: Path, fallback: Any = None) -> Any:
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        log.debug("File not found: %s — using fallback", path)
        return fallback
    except json.JSONDecodeError as exc:
        log.warning("Corrupt JSON in %s: %s — using fallback", path, exc)
        return fallback


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    try:
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
        tmp.replace(path)   # atomic on same filesystem
    except Exception as exc:
        log.error("Failed to write %s: %s", path, exc)
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        raise


def _append_jsonl(path: Path, entry: Dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as exc:
        log.error("Failed to append to %s: %s", path, exc)


def _read_jsonl(path: Path, limit: int = 0) -> List[Dict]:
    if not path.exists():
        return []
    entries: List[Dict] = []
    try:
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass   # skip corrupt line
    except Exception as exc:
        log.warning("Failed to read %s: %s", path, exc)
    if limit > 0:
        return entries[-limit:]
    return entries


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


# ── Settings ──────────────────────────────────────────────────────────────

def load_settings() -> Dict:
    """
    Return merged settings: defaults.json overridden by user_settings.json.
    Always returns a dict; never raises.
    """
    with _lock:
        defaults = _read_json(_DEFAULTS_FILE, fallback={})
        user     = _read_json(_SETTINGS_FILE, fallback={})

    # Deep-merge: user values win at every key level
    merged = _deep_merge(defaults, user)
    log.debug("Settings loaded (user keys: %d)", len(user))
    return merged


def save_settings(data: Dict) -> None:
    """
    Persist *data* to user_settings.json.
    Only writes keys that differ from defaults so the file stays minimal.
    Raises on I/O error.
    """
    with _lock:
        defaults = _read_json(_DEFAULTS_FILE, fallback={})
        diff = _diff_from_defaults(defaults, data)
        _write_json(_SETTINGS_FILE, diff)
    log.info("Settings saved (%d keys)", len(diff))


def get_setting(key: str, default: Any = None) -> Any:
    """Convenience: load settings and return a single top-level key."""
    return load_settings().get(key, default)


def set_setting(key: str, value: Any) -> None:
    """Convenience: load, update one key, save."""
    settings = load_settings()
    settings[key] = value
    save_settings(settings)


# ── Monitor-keyed preferences ──────────────────────────────────────────────

def get_monitor_pref(monitor_id: str, key: str, default: Any = None) -> Any:
    """
    Return a stored preference for a specific monitor.
    monitor_id is the raw device name e.g. r"\\\\.\\DISPLAY6".
    """
    settings = load_settings()
    monitors = settings.get("monitors", {})
    return monitors.get(monitor_id, {}).get(key, default)


def set_monitor_pref(monitor_id: str, key: str, value: Any) -> None:
    """Persist a preference keyed by monitor_id + key."""
    settings = load_settings()
    monitors = settings.setdefault("monitors", {})
    monitors.setdefault(monitor_id, {})[key] = value
    save_settings(settings)


# ── Event log ──────────────────────────────────────────────────────────────

# Valid event types (open set — others accepted but warned)
EventType = str   # "INFO" | "WARNING" | "ERROR" | "APPLY" | "RESET" | "ROLLBACK"


def log_event(
    event_type: EventType,
    detail: str,
    monitor_id: Optional[str] = None,
    extra: Optional[Dict] = None,
) -> None:
    """
    Append one entry to event_log.jsonl and optionally reset_history.jsonl.
    Thread-safe.

    Parameters
    ----------
    event_type : str    "INFO" | "WARNING" | "ERROR" | "APPLY" | "RESET" | "ROLLBACK"
    detail     : str    Human-readable description
    monitor_id : str    Device name, if relevant
    extra      : dict   Additional structured data (optional)
    """
    entry: Dict = {
        "ts":   _now_iso(),
        "type": event_type.upper(),
        "msg":  detail,
    }
    if monitor_id:
        entry["monitor"] = monitor_id
    if extra:
        entry["extra"] = extra

    with _lock:
        _append_jsonl(_EVENT_LOG, entry)
        # Also mirror reset/apply/rollback to the shorter reset history file
        if entry["type"] in ("APPLY", "RESET", "ROLLBACK"):
            _append_jsonl(_RESET_HISTORY, entry)

    # Update in-memory cache
    global _event_cache
    _event_cache.append(entry)
    if len(_event_cache) > _EVENT_CACHE_MAX:
        _event_cache = _event_cache[-_EVENT_CACHE_MAX:]

    log.debug("[event] %s: %s", event_type, detail)


def get_event_log(limit: int = 200) -> List[Dict]:
    """
    Return the last *limit* event log entries (newest last).
    Reads from in-memory cache if warm, otherwise from disk.
    """
    if _event_cache:
        return _event_cache[-limit:]
    with _lock:
        return _read_jsonl(_EVENT_LOG, limit=limit)


def get_reset_history(limit: int = 50) -> List[Dict]:
    """Return the last *limit* APPLY / RESET / ROLLBACK entries."""
    with _lock:
        return _read_jsonl(_RESET_HISTORY, limit=limit)


def clear_event_log() -> None:
    """Delete event_log.jsonl and flush the in-memory cache."""
    global _event_cache
    with _lock:
        if _EVENT_LOG.exists():
            _EVENT_LOG.unlink()
        _event_cache = []
    log.info("Event log cleared")


# ── Deep-merge helpers ────────────────────────────────────────────────────

def _deep_merge(base: Dict, override: Dict) -> Dict:
    """Recursively merge *override* into *base*, returning a new dict."""
    result = dict(base)
    for key, val in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = _deep_merge(result[key], val)
        else:
            result[key] = val
    return result


def _diff_from_defaults(defaults: Dict, data: Dict) -> Dict:
    """
    Return only the keys in *data* that differ from *defaults*.
    Handles nested dicts recursively.
    This keeps user_settings.json minimal and readable.
    """
    diff: Dict = {}
    for key, val in data.items():
        if key not in defaults:
            diff[key] = val
        elif isinstance(val, dict) and isinstance(defaults[key], dict):
            sub = _diff_from_defaults(defaults[key], val)
            if sub:
                diff[key] = sub
        elif val != defaults[key]:
            diff[key] = val
    return diff


# ── Warm the in-memory cache on first import ──────────────────────────────

def _warm_cache() -> None:
    global _event_cache
    try:
        with _lock:
            _event_cache = _read_jsonl(_EVENT_LOG, limit=_EVENT_CACHE_MAX)
        log.debug("Event cache warmed: %d entries", len(_event_cache))
    except Exception as exc:
        log.warning("Failed to warm event cache: %s", exc)


_warm_cache()


# ── CLI smoke test ────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    print("=== Persistence Layer Smoke Test ===\n")

    # 1. Load defaults
    s = load_settings()
    print(f"[1] load_settings()  -> {len(s)} top-level keys")
    print(f"    auto_apply_on_startup = {s.get('auto_apply_on_startup')}")
    print(f"    notify_on_mismatch    = {s.get('notify_on_mismatch')}")

    # 2. Save a user override
    set_setting("notify_on_mismatch", False)
    s2 = load_settings()
    assert s2["notify_on_mismatch"] is False, "save/load round-trip failed"
    print(f"\n[2] set_setting('notify_on_mismatch', False) -> {s2['notify_on_mismatch']}")

    # Restore
    set_setting("notify_on_mismatch", True)

    # 3. Monitor-keyed pref
    mon = r"\\.\DISPLAY6"
    set_monitor_pref(mon, "user_override_scale", 125)
    pref = get_monitor_pref(mon, "user_override_scale")
    assert pref == 125, f"monitor pref round-trip failed: {pref}"
    print(f"\n[3] set_monitor_pref({mon!r}, 'user_override_scale', 125) -> {pref}")

    # 4. Event log
    log_event("INFO",     "Smoke test started")
    log_event("APPLY",    "Applied 2560x1440@180Hz",  monitor_id=mon)
    log_event("RESET",    "Soft reset completed",      extra={"method": "SetupAPI"})
    log_event("ROLLBACK", "Rollback after CDS_TEST fail")

    events = get_event_log(limit=10)
    print(f"\n[4] get_event_log(10) -> {len(events)} entries")
    for e in events[-4:]:
        print(f"    {e['ts']}  [{e['type']:8s}]  {e['msg']}")

    history = get_reset_history()
    print(f"\n[5] get_reset_history() -> {len(history)} entries (APPLY/RESET/ROLLBACK only)")
    for h in history:
        print(f"    {h['ts']}  [{h['type']:8s}]  {h['msg']}")

    print("\n=== All checks passed ===")
