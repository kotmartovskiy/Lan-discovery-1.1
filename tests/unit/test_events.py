# -*- coding: utf-8 -*-
"""Unit: event engine (PHASE 7 / P5-27)."""
import json
from datetime import datetime, timedelta

from core.events import (EVENT_SEVERITY, add_event, cleanup_old_events,
                         event_to_dict, list_events, now_ts)


def test_now_ts_format():
    datetime.strptime(now_ts(), "%d.%m.%Y %H:%M:%S")


def test_severity_map():
    assert EVENT_SEVERITY["NEW"] == "info"
    assert EVENT_SEVERITY["OFFLINE"] == "warning"
    assert EVENT_SEVERITY["MAC_CHANGED"] == "warning"


def test_add_event_severity_resolution(events_con):
    assert add_event(events_con, "10.0.0.1", event="NEW") == "info"
    assert add_event(events_con, "10.0.0.2", event="OFFLINE") == "warning"
    assert add_event(events_con, "10.0.0.3", event="ANYTHING") == "info"
    assert add_event(events_con, "10.0.0.4", event="NEW",
                     severity="critical") == "critical"
    events_con.commit()


def test_add_event_persists_columns(events_con):
    add_event(events_con, "10.0.0.5", hostname="h1", mac="AA:BB:CC:DD:EE:FF",
              event="NEW", source="discovery", metadata={"x": 1},
              timestamp="01.02.2026 12:00:00")
    events_con.commit()
    row = list_events(events_con, ip="10.0.0.5")[0]
    d = event_to_dict(row)
    assert d["hostname"] == "h1"
    assert d["mac"] == "AA:BB:CC:DD:EE:FF"
    assert d["severity"] == "info"
    assert d["source"] == "discovery"
    assert d["metadata"] == {"x": 1}
    assert d["timestamp"] == "01.02.2026 12:00:00"


def test_list_events_filters(events_con):
    add_event(events_con, "10.0.0.1", event="NEW")
    add_event(events_con, "10.0.0.2", event="OFFLINE")
    add_event(events_con, "10.0.0.2", event="ONLINE", source="user")
    events_con.commit()
    assert len(list_events(events_con)) == 3
    assert len(list_events(events_con, event="OFFLINE")) == 1
    assert len(list_events(events_con, ip="10.0.0.2")) == 2
    assert len(list_events(events_con, severity="warning")) == 1
    assert len(list_events(events_con, source="user")) == 1
    assert len(list_events(events_con, limit=2)) == 2


def test_list_events_order_new_first(events_con):
    add_event(events_con, "10.0.0.1", event="NEW")
    add_event(events_con, "10.0.0.2", event="ONLINE")
    events_con.commit()
    rows = list_events(events_con)
    assert rows[0][2] == "10.0.0.2"


def test_event_to_dict_bad_metadata(events_con):
    add_event(events_con, "10.0.0.9", event="NEW")
    events_con.commit()
    events_con.execute(
        "UPDATE events SET metadata=? WHERE ip=?",
        ("{broken", "10.0.0.9"),
    )
    row = list_events(events_con, ip="10.0.0.9")[0]
    assert event_to_dict(row)["metadata"] == "{broken"


def test_cleanup_removes_old_keeps_fresh(events_con):
    old = (datetime.now() - timedelta(days=400)).strftime("%d.%m.%Y %H:%M:%S")
    fresh = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
    events_con.execute("INSERT INTO events (timestamp, ip, event) VALUES (?,?,?)",
                       (old, "10.0.0.1", "NEW"))
    events_con.execute("INSERT INTO events (timestamp, ip, event) VALUES (?,?,?)",
                       (fresh, "10.0.0.2", "NEW"))
    events_con.commit()
    assert cleanup_old_events(events_con, 180) == 1
    left = [r[0] for r in events_con.execute("SELECT ip FROM events")]
    assert left == ["10.0.0.2"]


def test_cleanup_disabled_and_garbage(events_con):
    old = (datetime.now() - timedelta(days=400)).strftime("%d.%m.%Y %H:%M:%S")
    events_con.execute("INSERT INTO events (timestamp, ip, event) VALUES (?,?,?)",
                       (old, "10.0.0.1", "NEW"))
    events_con.execute("INSERT INTO events (timestamp, ip, event) VALUES (?,?,?)",
                       ("not-a-date", "10.0.0.2", "NEW"))
    events_con.commit()
    assert cleanup_old_events(events_con, 0) == 0
    assert cleanup_old_events(events_con, None) == 0
    n = events_con.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    assert n == 2
    # мусорная дата не роняет чистку и не удаляется
    assert cleanup_old_events(events_con, 180) == 1
    assert events_con.execute(
        "SELECT ip FROM events").fetchone()[0] == "10.0.0.2"


def test_metadata_json_roundtrip(events_con):
    add_event(events_con, "10.0.0.7", event="NEW",
              metadata={"list": [1, 2], "с": "юникод"})
    events_con.commit()
    d = event_to_dict(list_events(events_con, ip="10.0.0.7")[0])
    assert d["metadata"] == {"list": [1, 2], "с": "юникод"}
    raw = events_con.execute("SELECT metadata FROM events").fetchone()[0]
    assert json.loads(raw) == d["metadata"]
