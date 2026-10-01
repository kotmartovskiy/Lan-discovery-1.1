# -*- coding: utf-8 -*-
"""Roles layer (STEP 9): конфиг-профили поверх modules, без изменения loader.

Роль = именованный набор модулей под сценарий использования устройства.
Профили описаны в PROFILES (код), выбор активной роли и состояние —
в /etc/lan-discovery/roles.json. Совместимость модуля роли с системой
проверяется через core.module_loader.compute_status (compat-check).

API (modules/module_manager.py):
    GET  /api/roles            — профили + статусы модулей (compat-check)
    POST /api/roles/<rid>/apply — применить профиль (вкл/выкл модулей)
"""
import json
import os

from core.module_loader import (
    discover_modules,
    module_status,
    set_module_status,
    status_context,
    compute_status,
    _missing_apt_packages,
)

STATE_PATH = "/etc/lan-discovery/roles.json"

# Модули, которые роль НЕ выключает никогда (доступ к настройкам/пользователям,
# управление питанием/сетью, бэкапы БД — безопасность панели).
ALWAYS_ON = (
    "sys-board", "sys-network", "sys-power",
    "sys-settings", "sys-users", "sys-db",
)

# Предустановленные профили. "modules": "*" — все модули панели.
PROFILES = {
    "default": {
        "name": "Полный",
        "description": "Все модули панели включены (базовый профиль).",
        "modules": "*",
    },
    "media": {
        "name": "Медиацентр",
        "description": "Торренты, DLNA/UPnP, плеер, радио, IPTV, загрузки.",
        "modules": [
            "torrent", "dlna", "player", "radio",
            "downloads", "upnp", "sys-iptv",
        ],
    },
    "network": {
        "name": "Сеть и наблюдение",
        "description": "Инвентаризация, мониторинг, сетевые утилиты, Bluetooth.",
        "modules": [
            "inventory", "monitoring", "nettools",
            "wifianalyzer", "bluetooth", "disks",
        ],
    },
}


def _read_state():
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


def _write_state(state):
    try:
        os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
        with open(STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def active_role():
    """Идентификатор активной роли (дефолт — default)."""
    rid = _read_state().get("active") or "default"
    return rid if rid in PROFILES else "default"


def set_active(rid):
    if rid not in PROFILES:
        return False
    state = _read_state()
    state["active"] = rid
    return _write_state(state)


def role_module_ids(rid):
    """Список id модулей роли; "*" → все существующие модули."""
    p = PROFILES.get(rid)
    if not p:
        return None
    if p["modules"] == "*":
        return [m["id"] for m in discover_modules()]
    known = {m["id"] for m in discover_modules()}
    return [mid for mid in p["modules"] if mid in known]


def _targets(rid):
    """{module_id: enabled_target} для роли (с учётом ALWAYS_ON)."""
    ids = set(role_module_ids(rid) or [])
    out = {}
    for m in discover_modules():
        mid = m["id"]
        out[mid] = (mid in ids) or (mid in ALWAYS_ON)
    return out


def apply_role(rid):
    """Применить профиль: вкл/выкл модулей с compat-check.

    Модули incompatible/requires-hardware не включаются (skipped со
    статусом). Возвращает {enabled, disabled, skipped, active}.
    """
    if rid not in PROFILES:
        return {"ok": False, "error": "unknown role"}
    targets = _targets(rid)
    all_pkgs = []
    for m in discover_modules():
        all_pkgs += ((m.get("deps") or {}).get("apt") or [])
    missing = set(_missing_apt_packages(all_pkgs))
    ctx = status_context()

    enabled, disabled, skipped = [], [], []
    for m in discover_modules():
        mid = m["id"]
        installed_now, current = module_status(mid)
        if not installed_now:
            continue  # не установлен — включать нечего (не ставим сам state)
        status = compute_status(m, {}, ctx, missing)
        want = targets[mid]
        if want and status in ("incompatible", "requires-hardware"):
            skipped.append({"id": mid, "name": m.get("name", mid),
                            "status": status})
            want = False
        if want and not current:
            set_module_status(mid, enabled=True)
            enabled.append(mid)
        elif not want and current:
            set_module_status(mid, enabled=False)
            disabled.append(mid)
    set_active(rid)
    return {"ok": True, "active": rid, "enabled": enabled,
            "disabled": disabled, "skipped": skipped}


def roles_overview():
    """Все профили + compat-check статусы модулей (для /roles и API).

    В каждый профиль входят модули роли + ALWAYS_ON (помечены флагом) —
    ровно то, что реально применяет apply_role().
    """
    all_pkgs = []
    mods_all = discover_modules()
    for m in mods_all:
        all_pkgs += ((m.get("deps") or {}).get("apt") or [])
    missing = set(_missing_apt_packages(all_pkgs))
    ctx = status_context()
    active = active_role()
    out = []
    for rid, p in PROFILES.items():
        base = set(role_module_ids(rid) or [])
        mods = []
        for m in mods_all:
            mid = m["id"]
            always = mid in ALWAYS_ON
            if mid not in base and not always:
                continue
            mods.append({
                "id": mid,
                "name": m.get("name", mid),
                "always_on": always,
                "status": compute_status(m, {}, ctx, missing),
                "enabled": module_status(mid)[1],
            })
        out.append({
            "id": rid,
            "name": p["name"],
            "description": p["description"],
            "modules": mods,
        })
    return {"active": active, "roles": out}
