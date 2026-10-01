# -*- coding: utf-8 -*-
"""Unit: SSRF-резидуал §8.8 — валидация схемы URL IPTV-плейлистов.

POST /system/iptv/add принимает URL, который сервер скачивает сам
(update-iptv.sh/curl): до фикса file://, gopher:// и прочее проходило.
Фикс: только http/https с netloc; внутренние адреса допустимы (LAN-модель).
"""
import json
import time

import pytest

import app
import modules.auth as auth
import modules.media_routes as media


@pytest.fixture()
def client(monkeypatch, tmp_path):
    app.app.config["TESTING"] = True
    old_csrf = app.app.config["WTF_CSRF_ENABLED"]
    app.app.config["WTF_CSRF_ENABLED"] = False
    monkeypatch.setattr(
        auth, "load_users",
        lambda: {"admin": {"enabled": True, "role": "admin"}},
    )
    cfg = tmp_path / "iptv-playlists.json"
    monkeypatch.setattr(media, "IPTV_CONFIG", str(cfg))
    media._iptv_playlists_cache["data"] = None
    media._iptv_playlists_cache["ts"] = 0
    c = app.app.test_client()
    with c.session_transaction() as s:
        s["user"] = "admin"
        s["login_ts"] = time.time()
    yield c
    media._iptv_playlists_cache["data"] = None
    media._iptv_playlists_cache["ts"] = 0
    app.app.config["WTF_CSRF_ENABLED"] = old_csrf


def _saved(tmp_path):
    cfg = tmp_path / "iptv-playlists.json"
    if not cfg.exists():
        return []
    return json.loads(cfg.read_text(encoding="utf-8"))


@pytest.mark.parametrize("url", [
    "file:///etc/passwd",
    "file://localhost/etc/passwd",
    "gopher://127.0.0.1:25/_x",
    "ftp://example.com/p.m3u",
    "javascript:alert(1)",
    "//evil.example/p.m3u",          # схема пустая
    "http:///no-netloc.m3u",         # http без netloc
])
def test_reject_non_http_schemes(client, tmp_path, url):
    r = client.post("/system/iptv/add", data={"name": "bad", "url": url})
    assert r.status_code == 302  # тихий редирект, как при пустых полях
    assert _saved(tmp_path) == []


@pytest.mark.parametrize("url", [
    "http://example.com/p.m3u",
    "https://example.com/p.m3u?x=1",
    "http://192.168.3.1:8080/local.m3u",   # внутренний адрес — LAN-модель
    "http://localhost/playlist",           # localhost по http — допустим
])
def test_accept_http_https(client, tmp_path, url):
    r = client.post("/system/iptv/add", data={"name": "ok", "url": url})
    assert r.status_code == 302
    data = _saved(tmp_path)
    assert len(data) == 1
    assert data[0]["url"] == url
    assert data[0]["enabled"] is True
