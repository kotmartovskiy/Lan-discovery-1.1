#!/usr/bin/env python3
"""Fetch UV index, air quality, and radiation data for Иваново"""

import json
import os
import sqlite3
import urllib.request
from datetime import datetime, timezone, timedelta

DB = "/opt/lan-discovery/devices.db"
LAT = 57.0
LON = 41.0
TZ = timezone(timedelta(hours=3))

def init_db():
    con = sqlite3.connect(DB)
    con.execute("PRAGMA busy_timeout=30000")
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("""
        CREATE TABLE IF NOT EXISTS env_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT UNIQUE,
            uv_index REAL,
            uv_level TEXT,
            aqi REAL,
            aqi_level TEXT,
            pm25 REAL,
            pm10 REAL,
            radiation REAL,
            radiation_level TEXT,
            fetched_at TEXT
        )
    """)
    con.commit()
    con.close()

def fetch_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())

def fetch_uv():
    """Fetch UV index. air-quality host first (different subnet, reachable),
    forecast host as fallback"""
    urls = [
        (
            "https://air-quality-api.open-meteo.com/v1/air-quality"
            f"?latitude={LAT}&longitude={LON}"
            "&daily=uv_index_max,uv_index_clear_sky_max"
            "&timezone=Europe/Moscow"
            "&forecast_days=1"
        ),
        (
            "https://api.open-meteo.com/v1/forecast"
            f"?latitude={LAT}&longitude={LON}"
            "&daily=uv_index_max,uv_index_clear_sky_max"
            "&timezone=Europe/Moscow"
            "&forecast_days=1"
        ),
    ]
    for url in urls:
        try:
            data = fetch_json(url)
            uv = data.get("daily", {}).get("uv_index_max", [None])[0]
            if uv is not None:
                return uv
        except Exception as e:
            print(f"  UV failed ({url.split('/')[2]}): {e}")
    return None

def uv_level(uv):
    if uv is None:
        return "Н/Д"
    if uv <= 2:
        return "Низкий"
    if uv <= 5:
        return "Умеренный"
    if uv <= 7:
        return "Высокий"
    if uv <= 10:
        return "Очень высокий"
    return "Экстремальный"

def fetch_air_quality():
    """Fetch air quality from Open-Meteo"""
    url = (
        f"https://air-quality-api.open-meteo.com/v1/air-quality?"
        f"latitude={LAT}&longitude={LON}"
        f"&current=european_aqi,pm10,pm2_5"
        f"&timezone=Europe/Moscow"
    )
    try:
        data = fetch_json(url)
    except Exception as e:
        print(f"  Air quality failed: {e}")
        return None, None, None
    current = data.get("current", {})
    aqi = current.get("european_aqi")
    pm25 = current.get("pm2_5")
    pm10 = current.get("pm10")
    return aqi, pm25, pm10

def aqi_level(aqi):
    if aqi is None:
        return "Н/Д"
    if aqi <= 20:
        return "Отлично"
    if aqi <= 40:
        return "Хорошо"
    if aqi <= 60:
        return "Умеренно"
    if aqi <= 80:
        return "Плохо"
    if aqi <= 100:
        return "Очень плохо"
    return "Ужасно"

def fetch_radiation():
    """Background radiation, µR/h.
    No public API available for our region (checked 2026-09:
    Rosgidromet EIP open data, open-radiation.org, Safecast,
    api_radiation.vercel.app - dead).
    TODO: replace with the home dosimeter device."""
    return None

def radiation_level(rad):
    if rad is None:
        return "Н/Д"
    if rad <= 20:
        return "Норма"
    if rad <= 50:
        return "Повышенный"
    if rad <= 100:
        return "Высокий"
    return "Опасный"

def main():
    init_db()
    now = datetime.now(TZ)
    today = now.strftime("%Y-%m-%d")

    print(f"Fetching environment data for {today}...")

    uv = fetch_uv()
    print(f"  UV index: {uv}")

    aqi, pm25, pm10 = fetch_air_quality()
    print(f"  AQI: {aqi}, PM2.5: {pm25}, PM10: {pm10}")

    rad = fetch_radiation()
    print(f"  Radiation: {rad} µR/h")

    con = sqlite3.connect(DB)
    con.execute("PRAGMA busy_timeout=30000")
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("""
        INSERT OR REPLACE INTO env_data
        (date, uv_index, uv_level, aqi, aqi_level, pm25, pm10,
         radiation, radiation_level, fetched_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        today,
        uv, uv_level(uv),
        aqi, aqi_level(aqi), pm25, pm10,
        rad, radiation_level(rad),
        now.isoformat()
    ))
    con.commit()
    con.close()
    print("Saved to database")

if __name__ == "__main__":
    main()
