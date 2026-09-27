import os
import sys
import json
import time
import re
import sqlite3
import logging
import subprocess
import threading
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, "/opt/lan-discovery")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout
)
log = logging.getLogger("lan-discovery")

DB = "/opt/lan-discovery/devices.db"
NETWORK = "192.168.3.0/24"
SETTINGS_PATH = "/etc/lan-discovery/settings.json"
USERS_PATH = "/etc/lan-discovery/users.json"
IPTV_CONFIG = "/etc/lan-discovery/iptv-playlists.json"
IPTV_DIR = "/srv/media/IPTV"
IPTV_UPDATE_STATUS = "/etc/lan-discovery/iptv-update-status.json"
GAMES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "games")
TRANSMISSION_CONF = "/etc/transmission-daemon/settings.json"
SCAN_INTERVAL = 30
MAX_MISSES = 6

_settings_cache = {"data": None, "ts": 0}
_rate_limits = {}
_inet_cache = {"ok": None, "ts": 0}
_page_data_cache = {"data": None, "ts": 0}
_monitoring_cache = {"data": None, "ts": 0}


def load_settings():
    now = time.time()
    if _settings_cache["data"] is not None and now - _settings_cache["ts"] < 10:
        return _settings_cache["data"]
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        _settings_cache["data"] = data
        _settings_cache["ts"] = now
        return data
    except Exception:
        return {}


def save_settings(data):
    try:
        os.makedirs(os.path.dirname(SETTINGS_PATH), exist_ok=True)
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        _settings_cache["data"] = data
        _settings_cache["ts"] = time.time()
    except Exception:
        pass


def _check_rate(action, cooldown=60):
    now = time.time()
    last = _rate_limits.get(action, 0)
    if now - last < cooldown:
        return False
    _rate_limits[action] = now
    return True


def _cfg(section, key, default=None):
    s = load_settings().get(section, {})
    return s.get(key, default)


def _cmd(cmd, timeout=30):
    try:
        r = subprocess.run(cmd, shell=isinstance(cmd, str), capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip()
    except Exception:
        return ""


def _read_file(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


def _format_dt(dt_str):
    if not dt_str:
        return ""
    try:
        dt = datetime.fromisoformat(dt_str)
        return dt.strftime("%d.%m.%Y %H:%M:%S")
    except Exception:
        return str(dt_str)


def _human_size(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return "0 B"
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if value < 1024:
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} PB"


def check_internet():
    try:
        r = subprocess.run(["ping", "-c", "1", "-W", "2", "1.1.1.1"], capture_output=True, timeout=5)
        return r.returncode == 0
    except Exception:
        return False


def check_internet_cached():
    now = time.time()
    if _inet_cache["ok"] is not None and now - _inet_cache["ts"] < 60:
        return _inet_cache["ok"]
    ok = check_internet()
    _inet_cache["ok"] = ok
    _inet_cache["ts"] = now
    return ok


def weather_current():
    try:
        con = sqlite3.connect(DB, timeout=5)
        row = con.execute(
            "SELECT timestamp, temperature, apparent_temperature, humidity, precipitation, "
            "weather_code, wind_speed, wind_direction, pressure, cloud_cover "
            "FROM weather_observations ORDER BY timestamp DESC LIMIT 1"
        ).fetchone()
        con.close()
        if not row:
            return None
        return {
            "timestamp": row[0], "temperature": row[1], "apparent_temperature": row[2],
            "humidity": row[3], "precipitation": row[4], "weather_code": row[5],
            "wind_speed": row[6], "wind_direction": row[7], "pressure": row[8],
            "cloud_cover": row[9] if len(row) > 9 else None
        }
    except Exception:
        return None


def currency_category_name(cat):
    return {"fiat": "Fiat валюты", "crypto": "Криптовалюта",
            "precious": "Драгоценные металлы", "industrial": "Промышленные металлы"}.get(cat, cat)


def recycling_category_name(cat):
    return {"paper": "Бумага / макулатура", "metal": "Металлы",
            "electronics": "Электроника"}.get(cat, cat)


def page_data():
    now = time.time()
    if _page_data_cache["data"] is not None and now - _page_data_cache["ts"] < 10:
        return _page_data_cache["data"]
    data = {
        "internet": check_internet_cached(),
        "interval": SCAN_INTERVAL,
        "max_misses": MAX_MISSES,
        "weather": weather_current()
    }
    _page_data_cache["data"] = data
    _page_data_cache["ts"] = now
    return data


# ==================== Flask app ====================

from flask import Flask, request, redirect, url_for, render_template, session, jsonify, send_file
from flask_wtf.csrf import CSRFProtect

SECRET_KEY_PATH = "/etc/lan-discovery/secret.key"


def _load_or_create_secret_key():
    try:
        with open(SECRET_KEY_PATH, "rb") as f:
            key = f.read()
        if len(key) >= 32:
            return key.hex()
    except Exception:
        pass
    key = os.urandom(32)
    try:
        os.makedirs(os.path.dirname(SECRET_KEY_PATH), exist_ok=True)
        with open(SECRET_KEY_PATH, "wb") as f:
            f.write(key)
    except Exception:
        pass
    return key.hex()


app = Flask(__name__)
app.secret_key = _load_or_create_secret_key()
csrf = CSRFProtect(app)

app.jinja_env.globals["currency_category_name"] = currency_category_name
app.jinja_env.globals["recycling_category_name"] = recycling_category_name
app.jinja_env.globals["_format_dt"] = _format_dt


@app.after_request
def _no_cache(resp):
    if request.path.startswith("/api/") or request.path.endswith(".json"):
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return resp


@app.context_processor
def _inject_user():
    from types import SimpleNamespace
    from modules.auth import get_current_user, get_current_username
    u = get_current_user()
    if not u:
        u = SimpleNamespace(username="", role="guest", enabled=False, display_name="Гость")
    return {"current_user": u, "current_username": get_current_username()}


# ==================== Auth ====================

from modules.auth import register_routes as register_auth_routes
register_auth_routes(app)

from modules.auth import login_required, admin_required, can_edit
import app as _app_module
_app_module.login_required = login_required
_app_module.admin_required = admin_required
_app_module.can_edit = can_edit

# ==================== Devices ====================

from modules.devices_routes import register_routes as register_devices_routes, start_scan_thread
register_devices_routes(app)

# ==================== Weather ====================

from modules.weather_routes import register_routes as register_weather_routes
register_weather_routes(app)

# ==================== Currencies ====================

from modules.currencies import update_all as update_currencies, get_latest as get_currency_latest
from modules.recycling import update_all as update_recycling, get_latest as get_recycling_latest


@app.route("/api/currencies")
@login_required
def api_currencies():
    return jsonify({"usd": get_currency_latest("usd") or {}, "eur": get_currency_latest("eur") or {}})


def update_currencies_background():
    try:
        update_currencies()
    except Exception as e:
        log.error("Currency update failed: %s", e)


def update_recycling_background():
    try:
        update_recycling()
    except Exception as e:
        log.error("Recycling update failed: %s", e)


# ==================== System ====================

from modules.system_routes import register_routes as register_system_routes, service_state
register_system_routes(app)

# ==================== Network ====================

from modules.network_routes import register_routes as register_network_routes
register_network_routes(app, login_required, admin_required, can_edit, _cmd, _cfg, page_data)

# ==================== Media ====================

from modules.media_routes import register_routes as register_media_routes
register_media_routes(app, login_required, admin_required, can_edit, _cmd, service_state, page_data)

# ==================== Monitor ====================

from modules.monitor import get_system_overview, get_netdata_stats_for_host


@app.route("/monitoring")
@login_required
def monitoring():
    now = time.time()
    if _monitoring_cache["data"] is not None and now - _monitoring_cache["ts"] < 10:
        return render_template("monitoring.html", **_monitoring_cache["data"])

    data = page_data()

    hosts = _cfg("monitoring", "hosts", [
        {"ip": "192.168.3.234", "name": "Orange Pi", "netdata": True},
        {"ip": "192.168.3.7", "name": "Комп рабочий LAN", "netdata": False},
        {"ip": "192.168.3.236", "name": "Thinkpad T480 WiFi", "netdata": False},
        {"ip": "192.168.3.239", "name": "Thinkpad T480 LAN", "netdata": False},
    ])

    monitoring_hosts = []
    for host in hosts:
        info = {"ip": host["ip"], "name": host["name"], "netdata": False,
                "cpu_percent": None, "ram_percent": None, "uptime": ""}
        if host.get("netdata"):
            try:
                stats = get_netdata_stats_for_host(host["ip"])
                info["netdata"] = True
                info["cpu_percent"] = stats.get("cpu_percent", 0)
                info["ram_percent"] = stats.get("ram_percent", 0)
            except Exception:
                pass
        monitoring_hosts.append(info)

    try:
        netdata_overview = get_system_overview()
    except Exception:
        netdata_overview = None

    if netdata_overview and netdata_overview.get("ram"):
        ram = netdata_overview["ram"]
        netdata_overview["ram_items"] = [
            {"label": l, "value": v}
            for l, v in zip(ram.get("labels", []), ram.get("values", []))
        ]
    elif netdata_overview:
        netdata_overview["ram_items"] = []

    if netdata_overview and netdata_overview.get("network"):
        net = netdata_overview["network"]
        netdata_overview["net_items"] = [
            {"label": l, "value": v}
            for l, v in zip(net.get("labels", []), net.get("values", []))
        ]
    elif netdata_overview:
        netdata_overview["net_items"] = []

    data["monitoring_hosts"] = monitoring_hosts
    data["netdata_overview"] = netdata_overview

    _monitoring_cache["data"] = data
    _monitoring_cache["ts"] = time.time()

    return render_template("monitoring.html", **data)


@app.route("/api/monitoring/<ip>")
@login_required
def api_monitoring(ip):
    return jsonify(get_system_overview(ip))


# ==================== Inventory ====================

from modules.inventory import scan_device_full, get_inventory, init_inventory_db, scan_all_devices


@app.route("/inventory")
@login_required
def inventory():
    data = page_data()

    try:
        scanned = get_inventory()
    except Exception:
        scanned = []

    scanned_dict = {}
    for inv in scanned:
        ip = inv.get("ip", "") if isinstance(inv, dict) else getattr(inv, "ip", "")
        scanned_dict[ip] = inv

    known_web_ports = _cfg("network", "known_web_ports", {
        "192.168.3.234": 8080, "192.168.3.235": 8080, "192.168.3.51": 8080,
    })

    all_devices = []
    try:
        con = sqlite3.connect(DB, timeout=30)
        con.execute("PRAGMA busy_timeout=30000")
        device_names, device_online, device_types = {}, {}, {}
        for row in con.execute("SELECT ip, name, online, device_type FROM devices"):
            device_names[row[0]] = row[1] or ""
            device_online[row[0]] = row[2]
            device_types[row[0]] = row[3] or ""

        for row in con.execute("SELECT ip, hostname, online FROM devices ORDER BY ip"):
            ip = row[0]
            if ip in scanned_dict:
                inv = scanned_dict[ip]
                if isinstance(inv, dict):
                    inv["device_name"] = device_names.get(ip, "")
                    inv["online"] = device_online.get(ip, 0)
                    inv["device_type"] = device_types.get(ip, "") or inv.get("device_type", "")
                    inv["has_web"] = False
                    inv["web_port"] = None
                    if inv.get("open_ports"):
                        try:
                            ports = json.loads(inv["open_ports"]) if isinstance(inv["open_ports"], str) else inv["open_ports"]
                            for p in ports:
                                if p.get("state") == "open" and p.get("port") in ("80", "443", "8080", "8443", "8081", "8888", "9091", "8000", "3000", "5000"):
                                    inv["has_web"] = True
                                    if p.get("port") in ("443", "8080"):
                                        inv["web_port"] = p.get("port")
                                    elif not inv.get("web_port"):
                                        inv["web_port"] = p.get("port")
                        except Exception:
                            pass
                    if not inv["has_web"] and ip in known_web_ports:
                        inv["has_web"] = True
                        inv["web_port"] = str(known_web_ports[ip])
                    if inv.get("open_ports"):
                        try:
                            raw = inv["open_ports"]
                            all_ports = json.loads(raw) if isinstance(raw, str) else raw
                            inv["open_ports"] = [p for p in all_ports if p.get("state") == "open"]
                        except Exception:
                            pass
                all_devices.append(inv)
            else:
                has_web = ip in known_web_ports
                all_devices.append({
                    "ip": ip, "hostname": row[1] or "", "online": row[2],
                    "device_name": device_names.get(ip, ""), "has_web": has_web,
                    "web_port": str(known_web_ports[ip]) if has_web else None,
                    "open_ports": None, "device_type": device_types.get(ip, ""),
                    "model": None, "manufacturer": None, "last_scan": None, "not_scanned": True
                })
        con.close()
    except Exception:
        pass

    def sort_key(inv):
        online = int(inv.get("online", 0) if isinstance(inv, dict) else getattr(inv, "online", 0) or 0)
        has_web = inv.get("has_web", False) if isinstance(inv, dict) else getattr(inv, "has_web", False)
        open_ports = inv.get("open_ports") if isinstance(inv, dict) else getattr(inv, "open_ports", None)
        has_ports = False
        if open_ports:
            try:
                ports = json.loads(open_ports) if isinstance(open_ports, str) else open_ports
                has_ports = len(ports) > 0
            except Exception:
                pass
        if online and has_web:
            return 0
        elif online and has_ports:
            return 1
        elif online:
            return 2
        else:
            return 3

    all_devices.sort(key=sort_key)
    data["inventories"] = all_devices

    return render_template("inventory.html", **data)


@app.route("/inventory/scan", methods=["POST"])
@login_required
def inventory_scan():
    threading.Thread(target=scan_all_devices, daemon=True).start()
    return redirect(url_for("inventory"))


@app.route("/inventory/device/<ip>")
@login_required
def inventory_device(ip):
    inv = get_inventory(ip)
    return render_template("inventory_device.html", ip=ip, inventory=inv, **page_data())


@app.route("/api/inventory/<ip>")
@login_required
def api_inventory(ip):
    return jsonify(get_inventory(ip))


# ==================== Missing page routes ====================

@app.route("/torrent")
@login_required
def torrent_page():
    return render_template("torrent.html", **page_data())


@app.route("/apps/notes")
@login_required
def app_notes():
    return render_template("apps/notes.html", **page_data())


@app.route("/apps/passwords")
@login_required
def app_passwords():
    return render_template("apps/passwords.html", **page_data())


@app.route("/apps/filemanager")
@login_required
def app_filemanager():
    return render_template("apps/filemanager.html", **page_data())


@app.route("/apps/terminal")
@login_required
def app_terminal():
    return render_template("apps/terminal.html", **page_data())


# ==================== Core routes ====================

from modules.core_routes import register_routes as register_core_routes
register_core_routes(app)


# ==================== Background tasks ====================

import schedule as _schedule


def _schedule_currencies():
    while True:
        _schedule.every(6).hours.do(update_currencies_background)
        _schedule.every(24).hours.do(update_recycling_background)
        while True:
            _schedule.run_pending()
            time.sleep(60)


# ==================== SocketIO ====================

from flask_socketio import SocketIO, emit

socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

from modules.core_routes import register_socketio_handlers
register_socketio_handlers(socketio)

# ==================== Main ====================

if __name__ == "__main__":
    init_inventory_db()
    start_scan_thread()

    threading.Thread(target=update_currencies_background, daemon=True).start()
    threading.Thread(target=update_recycling_background, daemon=True).start()
    threading.Thread(target=_schedule_currencies, daemon=True).start()

    socketio.run(app, host="0.0.0.0", port=8080, allow_unsafe_werkzeug=True)
