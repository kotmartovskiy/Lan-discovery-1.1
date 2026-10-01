# -*- coding: utf-8 -*-
"""Unit: roles layer (STEP 9) — профили модулей, apply, API /api/roles."""
import time

import pytest

import app
import core.roles as roles
import modules.auth as auth
from core.module_loader import MODULE_STATUSES, discover_modules, nav_groups


@pytest.fixture()
def client(monkeypatch):
    app.app.config["TESTING"] = True
    old = app.app.config["WTF_CSRF_ENABLED"]
    app.app.config["WTF_CSRF_ENABLED"] = False
    monkeypatch.setattr(
        auth, "load_users",
        lambda: {"admin": {"enabled": True, "role": "admin"}},
    )
    c = app.app.test_client()
    with c.session_transaction() as s:
        s["user"] = "admin"
        s["login_ts"] = time.time()
    yield c
    app.app.config["WTF_CSRF_ENABLED"] = old


def test_profiles_reference_real_modules():
    known = {m["id"] for m in discover_modules()}
    for rid, p in roles.PROFILES.items():
        if p["modules"] == "*":
            continue
        for mid in p["modules"]:
            assert mid in known, "роль %s ссылается на неизвестный %s" % (rid, mid)


def test_always_on_in_every_profile():
    for rid in roles.PROFILES:
        targets = roles._targets(rid)
        for mid in roles.ALWAYS_ON:
            if mid in targets:
                assert targets[mid] is True, "%s выключает %s" % (rid, mid)


def test_active_role_fallback(monkeypatch):
    monkeypatch.setattr(roles, "_read_state", lambda: {"active": "nope"})
    assert roles.active_role() == "default"
    monkeypatch.setattr(roles, "_read_state", lambda: {"active": "media"})
    assert roles.active_role() == "media"
    assert roles.set_active("nope") is False


def test_role_module_ids():
    assert set(roles.role_module_ids("default")) == {
        m["id"] for m in discover_modules()}
    media = roles.role_module_ids("media")
    assert "torrent" in media and "notes" not in media
    assert roles.role_module_ids("nope") is None


def _patch_apply_env(monkeypatch, status_fn):
    """Изолировать apply_role от /etc и системы."""
    monkeypatch.setattr(roles, "module_status", lambda mid: (True, True))
    monkeypatch.setattr(roles, "set_module_status",
                        lambda mid, installed=None, enabled=None: None)
    monkeypatch.setattr(roles, "set_active", lambda rid: True)
    monkeypatch.setattr(roles, "compute_status", status_fn)
    monkeypatch.setattr(roles, "_missing_apt_packages", lambda p: [])
    monkeypatch.setattr(roles, "status_context",
                        lambda: {"arch": "aarch64", "caps": {}})


def test_apply_role(monkeypatch):
    known = [m["id"] for m in discover_modules()]
    st = {mid: [True, True] for mid in known}
    st["torrent"] = [True, False]    # модуль роли выключен
    st["camera"] = [False, False]    # не установлен
    calls, acts = [], []

    monkeypatch.setattr(roles, "module_status",
                        lambda mid: (st[mid][0], st[mid][1]))

    def fake_set(mid, installed=None, enabled=None):
        calls.append((mid, enabled))
        if installed is not None:
            st[mid][0] = installed
        if enabled is not None:
            st[mid][1] = enabled

    monkeypatch.setattr(roles, "set_module_status", fake_set)
    monkeypatch.setattr(roles, "set_active", lambda rid: acts.append(rid) or True)
    monkeypatch.setattr(roles, "compute_status",
                        lambda m, e, c, mp=None: "active")
    monkeypatch.setattr(roles, "_missing_apt_packages", lambda p: [])
    monkeypatch.setattr(roles, "status_context",
                        lambda: {"arch": "aarch64", "caps": {}})

    res = roles.apply_role("media")
    assert res["ok"] and res["active"] == "media"
    assert acts == ["media"]
    assert "torrent" in res["enabled"]            # был выкл → включён
    assert "notes" in res["disabled"]             # вне роли → выключен
    assert "sys-settings" not in res["disabled"]  # ALWAYS_ON защищён
    assert "camera" not in [c[0] for c in calls]  # не установлен → не тронут
    assert res["skipped"] == []
    assert st["torrent"][1] is True


def test_apply_role_skips_hardware(monkeypatch):
    def status_fn(m, e, c, mp=None):
        if m.get("id") == "wifianalyzer":
            return "requires-hardware"
        return "active"

    _patch_apply_env(monkeypatch, status_fn)
    res = roles.apply_role("network")
    skipped = [s["id"] for s in res["skipped"]]
    assert "wifianalyzer" in skipped
    assert res["skipped"][0]["status"] == "requires-hardware"
    assert "wifianalyzer" not in res["enabled"]


def test_apply_unknown_role():
    assert roles.apply_role("nope")["ok"] is False


def test_roles_overview_shape():
    ov = roles.roles_overview()
    assert ov["active"] in roles.PROFILES
    assert [r["id"] for r in ov["roles"]] == list(roles.PROFILES.keys())
    for r in ov["roles"]:
        mids = {m["id"] for m in r["modules"]}
        for mid in roles.ALWAYS_ON:
            assert mid in mids, "%s без %s" % (r["id"], mid)
        for m in r["modules"]:
            assert m["status"] in MODULE_STATUSES
            assert isinstance(m["always_on"], bool)
            assert isinstance(m["enabled"], bool)


def test_api_roles(client):
    r = client.get("/api/roles")
    assert r.status_code == 200
    d = r.get_json()
    assert "active" in d
    assert len(d["roles"]) == len(roles.PROFILES)


def test_roles_page(client):
    r = client.get("/roles")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "Роли" in html
    assert "/roles/media/apply" in html
    assert ("Применить" in html) or ("Переприменить" in html)


def test_api_apply_unknown_role_json(client):
    r = client.post("/api/roles/nope/apply")
    assert r.status_code == 200
    assert r.get_json()["ok"] is False


def test_nav_roles_admin_only():
    admin_urls = {e["url"] for g in nav_groups(True) for e in g["entries"]}
    user_urls = {e["url"] for g in nav_groups(False) for e in g["entries"]}
    assert "/roles" in admin_urls
    assert "/roles" not in user_urls
