# -*- coding: utf-8 -*-
"""Unit: свежесть погодных данных в ридере /weather (прогноз/предупреждения)."""
from datetime import datetime, timedelta

import pytest

import modules.weather_routes as wr


@pytest.fixture()
def wdb(devices_db, monkeypatch):
    """Временная БД (все серверные таблицы) + переопределение путей ридера."""
    monkeypatch.setattr(wr, "DB", devices_db)
    monkeypatch.setattr(
        wr, "load_settings",
        lambda: {"weather": {"region_name": "Иваново",
                             "region_code": "ivanovo"}}
    )
    return devices_db


def _insert_forecast(db, date, code=0):
    import sqlite3
    con = sqlite3.connect(db)
    con.execute(
        "INSERT OR REPLACE INTO weather_forecast "
        "(forecast_date, weather_code, temp_min, temp_max, fetched_at) "
        "VALUES (?, ?, 1.0, 2.0, ?)",
        (date, code, datetime.now().isoformat(timespec="minutes")),
    )
    con.commit()
    con.close()


def test_forecast_excludes_past_dates(wdb):
    today = datetime.now().strftime("%Y-%m-%d")
    for delta in (-3, -1, 0, 1, 2, 8):
        _insert_forecast(wdb, (datetime.now() + timedelta(days=delta))
                         .strftime("%Y-%m-%d"))

    rows = wr.weather_forecast()
    dates = [r[0] for r in rows]

    assert dates[0] == today
    assert all(d >= today for d in dates)
    assert len(dates) == 4  # today, +1, +2 (хвосты отфильтрованы, +8 в пределах 7)


def test_forecast_limit_seven(wdb):
    for delta in range(9):
        _insert_forecast(wdb, (datetime.now() + timedelta(days=delta))
                         .strftime("%Y-%m-%d"))

    rows = wr.weather_forecast()
    assert len(rows) == 7


def _insert_weather_alert(db, fetched_at, alert="Туман"):
    import sqlite3
    con = sqlite3.connect(db)
    con.execute("DELETE FROM weather_alerts")
    con.execute(
        "INSERT INTO weather_alerts (id, fetched_at, region, alert, source_window) "
        "VALUES (1, ?, 'Иваново', ?, 'ближайшие 24 часа')",
        (fetched_at, alert),
    )
    con.commit()
    con.close()


def test_weather_alert_fresh_shown(wdb):
    fresh = (datetime.now() - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M")
    _insert_weather_alert(wdb, fresh)
    assert wr.weather_alerts() == [
        (fresh, "Иваново", "Туман", "ближайшие 24 часа")
    ]


def test_weather_alert_stale_hidden(wdb):
    stale = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%dT%H:%M")
    _insert_weather_alert(wdb, stale)
    assert wr.weather_alerts() == []


def test_weather_alert_empty_hidden(wdb):
    fresh = datetime.now().strftime("%Y-%m-%dT%H:%M")
    _insert_weather_alert(wdb, fresh, alert=None)
    assert wr.weather_alerts() == []


def _set_mchs(db, published_at, text):
    import sqlite3
    con = sqlite3.connect(db)
    con.execute("DELETE FROM mchs_alerts")
    con.execute(
        "INSERT INTO mchs_alerts (id, fetched_at, published_at, title, text, "
        "source_url) VALUES (1, ?, ?, 'Предупреждение', ?, "
        "'https://37.mchs.gov.ru/x')",
        (datetime.now().isoformat(timespec="minutes"), published_at, text),
    )
    con.commit()
    con.close()


def test_mchs_expired_text_hidden(wdb):
    _set_mchs(wdb, "2026-09-28 12:07",
              "Действует до 09:00 28 сентября 2026 года")
    assert wr.mchs_alerts() == []


def test_mchs_old_without_expiry_hidden(wdb):
    old = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d %H:%M")
    _set_mchs(wdb, old, "Гроза, ливень, град")
    assert wr.mchs_alerts() == []


def test_mchs_recent_without_expiry_shown(wdb):
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    _set_mchs(wdb, now_str, "Гроза, ливень, град")
    assert len(wr.mchs_alerts()) == 1


def test_mchs_future_expiry_shown_regardless_of_age(wdb):
    months = ["января", "февраля", "марта", "апреля", "мая", "июня",
              "июля", "августа", "сентября", "октября", "ноября", "декабря"]
    future = datetime.now() + timedelta(days=1)
    old = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d %H:%M")
    text = "Действует до 09:00 %d %s %d года" % (
        future.day, months[future.month - 1], future.year)
    _set_mchs(wdb, old, text)
    assert len(wr.mchs_alerts()) == 1
