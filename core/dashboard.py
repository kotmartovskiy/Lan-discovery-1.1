# -*- coding: utf-8 -*-
"""Dashboard-агрегат (STEP 4): merge alerts поверх health + событий.

alerts — read-only вьюха (новая таблица БД НЕ создаётся): предупреждения
`/api/system/health` + события severity warning/critical из events.
"""
SEV = ("warning", "critical")


def merge_alerts(warnings, events, limit=12):
    """[{level,icon,text,source,time,ip}] из health-warnings + событий.

    Сначала health (живые проблемы хоста), затем события (новые первыми,
    т.к. list_events отдаёт DESC). Вне SEV — отбрасывается, обрезка — limit.
    """
    out = []
    for w in warnings or []:
        level = w.get("level")
        if level not in SEV:
            level = "warning"
        out.append({
            "level": level,
            "icon": w.get("icon") or "⚠️",
            "text": w.get("text") or "",
            "source": "health",
            "time": None,
            "ip": None,
        })
    for e in events or []:
        if (e.get("severity") or "") not in SEV:
            continue
        ip = e.get("ip") or ""
        text = e.get("event") or ""
        if ip:
            text = "%s (%s)" % (text, ip)
        out.append({
            "level": e.get("severity"),
            "icon": "📌",
            "text": text,
            "source": "event",
            "time": e.get("timestamp"),
            "ip": ip or None,
        })
    return out[:limit]
