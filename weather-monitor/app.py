import requests
from flask import Flask, render_template, jsonify
from database import (
    get_latest_weather,
    get_latest_air,
    get_latest_uv,
    get_latest_radiation,
    get_today_weather,
    get_today_air,
    get_history,
)

app = Flask(__name__)

LAT = 56.997
LON = 41.008
TZ = "Europe/Moscow"

DAILY_URL = (
    f"https://api.open-meteo.com/v1/forecast"
    f"?latitude={LAT}&longitude={LON}"
    f"&daily=precipitation_sum,precipitation_probability_max,"
    f"sunrise,sunset,uv_index_max"
    f"&timezone={TZ}"
)


def get_daily_extra():
    try:
        r = requests.get(DAILY_URL, timeout=10)
        r.raise_for_status()
        return r.json().get("daily", {})
    except Exception:
        return {}


UV_CLASSES = {
    "Низкий": "uv-nizkiy",
    "Умеренный": "uv-umerennyy",
    "Высокий": "uv-vysokiy",
    "Очень высокий": "uv-ochen-vysokiy",
    "Экстремальный": "uv-ekstremalnyy",
}


def uv_class_for(desc):
    for key, cls in UV_CLASSES.items():
        if key in (desc or ""):
            return cls
    return "uv-nizkiy"


def aqi_class_for(aqi):
    if aqi is None:
        return "aqi-unknown"
    if aqi < 50:
        return "aqi-good"
    if aqi < 100:
        return "aqi-fair"
    return "aqi-poor"


@app.route("/")
def index():
    weather = get_latest_weather() or {}
    air = get_latest_air() or {}
    uv_row = get_latest_uv() or {}
    radiation = get_latest_radiation() or {}
    today_weather = get_today_weather()

    daily = get_daily_extra()

    wtemp = "%.1f" % weather["temp"] if weather.get("temp") is not None else "—"
    wdesc = weather.get("weather_desc") or "—"
    wwind = "%.1f" % weather["wind_speed"] if weather.get("wind_speed") is not None else "—"
    whum = "%.0f" % weather["humidity"] if weather.get("humidity") is not None else "—"
    wpress = "%.0f" % weather["pressure"] if weather.get("pressure") is not None else "—"

    precip_vals = daily.get("precipitation_sum") or []
    precip_prob = daily.get("precipitation_probability_max") or []
    precip_sum = precip_vals[0] if precip_vals else None
    precip_p = precip_prob[0] if precip_prob else None
    if precip_sum is not None:
        precip = "%.1f мм, вероятность %d%%" % (precip_sum, precip_p or 0)
    else:
        precip = "—"

    sunrises = daily.get("sunrise") or []
    sunsets = daily.get("sunset") or []
    sunrise = sunrises[0][11:16] if sunrises else "—"
    sunset = sunsets[0][11:16] if sunsets else "—"

    uv_max = uv_row.get("uv_max")
    uv_desc = uv_row.get("uv_description") or "—"
    uv_val = "%.1f" % uv_max if uv_max is not None else "—"
    uv_pct = int(uv_max / 11 * 100) if uv_max is not None else 0
    uv_cls = uv_class_for(uv_desc)

    aqi_val = air.get("aqi")
    aqi_cls = aqi_class_for(aqi_val)

    return render_template(
        "weather.html",
        weather=weather,
        air=air,
        uv=uv_row,
        radiation=radiation,
        today_weather=today_weather,
        wtemp=wtemp,
        wdesc=wdesc,
        wwind=wwind,
        whum=whum,
        wpress=wpress,
        precip=precip,
        sunrise=sunrise,
        sunset=sunset,
        uv_max=uv_max,
        uv_val=uv_val,
        uv_desc=uv_desc,
        uv_pct=uv_pct,
        uv_class=uv_cls,
        aqi_class=aqi_cls,
    )


@app.route("/api/today")
def api_today():
    weather = get_latest_weather() or {}
    air = get_latest_air() or {}
    uv = get_latest_uv() or {}
    radiation = get_latest_radiation() or {}

    daily = get_daily_extra()
    precip_vals = daily.get("precipitation_sum") or []
    precip_prob = daily.get("precipitation_probability_max") or []

    return jsonify({
        "weather": weather,
        "air": air,
        "uv": uv,
        "radiation": radiation,
        "precipitation": {
            "sum": precip_vals[0] if precip_vals else None,
            "probability": precip_prob[0] if precip_prob else None,
        },
        "sunrise": (daily.get("sunrise") or [None])[0],
        "sunset": (daily.get("sunset") or [None])[0],
        "today_weather": get_today_weather(),
        "today_air": get_today_air(),
    })


@app.route("/api/history/<table>")
def api_history(table):
    allowed = {"weather", "air_quality", "uv_index", "radiation"}
    if table not in allowed:
        return jsonify({"error": "invalid table"}), 400
    return jsonify(get_history(table))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
