# -*- coding: utf-8 -*-
"""Hardware abstraction (PHASE 3): thermal, storage, platform detection.

Без зависимостей от app/system — безопасно импортируется из любых модулей
(system_routes, monitor) и из standalone-скриптов.
"""
import glob
import os
import platform as _platform
import socket
import time

_thermal_cache = {"path": None, "ts": 0}
_detect_cache = {"data": None, "ts": 0}


def thermal_zone_path():
    """Путь temp первого доступного thermal_zone (перебор, не только zone0).

    Кэшируется на 60 секунд; при недоступности зон — None.
    """
    now = time.time()
    if _thermal_cache["ts"] and now - _thermal_cache["ts"] < 60:
        return _thermal_cache["path"]
    path = None
    try:
        for cand in sorted(glob.glob("/sys/class/thermal/thermal_zone*/temp")):
            try:
                with open(cand, "r", encoding="utf-8") as f:
                    int(f.read().strip())
                path = cand
                break
            except Exception:
                continue
    except Exception:
        path = None
    _thermal_cache["path"] = path
    _thermal_cache["ts"] = now
    return path


def thermal_temp():
    """Температура CPU °C из первого доступного thermal_zone; None если нет."""
    path = thermal_zone_path()
    if not path:
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return round(int(f.read().strip()) / 1000, 1)
    except Exception:
        return None


def hdd_device():
    """Имя первого блочного устройства sd* (HDD/SSD) в /sys/block; None если нет."""
    try:
        for name in sorted(os.listdir("/sys/block")):
            if name.startswith("sd") and len(name) >= 3 and name[2:].isalpha():
                return name
    except Exception:
        pass
    return None


def emmc_device():
    """Имя первого mmcblk* с device/type == 'MMC' (не SD); None если нет."""
    try:
        for name in sorted(os.listdir("/sys/block")):
            if not name.startswith("mmcblk") or "boot" in name:
                continue
            try:
                with open(f"/sys/block/{name}/device/type", "r",
                          encoding="utf-8") as f:
                    if f.read().strip() == "MMC":
                        return name
            except Exception:
                continue
    except Exception:
        pass
    return None


def sd_device():
    """Имя первого mmcblk* с device/type == 'SD'; None если нет."""
    try:
        for name in sorted(os.listdir("/sys/block")):
            if not name.startswith("mmcblk") or "boot" in name:
                continue
            try:
                with open(f"/sys/block/{name}/device/type", "r",
                          encoding="utf-8") as f:
                    if f.read().strip() == "SD":
                        return name
            except Exception:
                continue
    except Exception:
        pass
    return None


def board_model():
    """Полное имя платы из /proc/device-tree/model; fallback — hostname."""
    try:
        with open("/proc/device-tree/model", "rb") as f:
            m = f.read().replace(b"\x00", b"").decode("utf-8", "replace").strip()
        if m:
            return m
    except Exception:
        pass
    return socket.gethostname()


def detect_platform():
    """Кэшированное (60 с) описание платформы для /api/health и UI."""
    now = time.time()
    if _detect_cache["ts"] and now - _detect_cache["ts"] < 60:
        return _detect_cache["data"]
    data = {
        "board": board_model(),
        "arch": _platform.machine(),
        "system": _platform.system(),
        "emmc": emmc_device(),
        "sd": sd_device(),
        "hdd": hdd_device(),
        "thermal_zone": thermal_zone_path(),
    }
    _detect_cache["data"] = data
    _detect_cache["ts"] = now
    return data
