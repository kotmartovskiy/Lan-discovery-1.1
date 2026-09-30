# -*- coding: utf-8 -*-
"""Unit: конфигурация settings (_cfg, load_settings override)."""
import app


def test_cfg_defaults_when_missing(monkeypatch):
    monkeypatch.setattr(app, "load_settings", lambda: {})
    assert app._cfg("web", "flask_port", 8080) == 8080
    assert app._cfg("network", "scan_ifaces") is None
    assert app._cfg("no-such", "key", "fallback") == "fallback"


def test_cfg_reads_section(monkeypatch):
    settings = {"web": {"flask_port": 9090},
                "network": {"scan_ifaces": ["eth0"]},
                "events": {"retention_days": 0}}
    monkeypatch.setattr(app, "load_settings", lambda: settings)
    assert app._cfg("web", "flask_port", 8080) == 9090
    assert app._cfg("network", "scan_ifaces", ["x"]) == ["eth0"]
    assert app._cfg("events", "retention_days", 180) == 0


def test_cfg_missing_key_returns_default(monkeypatch):
    monkeypatch.setattr(app, "load_settings",
                        lambda: {"web": {"flask_host": "127.0.0.1"}})
    assert app._cfg("web", "flask_port", 8080) == 8080


def test_scan_interval_int(monkeypatch):
    monkeypatch.setattr(app, "load_settings",
                        lambda: {"network": {"scan_interval": 45}})
    assert app._scan_interval() == 45
    monkeypatch.setattr(app, "load_settings",
                        lambda: {"network": {"scan_interval": 0}})
    assert app._scan_interval() == 30  # 0 → default
    monkeypatch.setattr(app, "load_settings", lambda: {})
    assert app._scan_interval() == 30


def test_max_misses_int(monkeypatch):
    monkeypatch.setattr(app, "load_settings",
                        lambda: {"network": {"max_misses": 10}})
    assert app._max_misses() == 10
    monkeypatch.setattr(app, "load_settings", lambda: {})
    assert app._max_misses() == 6
