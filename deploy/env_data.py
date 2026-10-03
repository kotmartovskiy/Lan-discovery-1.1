#!/usr/bin/env python3
"""Fetch UV index, air quality, and radiation (ЕГАСМРО) for the settlement from settings"""

import http.cookiejar
import json
import math
import sqlite3
import urllib.request
from datetime import datetime, timezone, timedelta

DB = "/opt/lan-discovery/devices.db"
SETTINGS = "/etc/lan-discovery/settings.json"
LAT = 57.0
LON = 41.0
TZ = timezone(timedelta(hours=3))

EGASRMRO = "https://egasmro.ru"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
DIRS = ["С", "ССВ", "СВ", "ВСВ", "В", "ВЮВ", "ЮВ", "ЮЮВ",
        "Ю", "ЮЮЗ", "ЮЗ", "ЗЮЗ", "З", "ЗСЗ", "СЗ", "ССЗ"]


def load_site():
    """(lat, lon, населённый пункт, сколько ближайших пунктов) из settings.weather."""
    lat, lon, name, count = LAT, LON, "Иваново", 3
    try:
        with open(SETTINGS, encoding="utf-8") as f:
            w = json.load(f).get("weather", {})
        lat = float(w.get("latitude", lat))
        lon = float(w.get("longitude", lon))
        name = str(w.get("region_name") or name)
        count = int(w.get("radiation_points", count))
    except Exception as e:
        print(f"  Settings load failed ({e}), using defaults")
    return lat, lon, name, max(1, min(count, 10))


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
    cols = {r[1] for r in con.execute("PRAGMA table_info(env_data)")}
    if "radiation_points" not in cols:
        con.execute("ALTER TABLE env_data ADD COLUMN radiation_points TEXT")
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


def haversine_km(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(a))


def bearing_deg(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return math.degrees(math.atan2(y, x)) % 360


def direction_name(deg):
    return DIRS[int(((deg + 11.25) % 360) / 22.5)]


def nearest_points(rows, lat, lon, count):
    """Ближайшие пункты ЕГАСМРО к населённому пункту: tind=0 — только МЭД, мкЗв/ч."""
    pts = []
    for r in rows:
        if r.get("tind", 0) != 0:
            continue
        try:
            value = float(str(r.get("value")).replace(",", "."))
            plat = float(r["lat"])
            plon = float(r["lng"])
        except (KeyError, TypeError, ValueError):
            continue
        pts.append({
            "name": str(r.get("name") or "?"),
            "value": value,
            "dist": round(haversine_km(lat, lon, plat, plon)),
            "dir": direction_name(bearing_deg(lat, lon, plat, plon)),
            "date": str(r.get("date") or ""),
            "lat": plat,
            "lng": plon,
        })
    pts.sort(key=lambda p: p["dist"])
    return pts[:count]


def fetch_radiation(lat, lon, count):
    """Полная сессионная цепочка ЕГАСМРО (getData.php без визита страниц → 403)."""
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    curdata = EGASRMRO + "/ru/data/overal/curdata"
    base = EGASRMRO + "/apps/RMOpenData_new"
    index = base + "/index.php?lang=ru"

    def get(url, referer=None, xrw=False):
        headers = {"User-Agent": UA, "Accept-Language": "ru-RU,ru;q=0.9"}
        if referer:
            headers["Referer"] = referer
        if xrw:
            headers["X-Requested-With"] = "XMLHttpRequest"
            headers["Accept"] = "application/json, text/javascript, */*; q=0.01"
        req = urllib.request.Request(url, headers=headers)
        with opener.open(req, timeout=20) as resp:
            return resp.read()

    get(curdata)
    get(index, referer=curdata)
    get(base + "/services/getParams.php?lang=ru", referer=index, xrw=True)
    body = get(base + "/services/getData.php?lang=ru", referer=index, xrw=True)
    data = json.loads(body.decode("utf-8-sig"))
    if data.get("status") != 1:
        raise RuntimeError(f"egasmro status={data.get('status')}")
    rows = data.get("data") or []
    return nearest_points(rows, lat, lon, count)


def radiation_level(rad):
    """МЭД мкЗв/ч (пороги ≈ старым 20/50/100 мкР/ч)."""
    if rad is None:
        return "Н/Д"
    if rad <= 0.2:
        return "Норма"
    if rad <= 0.5:
        return "Повышенный"
    if rad <= 1.0:
        return "Высокий"
    return "Опасный"


def prev_radiation():
    """Прошлые данные ЕГАСМРО (у точек своя дата замера) при сбое источника."""
    try:
        con = sqlite3.connect(DB, timeout=30)
        con.execute("PRAGMA busy_timeout=30000")
        row = con.execute(
            "SELECT radiation, radiation_points FROM env_data "
            "WHERE radiation_points IS NOT NULL ORDER BY date DESC LIMIT 1"
        ).fetchone()
        con.close()
        if row and row[1]:
            json.loads(row[1])
            return row[0], row[1]
    except Exception as e:
        print(f"  Prev radiation load failed: {e}")
    return None, None


def main():
    global LAT, LON
    init_db()
    now = datetime.now(TZ)
    today = now.strftime("%Y-%m-%d")

    LAT, LON, settlement, npoints = load_site()
    print(f"Fetching environment data for {today} "
          f"({settlement} {LAT}, {LON}, {npoints} point(s))...")

    uv = fetch_uv()
    print(f"  UV index: {uv}")

    aqi, pm25, pm10 = fetch_air_quality()
    print(f"  AQI: {aqi}, PM2.5: {pm25}, PM10: {pm10}")

    points = None
    try:
        points = fetch_radiation(LAT, LON, npoints)
        print(f"  Radiation: {len(points)} point(s), "
              f"nearest={points[0]['name']} {points[0]['value']} mSv/h"
              if points else "  Radiation: no points")
    except Exception as e:
        print(f"  Radiation failed: {e}")

    rad = points[0]["value"] if points else None
    pts_json = json.dumps(points, ensure_ascii=False) if points else None
    if points is None:
        rad, pts_json = prev_radiation()
        if pts_json:
            print(f"  Radiation: kept previous EGASRMRO data ({rad} mSv/h)")
    print(f"  Radiation: {rad} mSv/h ({radiation_level(rad)})")

    con = sqlite3.connect(DB)
    con.execute("PRAGMA busy_timeout=30000")
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("""
        INSERT OR REPLACE INTO env_data
        (date, uv_index, uv_level, aqi, aqi_level, pm25, pm10,
         radiation, radiation_level, radiation_points, fetched_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        today,
        uv, uv_level(uv),
        aqi, aqi_level(aqi), pm25, pm10,
        rad, radiation_level(rad), pts_json,
        now.isoformat()
    ))
    con.commit()
    con.close()
    print("Saved to database")


if __name__ == "__main__":
    main()
