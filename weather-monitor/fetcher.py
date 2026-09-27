import requests
import logging
from datetime import datetime
from bs4 import BeautifulSoup
from database import (
    insert_weather,
    insert_air_quality,
    insert_uv,
    insert_radiation,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

LAT = 56.997
LON = 41.008
TZ = "Europe/Moscow"

UV_DESCRIPTIONS = {
    (0, 2): "Низкий",
    (3, 5): "Умеренный",
    (6, 7): "Высокий",
    (8, 10): "Очень высокий",
    (11, 99): "Экстремальный",
}


def describe_uv(uv: float) -> str:
    for (lo, hi), desc in UV_DESCRIPTIONS.items():
        if lo <= uv <= hi:
            return desc
    return "Неизвестно"


def aqi_from_pm25(pm25: float) -> int:
    if pm25 is None:
        return 0
    if pm25 <= 12:
        return int(pm25 * 50 / 12)
    elif pm25 <= 35.4:
        return 50 + int((pm25 - 12) * 49 / 23.4)
    elif pm25 <= 55.4:
        return 100 + int((pm25 - 35.4) * 49 / 20)
    elif pm25 <= 150.4:
        return 150 + int((pm25 - 55.4) * 49 / 95)
    elif pm25 <= 250.4:
        return 200 + int((pm25 - 150.4) * 99 / 100)
    else:
        return 300 + int((pm25 - 250.4) * 99 / 250)


def fetch_weather():
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={LAT}&longitude={LON}"
        f"&current=temperature_2m,relative_humidity_2m,wind_speed_10m,"
        f"weather_code,surface_pressure"
        f"&daily=uv_index_max,uv_index_clear_sky_max"
        f"&timezone={TZ}"
    )
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        current = data.get("current", {})
        now = datetime.now().isoformat(timespec="minutes")

        insert_weather({
            "timestamp": now,
            "temp": current.get("temperature_2m"),
            "humidity": current.get("relative_humidity_2m"),
            "wind_speed": current.get("wind_speed_10m"),
            "weather_code": current.get("weather_code"),
            "weather_desc": wmo_desc(current.get("weather_code", 0)),
            "pressure": current.get("surface_pressure"),
        })

        daily = data.get("daily", {})
        uv_values = daily.get("uv_index_max", [])
        if uv_values:
            uv_val = uv_values[0]
            insert_uv({
                "timestamp": now,
                "uv_max": uv_val,
                "uv_description": describe_uv(uv_val),
            })

        log.info("Weather + UV saved: temp=%s, uv=%s", current.get("temperature_2m"), uv_values[0] if uv_values else None)
        return True
    except Exception as e:
        log.error("Failed to fetch weather: %s", e)
        return False


def fetch_air_quality():
    url = (
        f"https://air-quality-api.open-meteo.com/v1/air-quality"
        f"?latitude={LAT}&longitude={LON}"
        f"&current=pm10,pm2_5,carbon_monoxide,nitrogen_dioxide,"
        f"sulphur_dioxide,ozone"
        f"&timezone={TZ}"
    )
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        current = data.get("current", {})
        now = datetime.now().isoformat(timespec="minutes")

        pm25 = current.get("pm2_5")
        insert_air_quality({
            "timestamp": now,
            "pm10": current.get("pm10"),
            "pm2_5": pm25,
            "no2": current.get("nitrogen_dioxide"),
            "so2": current.get("sulphur_dioxide"),
            "o3": current.get("ozone"),
            "co": current.get("carbon_monoxide"),
            "aqi": aqi_from_pm25(pm25),
        })

        log.info("Air quality saved: PM2.5=%s, AQI=%s", pm25, aqi_from_pm25(pm25))
        return True
    except Exception as e:
        log.error("Failed to fetch air quality: %s", e)
        return False


def fetch_radiation():
    import re

    sources = [
        ("https://www.meteoinfo.ru/forecasts/russia/ivanovo-region/ivanovo", "meteoinfo.ru"),
    ]

    radiation_value = None
    source_used = None

    for url, source_name in sources:
        try:
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            resp.encoding = "utf-8"
            soup = BeautifulSoup(resp.text, "lxml")
            text = soup.get_text()

            for line in text.split("\n"):
                line = line.strip()
                if "радиац" in line.lower() or "мкР" in line or "μR" in line:
                    numbers = re.findall(r"[\d.,]+", line)
                    if numbers:
                        radiation_value = float(numbers[0].replace(",", "."))
                        source_used = source_name
                        break

            if radiation_value is None:
                match = re.search(r"(\d+[.,]?\d*)\s*(?:мкР/?ч|μR/?h)", text)
                if match:
                    radiation_value = float(match.group(1).replace(",", "."))
                    source_used = source_name

            if radiation_value is not None:
                break
        except Exception as e:
            log.warning("Radiation fetch failed from %s: %s", source_name, e)
            continue

    now = datetime.now().isoformat(timespec="minutes")
    insert_radiation({
        "timestamp": now,
        "radiation_value": radiation_value,
        "unit": "μR/h",
        "source": source_used or "Нет данных",
    })

    if radiation_value is not None:
        log.info("Radiation saved: %s μR/h (source: %s)", radiation_value, source_used)
    else:
        log.warning("Radiation data not available from any source")
    return radiation_value is not None


def fetch_all():
    log.info("Starting data fetch cycle...")
    fetch_weather()
    fetch_air_quality()
    fetch_radiation()
    log.info("Fetch cycle complete.")


def wmo_desc(code: int) -> str:
    wmo = {
        0: "Ясно", 1: "Преимущественно ясно", 2: "Переменная облачность",
        3: "Пасмурно", 45: "Туман", 48: "Изморось",
        51: "Лёгкая морось", 53: "Умеренная морось", 55: "Сильная морось",
        61: "Небольшой дождь", 63: "Умеренный дождь", 65: "Сильный дождь",
        71: "Небольшой снег", 73: "Умеренный снег", 75: "Сильный снег",
        80: "Небольшой ливень", 81: "Умеренный ливень", 82: "Сильный ливень",
        95: "Гроза", 96: "Гроза с градом", 99: "Сильная гроза с градом",
    }
    return wmo.get(code, f"Код {code}")


if __name__ == "__main__":
    from database import init_db
    init_db()
    fetch_all()
