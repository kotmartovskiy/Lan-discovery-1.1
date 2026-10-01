# -*- coding: utf-8 -*-
"""Unit: residual UI (№65) — eMMC/clone/HDD блоки на узле без HDD/SD-boot.

На X96 (boot с SD, без HDD): кнопки eMMC-бэкапа disabled с причиной,
строка HDD в блоке «Плата» не рендерится, backup-test защищён guard'ом.
"""
import time

import pytest

import app
import modules.auth as auth
import modules.system_routes as sysroutes


@pytest.fixture()
def client(monkeypatch):
    app.app.config["TESTING"] = True
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
    app.app.config["WTF_CSRF_ENABLED"] = True


def test_emmc_buttons_disabled_when_not_allowed(client, monkeypatch):
    monkeypatch.setattr(
        sysroutes, "emmc_backup_guard",
        lambda: (False, "система загружена с SD-карты (тест)"),
    )
    html = client.get("/system").get_data(as_text=True)
    assert "btn-backup-create" in html
    assert 'id="btn-backup-create" type="button" onclick="startBackup()" disabled' \
        in html
    assert 'id="btn-emmc-restore" type="button" onclick="startEmmcRestore()" disabled' \
        in html
    assert 'title="система загружена с SD-карты (тест)"' in html


def test_emmc_buttons_enabled_when_allowed(client, monkeypatch):
    monkeypatch.setattr(
        sysroutes, "emmc_backup_guard", lambda: (True, ""),
    )
    html = client.get("/system").get_data(as_text=True)
    assert 'onclick="startBackup()"' in html
    assert 'onclick="startBackup()" disabled' not in html


def test_hdd_row_hidden_when_no_hdd(client, monkeypatch):
    """X96: hdd_device() → None → строка HDD в sys-board не рендерится."""
    monkeypatch.setattr(sysroutes, "hdd_device", lambda: None)
    html = client.get("/system").get_data(as_text=True)
    assert 'id="pi-hdd"' not in html
    assert 'id="pi-emmc"' in html  # eMMC-строка остаётся


def test_hdd_row_present_when_hdd_exists(client, monkeypatch):
    monkeypatch.setattr(sysroutes, "hdd_device", lambda: "sda")
    html = client.get("/system").get_data(as_text=True)
    assert 'id="pi-hdd"' in html


def test_backup_test_route_guarded(client, monkeypatch):
    """POST /system/backup-test без разрешения — 409, не запускает zstd."""
    monkeypatch.setattr(
        sysroutes, "emmc_backup_guard",
        lambda: (False, "HDD не подключен"),
    )
    r = client.post("/system/backup-test")
    assert r.status_code == 409
    assert r.get_json()["reason"] == "HDD не подключен"
