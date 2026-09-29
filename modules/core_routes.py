import os
import json
import time
import subprocess
import threading
import shutil
import socket
import struct
import select
from pathlib import Path
from datetime import datetime


# ==================== Cache dicts ====================

_settings_cache = {"data": None, "ts": 0}
_page_data_cache = {"data": None, "ts": 0}
_iptv_update_status_cache = {"data": None, "ts": 0}
_rate_limits = {}
_inet_cache = {"ok": None, "ts": 0}

IPTV_UPDATE_STATUS = "/etc/lan-discovery/iptv-update-status.json"
NETWORK_CONFIG = "/etc/lan-discovery/network.json"
NOTES_DIR = "/etc/lan-discovery/notes"
SECRETS_DIR = "/etc/lan-discovery/secrets"
SECRETS_KEY_PATH = "/etc/lan-discovery/secret.key"
TRANSMISSION_URL = "http://localhost:9091/transmission/rpc"
TRANSMISSION_USER = ""
TRANSMISSION_PASS = ""
FILEMANAGER_ROOT = "/"

os.makedirs(NOTES_DIR, exist_ok=True)
os.makedirs(SECRETS_DIR, exist_ok=True)


# ==================== Core utility functions ====================

def load_settings():
    from app import SETTINGS_PATH
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
    from app import SETTINGS_PATH
    try:
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        _settings_cache["data"] = data
        _settings_cache["ts"] = time.time()
        return True
    except Exception:
        return False


def _check_rate(action, cooldown):
    now = time.time()
    last = _rate_limits.get(action, 0)
    if now - last < cooldown:
        return False
    _rate_limits[action] = now
    return True


def _cfg(section, key, default=None):
    s = load_settings()
    return s.get(section, {}).get(key, default)


def _cmd(cmd, timeout=5):
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        return result.stdout.strip()
    except Exception:
        return ""


def _read_file(path):
    try:
        return Path(path).read_text().strip()
    except Exception:
        return ""


def _format_dt(dt_str):
    if not dt_str:
        return dt_str
    try:
        dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
        return dt.strftime("%d.%m.%Y %H:%M:%S")
    except Exception:
        pass
    try:
        dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M")
        return dt.strftime("%d.%m.%Y %H:%M")
    except Exception:
        pass
    try:
        parts = dt_str.split()
        if len(parts) >= 6:
            cleaned = " ".join(parts[:5]) + " " + parts[-1]
            dt = datetime.strptime(cleaned, "%a %b %d %I:%M:%S %p %Y")
            return dt.strftime("%d.%m.%Y %H:%M:%S")
    except Exception:
        pass
    try:
        parts = dt_str.split()
        if len(parts) == 3 and len(parts[1]) == 2:
            year = datetime.now().year
            cleaned = f"{parts[0]} {parts[1]} {year} {parts[2]}"
            dt = datetime.strptime(cleaned, "%b %d %Y %H:%M:%S")
            return dt.strftime("%d.%m.%Y %H:%M:%S")
    except Exception:
        pass
    return dt_str


def _human_size(value):
    try:
        value = float(value)
    except Exception:
        return str(value)

    units = ["B", "KiB", "MiB", "GiB", "TiB"]
    i = 0

    while value >= 1024 and i < len(units) - 1:
        value /= 1024
        i += 1

    if i == 0:
        return f"{int(value)} {units[i]}"

    return f"{value:.1f} {units[i]}"


# ==================== IPTV update status ====================

def load_iptv_update_status():
    now = time.time()
    if _iptv_update_status_cache["data"] is not None and now - _iptv_update_status_cache["ts"] < 60:
        return _iptv_update_status_cache["data"]
    try:
        with open(IPTV_UPDATE_STATUS, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, dict):
            return {}

        _iptv_update_status_cache["data"] = data
        _iptv_update_status_cache["ts"] = now
        return data

    except Exception:
        return {}


def save_iptv_update_status(data):
    path = Path(IPTV_UPDATE_STATUS)

    path.parent.mkdir(parents=True, exist_ok=True)

    tmp = path.with_suffix(".tmp")

    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=4
        )
        f.write("\n")

    tmp.replace(path)


# ==================== User helpers ====================

def _hash(pw):
    import bcrypt
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def _verify_hash(pw, stored_hash):
    import bcrypt
    try:
        if stored_hash.startswith("$2"):
            return bcrypt.checkpw(pw.encode(), stored_hash.encode())
    except Exception:
        pass
    import hashlib
    return hashlib.sha256(pw.encode()).hexdigest() == stored_hash


def load_users():
    from app import USERS_PATH
    try:
        with open(USERS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_users(data):
    from app import USERS_PATH
    try:
        with open(USERS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception:
        return False


def get_current_user():
    from flask import session
    from types import SimpleNamespace
    u = session.get("user")
    if not u:
        return None
    users = load_users()
    data = users.get(u)
    if not data:
        return None
    return SimpleNamespace(
        username=u,
        role=data.get("role", "guest"),
        enabled=data.get("enabled", True),
        display_name=data.get("display_name", u),
    )


def get_current_username():
    from flask import session
    return session.get("user")


# ==================== Context processor ====================

def _inject_user():
    from types import SimpleNamespace
    u = get_current_user()
    if not u:
        u = SimpleNamespace(username="", role="guest", enabled=False, display_name="Гость")
    return {"current_user": u, "current_username": get_current_username()}


# ==================== Currency / recycling helpers ====================

def update_currencies_background():
    from modules.currencies import update_all as update_currencies_fn
    try:
        update_currencies_fn()
    except Exception as e:
        from app import log
        log.error(f"CURRENCIES BG ERROR: {e}")


def update_recycling_background():
    from modules.recycling import update_all as update_recycling_fn
    try:
        update_recycling_fn()
    except Exception as e:
        from app import log
        log.error(f"RECYCLING BG ERROR: {e}")


_currency_cache = {"data": None, "recycling": None, "ts": 0, "updating": False}


def _refresh_currency_cache():
    if _currency_cache["updating"]:
        return
    _currency_cache["updating"] = True
    def _do():
        try:
            from modules.currencies import get_latest as get_currency_latest_fn
            from modules.recycling import get_latest as get_recycling_latest_fn
            d = get_currency_latest_fn()
            r = get_recycling_latest_fn()
            _currency_cache["data"] = d
            _currency_cache["recycling"] = r
        except Exception:
            pass
        _currency_cache["updating"] = False
    threading.Thread(target=_do, daemon=True).start()


def get_currency_cached():
    now = time.time()
    if now - _currency_cache["ts"] < 60 and _currency_cache["data"] is not None:
        return _currency_cache["data"], _currency_cache["recycling"]
    _refresh_currency_cache()
    return _currency_cache["data"] or {}, _currency_cache["recycling"] or {}


# ==================== Internet / weather / page_data ====================

def check_internet():
    try:
        result = subprocess.run(
            ["ping", "-c", "1", "-W", "2", "1.1.1.1"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=3
        )
        return result.returncode == 0
    except Exception:
        return False


def check_internet_cached():
    now = time.time()
    if now - _inet_cache["ts"] < 10:
        return _inet_cache["ok"]
    _inet_cache["ok"] = check_internet()
    _inet_cache["ts"] = now
    return _inet_cache["ok"]


def weather_current():
    from app import DB
    import sqlite3
    try:
        con = sqlite3.connect(DB, timeout=5)

        row = con.execute("""
            SELECT
                timestamp,
                temperature,
                apparent_temperature,
                humidity,
                precipitation,
                weather_code,
                wind_speed,
                wind_direction,
                pressure,
                cloud_cover
            FROM weather_observations
            ORDER BY timestamp DESC
            LIMIT 1
        """).fetchone()

        con.close()

        if not row:
            return {}

        return {
            "timestamp": row[0],
            "temperature": row[1],
            "apparent_temperature": row[2],
            "humidity": row[3],
            "precipitation": row[4],
            "weather_code": row[5],
            "wind_speed": row[6],
            "wind_direction": row[7],
            "pressure": row[8],
            "cloud_cover": row[9],
        }
    except Exception:
        return {}


def page_data():
    from app import SCAN_INTERVAL, MAX_MISSES
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


# ==================== Routes ====================

def register_routes(app):
    from flask import render_template, request, redirect, url_for, jsonify, send_file
    from app import login_required, admin_required, can_edit, GAMES_DIR

    # --- Games ---

    @app.route("/games/<path:filename>")
    @login_required
    def serve_game(filename):
        safe = os.path.normpath(filename)
        if safe.startswith("..") or os.path.isabs(safe):
            return "Forbidden", 403
        filepath = os.path.join(GAMES_DIR, safe)
        if not os.path.isfile(filepath):
            return "Not found", 404
        return send_file(filepath, mimetype="text/html")

    # --- Apps page ---

    @app.route("/apps")
    @login_required
    def apps_page():
        return render_template("apps.html", **page_data())

    # --- App pages ---

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

    # --- Help ---

    @app.route("/help")
    @login_required
    def help_page():
        page = page_data()

        return render_template("help.html",
            **page
        )

    # --- Currencies page ---

    @app.route("/currencies")
    @login_required
    def currencies():
        data = page_data()

        currency_data, recycling_data = get_currency_cached()

        currency_updated = ""
        if currency_data:
            for cat_items in currency_data.values():
                if cat_items:
                    currency_updated = cat_items[0].get("fetched_at", "")
                    break

        data["currency_data"] = currency_data
        data["recycling_data"] = recycling_data
        data["currency_updated"] = currency_updated

        return render_template("currencies.html",
            **data
        )

    @app.route("/api/currencies")
    @login_required
    def api_currencies():
        from modules.currencies import get_latest as get_currency_latest
        return jsonify({"usd": get_currency_latest("usd") or {}, "eur": get_currency_latest("eur") or {}})

    # --- Settings ---

    @app.route("/api/settings")
    @login_required
    def api_settings_get():
        return jsonify(load_settings())

    @app.route("/api/settings", methods=["POST"])
    @admin_required
    @login_required
    def api_settings_save():
        data = request.get_json() or {}
        if not data:
            return jsonify({"error": "empty"}), 400
        old = load_settings()
        old.update(data)
        if save_settings(old):
            _settings_cache["ts"] = 0
            return jsonify({"ok": True})
        return jsonify({"error": "save failed"}), 500

    # --- Users ---

    @app.route("/api/users")
    @admin_required
    def api_users_list():
        users = load_users()
        safe = {}
        for name, u in users.items():
            safe[name] = {
                "role": u.get("role"),
                "enabled": u.get("enabled"),
                "display_name": u.get("display_name", name)
            }
        return jsonify(safe)

    @app.route("/api/users/<username>/password", methods=["POST"])
    @admin_required
    def api_user_password(username):
        users = load_users()
        if username not in users:
            return jsonify({"error": "not found"}), 404
        data = request.get_json() or {}
        pw = data.get("password", "").strip()
        if len(pw) < 1:
            return jsonify({"error": "password too short"}), 400
        users[username]["password_hash"] = _hash(pw)
        save_users(users)
        return jsonify({"ok": True})

    @app.route("/api/users/<username>/toggle", methods=["POST"])
    @admin_required
    def api_user_toggle(username):
        users = load_users()
        if username not in users:
            return jsonify({"error": "not found"}), 404
        if users[username].get("role") == "admin":
            return jsonify({"error": "cannot disable admin"}), 400
        users[username]["enabled"] = not users[username].get("enabled", True)
        save_users(users)
        return jsonify({"ok": True, "enabled": users[username]["enabled"]})

    # --- Notes ---

    @app.route("/api/notes", methods=["GET"])
    @login_required
    def api_notes_list():
        idx = _notes_index()
        return {"ok": True, "notes": idx}

    @app.route("/api/notes", methods=["POST"])
    @login_required
    def api_notes_create():
        data = request.json
        title = data.get("title", "Без названия")
        content = data.get("content", "")
        idx = _notes_index()
        note_id = max([n["id"] for n in idx], default=0) + 1
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        note = {"id": note_id, "title": title, "content": content, "created": now, "updated": now}
        idx.append(note)
        _notes_save_index(idx)
        with open(os.path.join(NOTES_DIR, "%d.md" % note_id), "w") as f:
            f.write(content)
        return {"ok": True, "id": note_id}

    @app.route("/api/notes/<int:note_id>", methods=["PUT"])
    @login_required
    def api_notes_update(note_id):
        data = request.json
        idx = _notes_index()
        for n in idx:
            if n["id"] == note_id:
                n["title"] = data.get("title", n["title"])
                n["content"] = data.get("content", n["content"])
                n["updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                _notes_save_index(idx)
                with open(os.path.join(NOTES_DIR, "%d.md" % note_id), "w") as f:
                    f.write(n["content"])
                return {"ok": True}
        return {"ok": False, "error": "Not found"}, 404

    @app.route("/api/notes/<int:note_id>", methods=["DELETE"])
    @login_required
    def api_notes_delete(note_id):
        idx = _notes_index()
        idx = [n for n in idx if n["id"] != note_id]
        _notes_save_index(idx)
        try:
            os.remove(os.path.join(NOTES_DIR, "%d.md" % note_id))
        except Exception:
            pass
        return {"ok": True}

    # --- Secrets / Passwords ---

    @app.route("/api/secrets", methods=["GET"])
    @login_required
    def api_secrets_list():
        secrets = _load_secrets()
        return {"ok": True, "secrets": secrets}

    @app.route("/api/secrets", methods=["POST"])
    @login_required
    def api_secrets_create():
        data = request.json
        secrets = _load_secrets()
        secret_id = max([s["id"] for s in secrets], default=0) + 1
        secret = {
            "id": secret_id,
            "name": data.get("name", ""),
            "login": data.get("login", ""),
            "password": data.get("password", ""),
            "url": data.get("url", ""),
            "notes": data.get("notes", "")
        }
        secrets.append(secret)
        _save_secrets(secrets)
        return {"ok": True, "id": secret_id}

    @app.route("/api/secrets/<int:secret_id>", methods=["PUT"])
    @login_required
    def api_secrets_update(secret_id):
        data = request.json
        secrets = _load_secrets()
        for s in secrets:
            if s["id"] == secret_id:
                s["name"] = data.get("name", s["name"])
                s["login"] = data.get("login", s["login"])
                s["password"] = data.get("password", s["password"])
                s["url"] = data.get("url", s["url"])
                s["notes"] = data.get("notes", s["notes"])
                _save_secrets(secrets)
                return {"ok": True}
        return {"ok": False, "error": "Not found"}, 404

    @app.route("/api/secrets/<int:secret_id>", methods=["DELETE"])
    @login_required
    def api_secrets_delete(secret_id):
        secrets = _load_secrets()
        secrets = [s for s in secrets if s["id"] != secret_id]
        _save_secrets(secrets)
        return {"ok": True}

    # --- File Manager ---

    @app.route("/api/filemanager/list")
    @login_required
    def api_filemanager_list():
        path = request.args.get("path", "/")
        path = os.path.normpath(path)
        if not os.path.exists(path):
            return {"ok": False, "error": "Path not found"}, 404
        if not os.path.isdir(path):
            return {"ok": False, "error": "Not a directory"}, 400
        try:
            entries = []
            for name in sorted(os.listdir(path)):
                full = os.path.join(path, name)
                try:
                    st = os.stat(full)
                    is_dir = os.path.isdir(full)
                    entries.append({
                        "name": name,
                        "is_dir": is_dir,
                        "size": st.st_size if not is_dir else 0,
                        "modified": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M"),
                        "permissions": oct(st.st_mode)[-3:] if os.path.islink(full) else ""
                    })
                except Exception:
                    entries.append({
                        "name": name,
                        "is_dir": False,
                        "size": 0,
                        "modified": "",
                        "permissions": ""
                    })
            entries.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
            return {"ok": True, "path": path, "files": entries}
        except PermissionError:
            return {"ok": False, "error": "Permission denied"}, 403
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @app.route("/api/filemanager/read")
    @login_required
    def api_filemanager_read():
        path = request.args.get("path", "")
        path = os.path.normpath(path)
        if not os.path.exists(path):
            return {"ok": False, "error": "File not found"}, 404
        try:
            with open(path, "r", errors="replace") as f:
                content = f.read(512000)
            return {"ok": True, "content": content, "name": os.path.basename(path)}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @app.route("/api/filemanager/mkdir", methods=["POST"])
    @login_required
    def api_filemanager_mkdir():
        path = request.json.get("path", "")
        try:
            os.makedirs(path, exist_ok=True)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @app.route("/api/filemanager/delete", methods=["POST"])
    @login_required
    def api_filemanager_delete():
        path = request.json.get("path", "")
        try:
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @app.route("/api/filemanager/rename", methods=["POST"])
    @login_required
    def api_filemanager_rename():
        data = request.json
        try:
            os.rename(data["old_path"], data["new_path"])
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @app.route("/api/filemanager/copy", methods=["POST"])
    @login_required
    def api_filemanager_copy():
        data = request.json
        try:
            if os.path.isdir(data["src"]):
                shutil.copytree(data["src"], data["dst"])
            else:
                shutil.copy2(data["src"], data["dst"])
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @app.route("/api/filemanager/move", methods=["POST"])
    @login_required
    def api_filemanager_move():
        data = request.json
        try:
            shutil.move(data["src"], data["dst"])
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}


# ==================== Notes helpers ====================

def _notes_index():
    idx_path = os.path.join(NOTES_DIR, "index.json")
    if os.path.exists(idx_path):
        with open(idx_path, "r") as f:
            return json.load(f)
    return []


def _notes_save_index(idx):
    idx_path = os.path.join(NOTES_DIR, "index.json")
    with open(idx_path, "w") as f:
        json.dump(idx, f, ensure_ascii=False, indent=2)


# ==================== Secrets helpers ====================

def _get_secrets_key():
    if os.path.exists(SECRETS_KEY_PATH):
        with open(SECRETS_KEY_PATH, "rb") as f:
            return f.read()
    key = os.urandom(32)
    os.makedirs(os.path.dirname(SECRETS_KEY_PATH), exist_ok=True)
    with open(SECRETS_KEY_PATH, "wb") as f:
        f.write(key)
    return key


def _secrets_encrypt(text):
    from hashlib import sha256
    key = _get_secrets_key()
    from base64 import b64encode
    from hmac import HMAC
    h = HMAC(key, text.encode(), sha256).digest()
    return b64encode(h[:16] + text.encode()).decode()


def _secrets_decrypt(data):
    from hashlib import sha256
    from base64 import b64decode
    from hmac import HMAC
    key = _get_secrets_key()
    raw = b64decode(data)
    text = raw[16:].decode()
    h = HMAC(key, text.encode(), sha256).digest()
    if h[:16] == raw[:16]:
        return text
    return text


def _secrets_file():
    return os.path.join(SECRETS_DIR, "secrets.json")


def _load_secrets():
    path = _secrets_file()
    if os.path.exists(path):
        with open(path, "r") as f:
            data = json.load(f)
        for s in data:
            if "password" in s and s["password"]:
                try:
                    s["password"] = _secrets_decrypt(s["password"])
                except Exception:
                    pass
        return data
    return []


def _save_secrets(secrets):
    path = _secrets_file()
    for s in secrets:
        if "password" in s and s["password"]:
            s["password"] = _secrets_encrypt(s["password"])
    with open(path, "w") as f:
        json.dump(secrets, f, ensure_ascii=False, indent=2)


# ==================== Alarm helpers ====================

ALARM_FILE = "/etc/lan-discovery/alarms.json"


def _load_alarms():
    try:
        with open(ALARM_FILE, "r") as f:
            return json.load(f)
    except:
        return []


def _save_alarms(alarms):
    with open(ALARM_FILE, "w") as f:
        json.dump(alarms, f, indent=2, ensure_ascii=False)


def _alarm_scheduler():
    import datetime as _dt
    fired = set()
    while True:
        time.sleep(15)
        try:
            now = _dt.datetime.now()
            weekday = now.isoweekday()
            current = now.strftime("%H:%M")
            alarms = _load_alarms()
            for a in alarms:
                if not a.get("enabled"):
                    continue
                if a["time"] != current:
                    fired.discard(a["id"])
                    continue
                if weekday not in a.get("days", []):
                    continue
                if a["id"] in fired:
                    continue
                fired.add(a["id"])
                fpath = a.get("file", "")
                if fpath and os.path.exists(fpath):
                    try:
                        ext = os.path.splitext(fpath)[1].lower()
                        if ext == ".mp3":
                            subprocess.Popen(["mpg123", "-q", fpath])
                        else:
                            subprocess.Popen(["aplay", "-q", fpath])
                    except:
                        pass
                if len(fired) > 100:
                    fired.clear()
        except:
            pass


# ==================== Terminal / SocketIO ====================

_terminal_sessions = {}


def register_socketio_handlers(socketio):
    from flask import request

    @socketio.on("connect")
    def terminal_connect():
        pass

    @socketio.on("terminal_input")
    def terminal_input(data):
        sid = request.sid
        if sid not in _terminal_sessions:
            return
        fd = _terminal_sessions[sid]["fd"]
        try:
            os.write(fd, data.encode())
        except Exception:
            pass

    @socketio.on("terminal_resize")
    def terminal_resize(data):
        sid = request.sid
        if sid not in _terminal_sessions:
            return
        fd = _terminal_sessions[sid]["fd"]
        try:
            import fcntl, termios
            winsize = struct.pack("HHHH", data.get("rows", 24), data.get("cols", 80), 0, 0)
            fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)
        except Exception:
            pass

    @socketio.on("terminal_start")
    def terminal_start(data=None):
        import pty, fcntl, termios
        sid = request.sid

        if sid in _terminal_sessions:
            return

        master_fd, slave_fd = pty.openpty()
        winsize = struct.pack("HHHH", 24, 80, 0, 0)
        fcntl.ioctl(slave_fd, termios.TIOCSWINSZ, winsize)

        pid = os.fork()
        if pid == 0:
            os.close(master_fd)
            os.setsid()
            fcntl.ioctl(slave_fd, termios.TIOCSCTTY, 0)
            os.dup2(slave_fd, 0)
            os.dup2(slave_fd, 1)
            os.dup2(slave_fd, 2)
            os.close(slave_fd)
            os.environ["TERM"] = "xterm-256color"
            os.execvp("/bin/bash", ["/bin/bash", "--login"])
        else:
            os.close(slave_fd)
            _terminal_sessions[sid] = {"fd": master_fd, "pid": pid}

            def read_output():
                while sid in _terminal_sessions:
                    try:
                        r, _, _ = select.select([master_fd], [], [], 0.1)
                        if r:
                            data = os.read(master_fd, 4096)
                            if data:
                                socketio.emit("terminal_output", data.decode("utf-8", errors="replace"), room=sid)
                            else:
                                break
                    except Exception:
                        break
                if sid in _terminal_sessions:
                    socketio.emit("terminal_output", "\r\n\x1b[31mСессия завершена\x1b[0m\r\n", room=sid)

            threading.Thread(target=read_output, daemon=True).start()

    @socketio.on("terminal_stop")
    def terminal_stop():
        sid = request.sid
        if sid in _terminal_sessions:
            sess = _terminal_sessions.pop(sid)
            try:
                os.kill(sess["pid"], 9)
            except Exception:
                pass
            try:
                os.close(sess["fd"])
            except Exception:
                pass

    @socketio.on("disconnect")
    def terminal_disconnect():
        sid = request.sid
        if sid in _terminal_sessions:
            sess = _terminal_sessions.pop(sid)
            try:
                os.kill(sess["pid"], 9)
            except Exception:
                pass
            try:
                os.close(sess["fd"])
            except Exception:
                pass


# ==================== Background tasks ====================

def init_background_tasks(app, socketio, scan_loop_fn=None):
    register_socketio_handlers(socketio)

    if scan_loop_fn:
        threading.Thread(
            target=scan_loop_fn,
            daemon=True
        ).start()

    threading.Thread(
        target=update_currencies_background,
        daemon=True
    ).start()

    threading.Thread(
        target=update_recycling_background,
        daemon=True
    ).start()

    import schedule as sched
    sched.every(6).hours.do(update_currencies_background)
    sched.every(24).hours.do(update_recycling_background)

    def run_schedule():
        while True:
            sched.run_pending()
            time.sleep(60)

    threading.Thread(
        target=run_schedule,
        daemon=True
    ).start()

    threading.Thread(target=_alarm_scheduler, daemon=True).start()
