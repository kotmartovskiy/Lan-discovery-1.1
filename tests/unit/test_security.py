# -*- coding: utf-8 -*-
"""Unit: security-регресс (PHASE 8) — заголовки, cookie, аноним-поведение.

Фиксирует hardening P1-10/P0: nosniff/XFO/Referrer-Policy на всех
ответах, HttpOnly+SameSite=Lax у session-cookie, аноним → 302 на
/login, mutating-POST без CSRF → 400. Ловится в CI (без живой панели).
"""
import pytest

import app


@pytest.fixture()
def client():
    app.app.config["TESTING"] = True
    old = app.app.config["WTF_CSRF_ENABLED"]
    app.app.config["WTF_CSRF_ENABLED"] = False
    yield app.app.test_client()
    app.app.config["WTF_CSRF_ENABLED"] = old


@pytest.fixture()
def csrf_client():
    """CSRF включён — для проверки отказа анониму."""
    app.app.config["TESTING"] = True
    old = app.app.config["WTF_CSRF_ENABLED"]
    app.app.config["WTF_CSRF_ENABLED"] = True
    yield app.app.test_client()
    app.app.config["WTF_CSRF_ENABLED"] = old


def test_security_headers_on_login(client):
    r = client.get("/login")
    assert r.status_code == 200
    assert r.headers.get("X-Content-Type-Options") == "nosniff"
    assert r.headers.get("X-Frame-Options") == "SAMEORIGIN"
    assert r.headers.get("Referrer-Policy") == "same-origin"


def test_security_headers_on_api(client):
    r = client.get("/api/health")
    assert r.status_code in (200, 503)  # 503 — нет системных бинарей
    assert r.headers.get("X-Content-Type-Options") == "nosniff"
    assert r.headers.get("X-Frame-Options") == "SAMEORIGIN"


def test_security_headers_on_static(client):
    r = client.get("/static/style.css")
    assert r.status_code == 200
    assert r.headers.get("X-Content-Type-Options") == "nosniff"


def test_session_cookie_flags(client):
    r = client.get("/login")
    sc = r.headers.get("Set-Cookie", "")
    assert "HttpOnly" in sc
    assert "SameSite=Lax" in sc
    assert "Secure" not in sc  # панель по HTTP в LAN — Secure сломает вход


def test_api_response_no_store(client):
    r = client.get("/api/health")
    assert "no-store" in r.headers.get("Cache-Control", "")


def test_anonymous_redirects_to_login(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 302
    assert "/login" in r.headers.get("Location", "")


def test_anonymous_cannot_read_settings(client):
    r = client.get("/api/settings")
    assert r.status_code in (302, 401)
    if r.status_code == 302:
        assert "/login" in r.headers.get("Location", "")


def test_mutating_post_without_csrf_is_rejected(csrf_client):
    r = csrf_client.post("/api/settings", json={"web": {}})
    assert r.status_code == 400
