# -*- coding: utf-8 -*-
"""Capabilities layer (STEP 7): только достоверные данные с reliability-флагами.

Read-only, без зависимостей от app (как core/hardware.py).

Формат capability-записи:
    {"state": "present" | "absent" | "unknown",
     "reliability": "measured"   -- значение прочитано из источника
                  | "detected"    -- наличие/отсутствие определено проверкой
                  | "unverified", -- источник недоступен/не подтверждён
     "value": <дополнительно, только если есть проверенное значение>}

Ничего не угадывается: если проверить не удалось — state=unknown,
reliability=unverified; отсутствие фиксируется только после неудачного
поиска (перебор sysfs / shutil.which).
"""
import platform as _platform
import shutil
import socket
import time

from core.hardware import (
    emmc_device,
    hdd_device,
    sd_device,
    thermal_temp,
    thermal_zone_path,
)

# Единый источник проб внешних бинарей.
# app.py импортирует этот кортеж как CAPABILITY_PROBES (probe для /api/health).
TOOL_PROBES = (
    "nmap", "ping", "tracepath", "host", "iw",
    "bluetoothctl", "smartctl", "ffmpeg", "mpv", "lsblk",
)

VALID_STATES = ("present", "absent", "unknown")
VALID_RELIABILITY = ("measured", "detected", "unverified")

_TTL = 30
_TOOLS_TTL = 300
_cache = {"data": None, "ts": 0}
_tools_cache = {"data": None, "ts": 0}


def _cap(state, reliability, value=None):
    d = {"state": state, "reliability": reliability}
    if value is not None:
        d["value"] = value
    return d


def probe_tools():
    """Наличие внешних бинарей в PATH (кэш 300 с)."""
    now = time.time()
    if _tools_cache["data"] is not None and now - _tools_cache["ts"] < _TOOLS_TTL:
        return _tools_cache["data"]
    tools = {}
    for name in TOOL_PROBES:
        try:
            found = shutil.which(name) is not None
        except Exception:
            found = None
        if found is None:
            tools[name] = _cap("unknown", "unverified")
        else:
            tools[name] = _cap("present" if found else "absent", "detected")
    _tools_cache["data"] = tools
    _tools_cache["ts"] = now
    return tools


def _storage(fn):
    """Хранилище из core.hardware: имя устройства или отсутствие."""
    try:
        dev = fn()
    except Exception:
        return _cap("unknown", "unverified")
    if dev:
        return _cap("present", "detected", value=dev)
    return _cap("absent", "detected")


def _board():
    """Модель платы: /proc/device-tree/model = measured; иначе hostname — unverified."""
    base = {"arch": _platform.machine(), "system": _platform.system()}
    try:
        with open("/proc/device-tree/model", "rb") as f:
            m = f.read().replace(b"\x00", b"").decode("utf-8", "replace").strip()
        if m:
            return dict(base, model=m, reliability="measured")
    except Exception:
        pass
    try:
        return dict(base, model=socket.gethostname(), reliability="unverified")
    except Exception:
        return dict(base, model=None, reliability="unverified")


def _thermal():
    """Термозона + температура: measured если значение прочитано."""
    try:
        zone = thermal_zone_path()
    except Exception:
        return _cap("unknown", "unverified")
    if not zone:
        return _cap("absent", "detected")
    try:
        temp = thermal_temp()
    except Exception:
        temp = None
    if temp is None:
        return _cap("unknown", "unverified", value=zone)
    return _cap("present", "measured", value=temp)


def collect():
    """Агрегат всех capabilities (кэш 30 с)."""
    now = time.time()
    if _cache["data"] is not None and now - _cache["ts"] < _TTL:
        return _cache["data"]
    data = {
        "board": _board(),
        "storage": {
            "emmc": _storage(emmc_device),
            "sd": _storage(sd_device),
            "hdd": _storage(hdd_device),
        },
        "thermal": _thermal(),
        "tools": probe_tools(),
        "checked_at": time.strftime("%d.%m.%Y %H:%M:%S"),
    }
    _cache["data"] = data
    _cache["ts"] = now
    return data
