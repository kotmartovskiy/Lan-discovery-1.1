# -*- coding: utf-8 -*-
"""Тесты core/samba_guest.py — чистые функции transform/_state."""
import re

from core.samba_guest import transform, _state, MANAGED_PREFIX

SAMPLE = """[global]
   workgroup = WORKGROUP
   server role = standalone server
   log file = /var/log/samba/log.%m

[printers]
   path = /var/tmp
   printable = yes
   guest ok = no

[downloads]
    path = /srv/downloads
    browseable = yes
    read only = no
    valid users = kot
    force user = kot
    create mask = 0664

[share]
    path = /srv/share
    read only = no
    valid users = kot
    force user = kot
"""

# Результат ON: в [global] добавлен map to guest (при выключении остаётся)
SAMPLE_WITH_MAP = SAMPLE.replace(
    "[global]\n",
    "[global]\n    map to guest = bad user\n",
    1,
)


def test_state_before_enable():
    st = _state(SAMPLE)
    assert st["enabled"] is False
    assert set(st["shares"]) == {"downloads", "share"}
    assert "printers" not in st["shares"]
    for share in st["shares"].values():
        assert share["guest_ok"] is False
        assert share["restricted"] is True
        assert share["enabled"] is False


def test_enable_adds_guest_ok_and_comments_valid_users():
    out = transform(SAMPLE, True)
    assert out.count("    guest ok = yes") == 2
    assert out.count(MANAGED_PREFIX + "    valid users = kot") == 2
    assert not re.search(r"^\s*valid users", out, re.M)
    assert "    map to guest = bad user" in out
    st = _state(out)
    assert st["enabled"] is True
    assert all(s["enabled"] for s in st["shares"].values())


def test_enable_is_idempotent():
    once = transform(SAMPLE, True)
    twice = transform(once, True)
    assert once == twice


def test_enable_does_not_touch_printers_or_global():
    out = transform(SAMPLE, True)
    printers = out[out.index("[printers]"):out.index("[downloads]")]
    assert "guest ok = no" in printers
    assert MANAGED_PREFIX not in printers
    global_sec = out[out.index("[global]"):out.index("[printers]")]
    assert "valid users" not in global_sec


def test_disable_on_untouched_config_is_noop():
    assert transform(SAMPLE, False) == SAMPLE


def test_disable_restores_config():
    out = transform(transform(SAMPLE, True), False)
    assert out == SAMPLE_WITH_MAP
    st = _state(out)
    assert st["enabled"] is False
    for share in st["shares"].values():
        assert share["restricted"] is True
        assert share["guest_ok"] is False


def test_disable_is_idempotent():
    on = transform(SAMPLE, True)
    off1 = transform(on, False)
    off2 = transform(off1, False)
    assert off1 == off2


def test_enable_twice_then_disable_once():
    out = transform(transform(SAMPLE, True), True)
    assert transform(out, False) == SAMPLE_WITH_MAP


def test_state_without_file_shares():
    text = "[global]\n    workgroup = WORKGROUP\n"
    st = _state(text)
    assert st["enabled"] is False
    assert st["shares"] == {}
