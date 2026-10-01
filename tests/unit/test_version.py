# -*- coding: utf-8 -*-
"""Unit: семверы/чейнджлог (№63, P10) — APP_VERSION, CHANGELOG, health."""
import re

import pytest

import app
import modules.auth as auth


def test_app_version_is_semver():
    assert re.fullmatch(r"\d+\.\d+\.\d+", app.APP_VERSION), (
        f"APP_VERSION не семвер: {app.APP_VERSION!r}"
    )


def test_changelog_mentions_current_version():
    text = open("CHANGELOG.md", encoding="utf-8").read()
    assert f"## [{app.APP_VERSION}]" in text, (
        f"в CHANGELOG.md нет раздела ## [{app.APP_VERSION}]"
    )


def test_health_reports_version():
    app.app.config["TESTING"] = True
    c = app.app.test_client()
    data = c.get("/api/health").get_json()
    assert data.get("version") == app.APP_VERSION


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
        import time as _t
        s["login_ts"] = _t.time()
    yield c


def test_about_page_shows_version(client):
    html = client.get("/about").get_data(as_text=True)
    assert f">v{app.APP_VERSION}<" in html.replace("\n", "").replace(
        "  ", " "
    ) or f"v{app.APP_VERSION}" in html
