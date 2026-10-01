# -*- coding: utf-8 -*-
"""Unit: dashboard-агрегат (STEP 4) — merge_alerts + GET /api/dashboard."""
import time

import pytest

import app
import modules.auth as auth
from core.dashboard import merge_alerts


@pytest.fixture()
def client(monkeypatch):
    app.app.config["TESTING"] = True
    monkeypatch.setattr(
        auth, "load_users",
        lambda: {"admin": {"enabled": True, "role": "admin"}},
    )
    c = app.app.test_client()
    with c.session_transaction() as s:
        s["user"] = "admin"
        s["login_ts"] = time.time()
    yield c


def _ev(severity, event="ONLINE", ip="192.168.3.10"):
    return {"severity": severity, "event": event, "ip": ip,
            "timestamp": 1770000000}


def test_merge_alerts_health_first_then_events():
    warns = [{"level": "critical", "text": "CPU перегрев: 85.0°C", "icon": "🔥"}]
    out = merge_alerts(warns, [_ev("info"), _ev("warning", "OFFLINE"),
                               _ev("critical", "PANIC")])
    assert [a["level"] for a in out] == ["critical", "warning", "critical"]
    assert [a["source"] for a in out] == ["health", "event", "event"]
    assert out[1]["text"] == "OFFLINE (192.168.3.10)"
    assert out[0]["source"] == "health" and out[0]["time"] is None


def test_merge_alerts_skips_info_and_limits():
    out = merge_alerts(None, [_ev("info")] * 3)
    assert out == []
    out = merge_alerts([], [_ev("warning")] * 20, limit=5)
    assert len(out) == 5


def test_merge_alerts_unknown_level_becomes_warning():
    out = merge_alerts([{"level": "notice", "text": "x"}], [])
    assert out[0]["level"] == "warning"


def test_dashboard_endpoint_shape(client):
    r = client.get("/api/dashboard")
    assert r.status_code == 200
    d = r.get_json()
    for key in ("system", "health", "devices", "events", "alerts",
                "internet", "checked_at"):
        assert key in d, key
    assert "services" in d["system"]
    assert "ok" in d["health"] and isinstance(d["health"]["warnings"], list)
    assert isinstance(d["devices"]["total"], int)
    assert isinstance(d["devices"]["online"], int)
    assert isinstance(d["events"], list)
    assert isinstance(d["alerts"], list)
    assert d["internet"] is None or isinstance(d["internet"], bool)


def test_api_status_still_available(client):
    """Регресс: /api/status не удалён (STEP 4 только агрегирует)."""
    r = client.get("/api/status")
    assert r.status_code == 200
    assert "services" in r.get_json()
