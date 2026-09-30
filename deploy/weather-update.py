#!/usr/bin/env python3
"""Сбор погодных данных для панели LAN Discovery (Open-Meteo).

Пишет в /opt/lan-discovery/devices.db:
  weather_observations   — текущий час (наблюдение для шапки/сейчас)
  weather_hourly         — почасовой прогноз: остаток сегодня + завтра
  weather_daily          — агрегаты текущего дня из наблюдений
  weather_forecast       — прогноз на 7 дней (+ восход/заход)
  weather_forecast_history — архив ежедневных прогнозов
  weather_alerts         — гидромет-предупреждение (meteoinfo.ru информер)
  mchs_alerts            — последнее экстренное предупреждение (37.mchs.gov.ru)

Координаты/регион берутся из /etc/lan-discovery/settings.json (секция weather).
"""
import json
import os
import re
import sqlite3
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

DB = "/opt/lan-discovery/devices.db"
SETTINGS = "/etc/lan-discovery/settings.json"
TZ = timezone(timedelta(hours=3))

# Основной forecast API и запасной ensemble-эндпоинт (тот же формат полей).
ENDPOINTS = (
    "https://api.open-meteo.com/v1/forecast?",
    "https://ensemble-api.open-meteo.com/v1/ensemble?models=icon_seamless&",
)


def load_settings():
    try:
        with open(SETTINGS, encoding="utf-8") as f:
            return json.load(f).get("weather", {})
    except Exception:
        return {}


def get_json(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": "lan-discovery-weather"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch(query, tries=2, timeout=12, pause=5):
    """Перебирает эндпоинты с ретраями, возвращает (data, endpoint)."""
    last = None
    for base in ENDPOINTS:
        url = base + query
        for _ in range(tries):
            try:
                return get_json(url, timeout=timeout), base.split("?")[0]
            except Exception as e:
                last = e
                time.sleep(pause)
    raise last


REGION_CODES = {
    "ivanovo": "019",
    "yaroslavl": "076",
    "kostroma": "044",
    "vladimir": "33",
    "nizhny_novgorod": "52",
    "ryazan": "62",
    "moscow": "50",
    "moscow_region": "50",
    "tver": "69",
}


def fetch_weather_alert(w):
    """Гидромет-предупреждение с информера meteoinfo.ru (POST-регион)."""
    region_code = w.get("region_code", "ivanovo")
    post_code = REGION_CODES.get(region_code, "019")

    url = "https://meteoinfo.ru/informer/meteoalert/"
    request = urllib.request.Request(
        url,
        data=f"a={post_code}".encode(),
        method="POST",
        headers={"User-Agent": "lan-discovery-weather"},
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        html = response.read().decode("utf-8", "ignore")

    match = re.search(
        r"Ивановская обл\..{0,1500}?<img[^>]+title=\"([^\"]+)\"",
        html,
        re.I | re.S,
    )
    if not match:
        return None
    alert = match.group(1).strip()
    if alert == "Оповещения о погоде не требуется":
        alert = None
    return alert


def update_weather_alert(con, w, now):
    fetched_at = now.isoformat(timespec="minutes")
    try:
        alert = fetch_weather_alert(w)
    except Exception as e:
        print("=== WEATHER ALERT ERROR: %s" % e, file=sys.stderr)
        return
    con.execute(
        """INSERT INTO weather_alerts (id, fetched_at, region, alert, source_window)
           VALUES (1, ?, ?, ?, 'ближайшие 24 часа')
           ON CONFLICT(id) DO UPDATE SET
               fetched_at=excluded.fetched_at, region=excluded.region,
               alert=excluded.alert, source_window=excluded.source_window""",
        (fetched_at, w.get("region_name", "Иваново"), alert),
    )
    con.commit()
    print("=== WEATHER ALERT OK: %s" % (alert or "нет предупреждений"))


def fetch_mchs_alert():
    """Последнее экстренное предупреждение с регионального сайта МЧС."""
    list_url = (
        "https://37.mchs.gov.ru/deyatelnost/press-centr/"
        "operativnaya-informaciya/shtormovye-i-ekstrennye-preduprezhdeniya"
    )
    request = urllib.request.Request(
        list_url, headers={"User-Agent": "lan-discovery-weather"}
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        html = response.read().decode("utf-8", "ignore")

    match = re.search(
        r"<a class=\"articles-item__title\" href=\"([^\"]+)\">([^<]+)</a>",
        html,
        re.I,
    )
    if not match:
        return None

    path = match.group(1)
    title = re.sub(r"\s+", " ", match.group(2)).strip()
    article_url = (
        path if path.startswith("http") else "https://37.mchs.gov.ru" + path
    )

    request = urllib.request.Request(
        article_url, headers={"User-Agent": "lan-discovery-weather"}
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        article_html = response.read().decode("utf-8", "ignore")

    published = re.search(
        r"<meta[^>]+itemprop=\"datePublished\"[^>]+(?:datetime|content)=\"([^\"]+)\"",
        article_html,
        re.I,
    )
    body = re.search(
        r"<article[^>]+itemprop=\"articleBody\"[^>]*>(.*?)</article>",
        article_html,
        re.I | re.S,
    )

    text = None
    if body:
        text = re.sub(r"<br\s*/?>", "\n", body.group(1), flags=re.I)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"&nbsp;", " ", text, flags=re.I)
        text = re.sub(r"\s+", " ", text).strip()

    return {
        "title": title,
        "published_at": published.group(1).strip() if published else None,
        "text": text,
        "source_url": article_url,
    }


def update_mchs_alert(con, now):
    fetched_at = now.isoformat(timespec="minutes")
    try:
        alert = fetch_mchs_alert()
    except Exception as e:
        print("=== MCHS ALERT ERROR: %s" % e, file=sys.stderr)
        return
    if not alert:
        print("=== MCHS ALERT: предупреждение не найдено")
        return
    con.execute(
        """INSERT INTO mchs_alerts (id, fetched_at, published_at, title, text, source_url)
           VALUES (1, ?, ?, ?, ?, ?)
           ON CONFLICT(id) DO UPDATE SET
               fetched_at=excluded.fetched_at, published_at=excluded.published_at,
               title=excluded.title, text=excluded.text,
               source_url=excluded.source_url""",
        (fetched_at, alert["published_at"], alert["title"],
         alert["text"], alert["source_url"]),
    )
    con.commit()
    print("=== MCHS ALERT OK: %s" % alert["title"])


def main():
    w = load_settings()
    lat = w.get("latitude", 57.0)
    lon = w.get("longitude", 41.0)
    tzname = w.get("timezone", "Europe/Moscow")
    now = datetime.now(TZ)
    today = now.strftime("%Y-%m-%d")
    tomorrow = (now + timedelta(days=1)).strftime("%Y-%m-%d")

    query = (
        f"latitude={lat}&longitude={lon}"
        f"&timezone={urllib.parse.quote(tzname)}"
        "&current=temperature_2m,apparent_temperature,relative_humidity_2m,"
        "precipitation,weather_code,wind_speed_10m,wind_direction_10m,"
        "surface_pressure,cloud_cover"
        "&hourly=temperature_2m,weather_code,precipitation,precipitation_probability,"
        "wind_speed_10m,wind_direction_10m,cloud_cover"
        "&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum,"
        "precipitation_probability_max,wind_speed_10m_max,sunrise,sunset"
        "&forecast_days=7"
    )
    data, endpoint = fetch(query)

    current = data.get("current", {})
    hourly = data.get("hourly", {})
    daily = data.get("daily", {})
    fetched_at = now.isoformat(timespec="minutes")

    con = sqlite3.connect(DB, timeout=30)
    con.execute("PRAGMA busy_timeout=30000")

    # --- текущий час: одно наблюдение на час ---
    ts_hour = now.strftime("%Y-%m-%dT%H:00")
    con.execute("DELETE FROM weather_observations WHERE timestamp = ?", (ts_hour,))
    con.execute(
        """INSERT INTO weather_observations
           (timestamp, temperature, apparent_temperature, humidity, precipitation,
            weather_code, wind_speed, wind_direction, pressure, cloud_cover)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            ts_hour,
            current.get("temperature_2m"),
            current.get("apparent_temperature"),
            current.get("relative_humidity_2m"),
            current.get("precipitation"),
            current.get("weather_code"),
            current.get("wind_speed_10m"),
            current.get("wind_direction_10m"),
            current.get("surface_pressure"),
            current.get("cloud_cover"),
        ),
    )

    # --- агрегаты текущего дня из накопленных наблюдений ---
    con.execute("DELETE FROM weather_daily WHERE date = ?", (today,))
    con.execute(
        """INSERT INTO weather_daily
           (date, temp_min, temp_max, temp_avg, humidity_avg, pressure_avg,
            wind_avg, precipitation_sum, observations)
           SELECT substr(timestamp, 1, 10), min(temperature), max(temperature),
                  avg(temperature), avg(humidity), avg(pressure), avg(wind_speed),
                  coalesce(sum(precipitation), 0), count(*)
           FROM weather_observations
           WHERE substr(timestamp, 1, 10) = ?""",
        (today,),
    )

    # --- почасовой: остаток сегодня + завтра ---
    con.execute("DELETE FROM weather_hourly")
    times = hourly.get("time", [])
    now_h = now.strftime("%Y-%m-%dT%H:00")
    for i, t in enumerate(times):
        if len(t) < 13:
            continue
        fdate, hour = t[:10], int(t[11:13])
        if fdate not in (today, tomorrow):
            continue
        if fdate == today and t < now_h:
            continue
        con.execute(
            """INSERT OR REPLACE INTO weather_hourly
               (forecast_date, hour, temperature, weather_code, precipitation,
                precipitation_probability, wind_speed, wind_direction, cloud_cover)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                fdate,
                hour,
                hourly.get("temperature_2m", [None] * len(times))[i],
                hourly.get("weather_code", [None] * len(times))[i],
                hourly.get("precipitation", [None] * len(times))[i],
                hourly.get("precipitation_probability", [None] * len(times))[i],
                hourly.get("wind_speed_10m", [None] * len(times))[i],
                hourly.get("wind_direction_10m", [None] * len(times))[i],
                hourly.get("cloud_cover", [None] * len(times))[i],
            ),
        )

    # --- прогноз на 7 дней (направление ветра — с полудня) ---
    # Чистим просроченные даты, иначе LIMIT 7 в ридере отдаёт старые хвосты.
    con.execute("DELETE FROM weather_forecast WHERE forecast_date < ?", (today,))

    noon_wdir = {}
    for i, t in enumerate(times):
        if len(t) >= 13 and int(t[11:13]) == 12:
            noon_wdir[t[:10]] = hourly.get("wind_direction_10m", [None] * len(times))[i]

    fc_rows = []
    d_times = daily.get("time", [])
    for i, fdate in enumerate(d_times):
        row = (
            fdate,
            daily.get("weather_code", [None] * len(d_times))[i],
            daily.get("temperature_2m_min", [None] * len(d_times))[i],
            daily.get("temperature_2m_max", [None] * len(d_times))[i],
            daily.get("precipitation_sum", [None] * len(d_times))[i],
            daily.get("precipitation_probability_max", [None] * len(d_times))[i],
            daily.get("wind_speed_10m_max", [None] * len(d_times))[i],
            noon_wdir.get(fdate),
            (daily.get("sunrise", [None] * len(d_times))[i] or None),
            (daily.get("sunset", [None] * len(d_times))[i] or None),
            fetched_at,
        )
        fc_rows.append(row)
        con.execute(
            """INSERT OR REPLACE INTO weather_forecast
               (forecast_date, weather_code, temp_min, temp_max, precipitation_sum,
                precipitation_probability, wind_speed_max, wind_direction,
                sunrise, sunset, fetched_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            row,
        )
        con.execute(
            """INSERT OR REPLACE INTO weather_forecast_history
               (fetched_at, forecast_date, weather_code, temp_min, temp_max,
                precipitation_sum, precipitation_probability, wind_speed_max,
                wind_direction, sunrise, sunset)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            row[:11],
        )

    con.commit()

    # --- предупреждения (meteoinfo + МЧС), сбой источника не валит погоду ---
    update_weather_alert(con, w, now)
    update_mchs_alert(con, now)
    con.close()

    print(
        "=== WEATHER UPDATE OK: %s (прогноз: %d дн., источник: %s)"
        % (
            now.strftime("%d.%m.%Y %H:%M:%S"),
            len(fc_rows),
            endpoint.rsplit("/", 1)[-1],
        )
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("=== WEATHER UPDATE FAILED: %s" % e, file=sys.stderr)
        raise SystemExit(1)
