# -*- coding: utf-8 -*-
"""Event engine (PHASE 7): формализованные события, единая точка записи/чтения.

Схема events v2 (см. modules/devices_routes.init_db_schema): колонки
`severity` (info/warning/critical), `source` (discovery/system/monitoring/
user), `metadata` (JSON-текст).

Фабрика `add_event` — единственная точка INSERT: тип события неизвестный
получает severity=info; известные — из `EVENT_SEVERITY`.
"""
import json
from datetime import datetime

EVENT_SEVERITY = {
    "NEW": "info",
    "ONLINE": "info",
    "OFFLINE": "warning",
    "MAC_CHANGED": "warning",
}
DEFAULT_SEVERITY = "info"
SEVERITIES = ("info", "warning", "critical")


def now_ts():
    return datetime.now().strftime("%d.%m.%Y %H:%M:%S")


def add_event(con, ip, hostname=None, mac=None, event="INFO",
              source="discovery", metadata=None, severity=None,
              timestamp=None):
    """Вставить событие; возвращает фактическую severity."""
    if severity not in SEVERITIES:
        severity = EVENT_SEVERITY.get(event, DEFAULT_SEVERITY)
    meta = json.dumps(metadata, ensure_ascii=False) if metadata else None
    con.execute(
        """
        INSERT INTO events
        (timestamp, ip, hostname, mac, event, severity, source, metadata)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (timestamp or now_ts(), ip, hostname, mac, event, severity,
         source, meta),
    )
    return severity


def list_events(con, limit=500, event=None, severity=None, ip=None,
                source=None):
    """SELECT событий с фильтрами; новые первыми."""
    q = ("SELECT id, timestamp, ip, hostname, mac, event, severity, source, "
         "metadata FROM events WHERE 1=1")
    params = []
    if event:
        q += " AND event=?"
        params.append(event)
    if severity:
        q += " AND severity=?"
        params.append(severity)
    if ip:
        q += " AND ip=?"
        params.append(ip)
    if source:
        q += " AND source=?"
        params.append(source)
    q += " ORDER BY id DESC LIMIT ?"
    params.append(max(1, int(limit)))
    return con.execute(q, params).fetchall()


def event_to_dict(row):
    """Строка list_events -> dict (metadata парсится из JSON)."""
    meta = row[8]
    if meta:
        try:
            meta = json.loads(meta)
        except Exception:
            pass
    return {
        "id": row[0],
        "timestamp": row[1],
        "ip": row[2],
        "hostname": row[3],
        "mac": row[4],
        "event": row[5],
        "severity": row[6],
        "source": row[7],
        "metadata": meta,
    }
