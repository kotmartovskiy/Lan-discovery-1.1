# -*- coding: utf-8 -*-
"""Unit: capabilities layer (STEP 7) — только достоверные + reliability."""
import time

import pytest

import app
import modules.auth as auth
from core.capabilities import (
    TOOL_PROBES,
    VALID_RELIABILITY,
    VALID_STATES,
    _cap,
    collect,
    probe_tools,
)


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


def _check_cap(c, where):
    assert c["state"] in VALID_STATES, (where, c)
    assert c["reliability"] in VALID_RELIABILITY, (where, c)
    if c["state"] == "unknown":
        assert c["reliability"] == "unverified", (where, c)


def test_collect_shape_and_reliability():
    d = collect()
    for key in ("board", "storage", "thermal", "tools", "checked_at"):
        assert key in d, key
    assert d["board"]["reliability"] in VALID_RELIABILITY
    assert d["board"]["model"] is None or isinstance(d["board"]["model"], str)
    for key in ("emmc", "sd", "hdd"):
        _check_cap(d["storage"][key], "storage." + key)
    _check_cap(d["thermal"], "thermal")
    for name in TOOL_PROBES:
        assert name in d["tools"], name
        _check_cap(d["tools"][name], "tools." + name)


def test_probe_tools_covers_all_probes():
    tools = probe_tools()
    assert set(tools) == set(TOOL_PROBES)


def test_cap_helper():
    assert _cap("absent", "detected") == {
        "state": "absent", "reliability": "detected"}
    c = _cap("present", "measured", value=52.0)
    assert c["value"] == 52.0
    assert "value" not in _cap("unknown", "unverified")


def test_api_capabilities_shape(client):
    r = client.get("/api/capabilities")
    assert r.status_code == 200
    d = r.get_json()
    for key in ("board", "storage", "thermal", "tools", "checked_at"):
        assert key in d, key
    _check_cap(d["storage"]["emmc"], "api.storage.emmc")
    _check_cap(d["thermal"], "api.thermal")


def test_capabilities_page_renders(client):
    r = client.get("/capabilities")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "Возможности системы" in html
    assert "/api/capabilities" in html
    # semantic-состояние хотя бы одно (present/absent/unknown покрытие полное)
    assert ("status-ok" in html) or ('class="na"' in html) \
        or ("status-unknown" in html)


def test_app_probes_single_source():
    """app.CAPABILITY_PROBES — алиас core.capabilities.TOOL_PROBES."""
    assert app.CAPABILITY_PROBES is TOOL_PROBES
