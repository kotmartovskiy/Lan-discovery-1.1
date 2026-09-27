"""
Standalone Restore Server — минимальный Flask-сервер для восстановления из бэкапов.
Работает на порту 8081, не зависит от основного app.py.
Доступен даже если основной сервис lan-discovery упал.
"""

import os
import sys
import json
import shutil
import subprocess
import sqlite3
import hashlib
import secrets
import time
from pathlib import Path
from datetime import datetime
from flask import Flask, render_template_string, request, redirect, url_for, session, jsonify

# ============================================================
# CONFIG
# ============================================================

PORT = 8081
DB_PATH = "/opt/lan-discovery/devices.db"
DB_BACKUP_DIR = "/srv/backup-db"
DB_BACKUP_PATTERN = "devices_*.db"
EMMC_BACKUP_PATH = "/srv/backup-system/emmc.img.zst"
CREDS_FILE = "/etc/lan-discovery/restore-creds.json"
APP_VERSION = "1.0.0"

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)

# ============================================================
# AUTH
# ============================================================

def _hash_pw(pw):
    return hashlib.sha256(pw.encode()).hexdigest()


def load_creds():
    try:
        with open(CREDS_FILE, "r") as f:
            return json.load(f)
    except Exception:
        # Default: admin / restore2024
        default = {"username": "admin", "password_hash": _hash_pw("restore2024")}
        os.makedirs(os.path.dirname(CREDS_FILE), exist_ok=True)
        with open(CREDS_FILE, "w") as f:
            json.dump(default, f, indent=2)
        return default


def login_required(f):
    from functools import wraps
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not session.get("restore_user"):
            return redirect(url_for("login_page"))
        return f(*args, **kwargs)
    return wrapped


@app.route("/login", methods=["GET", "POST"])
def login_page():
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        creds = load_creds()
        if username == creds.get("username") and _hash_pw(password) == creds.get("password_hash"):
            session["restore_user"] = username
            return redirect(url_for("index"))
        error = "Неверные учётные данные"
    return render_template_string(LOGIN_HTML, error=error)


@app.route("/logout")
def logout():
    session.pop("restore_user", None)
    return redirect(url_for("login_page"))


# ============================================================
# BACKUP LISTING
# ============================================================

def db_backup_list():
    backups = []
    try:
        d = Path(DB_BACKUP_DIR)
        if not d.exists():
            return backups
        for f in sorted(d.glob(DB_BACKUP_PATTERN), reverse=True):
            name = f.name
            size = f.stat().st_size
            mtime = datetime.fromtimestamp(f.stat().st_mtime).strftime("%d.%m.%Y %H:%M:%S")
            backups.append({"name": name, "size": size, "mtime": mtime})
    except Exception:
        pass
    return backups


def human_size(size_bytes):
    if size_bytes >= 1024**3:
        return f"{size_bytes / 1024**3:.1f} GiB"
    if size_bytes >= 1024**2:
        return f"{size_bytes / 1024**2:.1f} MiB"
    if size_bytes >= 1024:
        return f"{size_bytes / 1024:.1f} KiB"
    return f"{size_bytes} B"


def emmc_backup_status():
    try:
        p = Path(EMMC_BACKUP_PATH)
        if not p.exists():
            return {"exists": False}
        size = p.stat().st_size
        mtime = datetime.fromtimestamp(p.stat().st_mtime).strftime("%d.%m.%Y %H:%M:%S")
        return {"exists": True, "size": size, "mtime": mtime}
    except Exception:
        return {"exists": False}


def service_state(service):
    try:
        r = subprocess.run(
            ["systemctl", "is-active", service],
            capture_output=True, text=True, timeout=5
        )
        return r.stdout.strip()
    except Exception:
        return "unknown"


def service_running():
    lan = service_state("lan-discovery")
    return lan in ("active", "activating")


# ============================================================
# ROUTES
# ============================================================

@app.route("/")
@login_required
def index():
    backups = db_backup_list()
    for b in backups:
        b["size_human"] = human_size(b["size"])
    emmc = emmc_backup_status()
    if emmc.get("exists"):
        emmc["size_human"] = human_size(emmc["size"])
    return render_template_string(
        INDEX_HTML,
        backups=backups,
        emmc=emmc,
        lan_running=service_running(),
        db_path=DB_PATH,
        db_exists=os.path.exists(DB_PATH),
    )


@app.route("/api/backups")
@login_required
def api_backups():
    backups = db_backup_list()
    for b in backups:
        b["size_human"] = human_size(b["size"])
    return jsonify({"ok": True, "backups": backups})


@app.route("/api/status")
@login_required
def api_status():
    return jsonify({
        "ok": True,
        "lan_running": service_running(),
        "db_exists": os.path.exists(DB_PATH),
        "emmc": emmc_backup_status(),
    })


@app.route("/api/restore/db", methods=["POST"])
@login_required
def api_restore_db():
    data = request.get_json(silent=True) or {}
    filename = data.get("file", "")

    if not filename or "/" in filename or ".." in filename:
        return jsonify({"ok": False, "error": "Недопустимое имя файла"})

    backup_path = os.path.join(DB_BACKUP_DIR, filename)
    if not os.path.isfile(backup_path):
        return jsonify({"ok": False, "error": "Файл бэкапа не найден"})

    # Verify integrity
    try:
        r = subprocess.run(
            ["sqlite3", backup_path, "PRAGMA integrity_check;"],
            capture_output=True, text=True, timeout=10
        )
        if "ok" not in r.stdout:
            return jsonify({"ok": False, "error": "Бэкап повреждён (integrity check failed)"})
    except Exception as e:
        return jsonify({"ok": False, "error": f"Ошибка проверки: {e}"})

    # Stop service → copy → start
    try:
        subprocess.run(["systemctl", "stop", "lan-discovery"], timeout=15)
        time.sleep(1)
        shutil.copy2(backup_path, DB_PATH)
        time.sleep(0.5)
        subprocess.Popen(["systemctl", "start", "lan-discovery"])
        return jsonify({"ok": True, "message": f"Восстановлено из {filename}"})
    except Exception as e:
        subprocess.Popen(["systemctl", "start", "lan-discovery"])
        return jsonify({"ok": False, "error": f"Ошибка восстановления: {e}"})


@app.route("/api/restore/emmc", methods=["POST"])
@login_required
def api_restore_emmc():
    if not os.path.isfile(EMMC_BACKUP_PATH):
        return jsonify({"ok": False, "error": "Файл бэкапа eMMC не найден"})

    state = service_state("backup-emmc-restore.service")
    if state in ("active", "activating"):
        return jsonify({"ok": False, "error": "Восстановление уже выполняется"})

    try:
        subprocess.Popen(["systemctl", "start", "backup-emmc-restore.service"])
        return jsonify({"ok": True, "message": "Запущено восстановление eMMC. Устройство перезагрузится."})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/api/service/restart", methods=["POST"])
@login_required
def api_restart_lan():
    try:
        subprocess.Popen(["systemctl", "restart", "lan-discovery"])
        return jsonify({"ok": True, "message": "lan-discovery перезапущен"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


# ============================================================
# HTML TEMPLATES
# ============================================================

BASE_CSS = """
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f1117; color: #e0e0e0; min-height: 100vh; }
.header { background: #1a1d27; padding: 16px 24px; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #2a2d3a; }
.header h1 { font-size: 20px; color: #ff6b6b; }
.header h1 span { color: #666; font-weight: 400; font-size: 14px; margin-left: 8px; }
.header a { color: #888; text-decoration: none; font-size: 14px; }
.header a:hover { color: #ff6b6b; }
.container { max-width: 800px; margin: 24px auto; padding: 0 16px; }
.card { background: #1a1d27; border-radius: 12px; padding: 20px; margin-bottom: 16px; border: 1px solid #2a2d3a; }
.card h2 { font-size: 16px; color: #aaa; margin-bottom: 12px; text-transform: uppercase; letter-spacing: 1px; }
.status-ok { color: #4caf50; }
.status-err { color: #ff6b6b; }
.status-warn { color: #ff9800; }
table { width: 100%; border-collapse: collapse; }
th, td { padding: 10px 12px; text-align: left; border-bottom: 1px solid #2a2d3a; }
th { color: #888; font-size: 12px; text-transform: uppercase; }
td { font-size: 14px; }
.btn { display: inline-block; padding: 8px 16px; border-radius: 8px; border: none; cursor: pointer; font-size: 14px; font-weight: 500; transition: all 0.2s; }
.btn-danger { background: #ff6b6b; color: #fff; }
.btn-danger:hover { background: #ff5252; }
.btn-warn { background: #ff9800; color: #fff; }
.btn-warn:hover { background: #f57c00; }
.btn-ok { background: #4caf50; color: #fff; }
.btn-ok:hover { background: #43a047; }
.btn-sm { padding: 5px 12px; font-size: 12px; }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.flash { padding: 12px 16px; border-radius: 8px; margin-bottom: 16px; font-size: 14px; }
.flash-ok { background: #1b3a1b; color: #4caf50; border: 1px solid #2d5a2d; }
.flash-err { background: #3a1b1b; color: #ff6b6b; border: 1px solid #5a2d2d; }
.info-row { display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid #1f222e; font-size: 14px; }
.info-row:last-child { border-bottom: none; }
.info-label { color: #888; }
.warning-box { background: #3a2a1b; border: 1px solid #5a4a2d; border-radius: 8px; padding: 12px 16px; margin-bottom: 16px; color: #ffb74d; font-size: 13px; }
.empty { color: #555; font-style: italic; padding: 20px; text-align: center; }
.login-container { max-width: 360px; margin: 80px auto; }
.login-container h1 { text-align: center; color: #ff6b6b; margin-bottom: 24px; }
.login-container input { width: 100%; padding: 12px; border-radius: 8px; border: 1px solid #2a2d3a; background: #0f1117; color: #e0e0e0; font-size: 14px; margin-bottom: 12px; }
.login-container .btn { width: 100%; padding: 12px; }
"""

LOGIN_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Restore Server — Вход</title>
<style>""" + BASE_CSS + """</style></head>
<body>
<div class="login-container">
  <h1>Emergency Restore</h1>
  <div class="card">
    <form method="POST">
      <input name="username" placeholder="Логин" required autofocus>
      <input name="password" type="password" placeholder="Пароль" required>
      {% if error %}<div class="flash flash-err">{{ error }}</div>{% endif %}
      <button class="btn btn-danger" type="submit">Войти</button>
    </form>
  </div>
  <p style="text-align:center;color:#555;font-size:12px;margin-top:16px">
    Standalone restore server v""" + APP_VERSION + """<br>
    Порт 8081 · Не зависит от основного приложения
  </p>
</div>
</body></html>"""


INDEX_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Emergency Restore Server</title>
<style>""" + BASE_CSS + """
.modal-overlay { display:none; position:fixed; top:0; left:0; right:0; bottom:0; background:rgba(0,0,0,0.7); z-index:100; justify-content:center; align-items:center; }
.modal-overlay.active { display:flex; }
.modal { background:#1a1d27; border:1px solid #2a2d3a; border-radius:12px; padding:24px; max-width:400px; width:90%; text-align:center; }
.modal h3 { margin-bottom:16px; color:#ff9800; }
.modal p { margin-bottom:16px; font-size:14px; color:#aaa; }
.modal .btns { display:flex; gap:12px; justify-content:center; }
</style></head>
<body>

<div class="header">
  <h1>Emergency Restore <span>v""" + APP_VERSION + """</span></h1>
  <a href="/logout">Выйти</a>
</div>

<div class="container">
  {% if flash_ok %}
  <div class="flash flash-ok">{{ flash_ok }}</div>
  {% endif %}
  {% if flash_err %}
  <div class="flash flash-err">{{ flash_err }}</div>
  {% endif %}

  <!-- STATUS -->
  <div class="card">
    <h2>Состояние</h2>
    <div class="info-row">
      <span class="info-label">lan-discovery</span>
      {% if lan_running %}
      <span class="status-ok">● Работает</span>
      {% else %}
      <span class="status-err">● Остановлен</span>
      {% endif %}
    </div>
    <div class="info-row">
      <span class="info-label">База данных</span>
      {% if db_exists %}
      <span class="status-ok">● {{ db_path }}</span>
      {% else %}
      <span class="status-err">● Не найдена</span>
      {% endif %}
    </div>
    <div class="info-row">
      <span class="info-label">eMMC бэкап</span>
      {% if emmc.exists %}
      <span class="status-ok">● {{ emmc.size_human }} ({{ emmc.mtime }})</span>
      {% else %}
      <span class="status-warn">● Нет бэкапа</span>
      {% endif %}
    </div>
    {% if not lan_running %}
    <div style="margin-top:12px">
      <button class="btn btn-ok btn-sm" onclick="restartLan()">Запустить lan-discovery</button>
    </div>
    {% endif %}
  </div>

  <!-- DB RESTORE -->
  <div class="card">
    <h2>Восстановление базы данных</h2>
    {% if backups %}
    <table>
      <thead><tr><th>Файл</th><th>Размер</th><th>Дата</th><th></th></tr></thead>
      <tbody>
      {% for b in backups %}
      <tr>
        <td>{{ b.name }}</td>
        <td>{{ b.size_human }}</td>
        <td>{{ b.mtime }}</td>
        <td><button class="btn btn-danger btn-sm" onclick="confirmDbRestore('{{ b.name }}')">Восстановить</button></td>
      </tr>
      {% endfor %}
      </tbody>
    </table>
    {% else %}
    <div class="empty">Бэкапы базы данных не найдены в {{ db_backup_dir }}</div>
    {% endif %}
  </div>

  <!-- EMC RESTORE -->
  <div class="card">
    <h2>Восстановление eMMC</h2>
    <div class="warning-box">
      ⚠️ Восстановление eMMC перезапишет всю системную область. Устройство будет перезагружено.
    </div>
    {% if emmc.exists %}
    <button class="btn btn-danger" onclick="confirmEmmcRestore()">Восстановить eMMC из бэкапа</button>
    {% else %}
    <button class="btn btn-danger" disabled>Бэкап eMMC не найден</button>
    {% endif %}
  </div>

  <!-- RESTART -->
  <div class="card">
    <h2>Управление</h2>
    <button class="btn btn-ok" onclick="restartLan()">Перезапустить lan-discovery</button>
  </div>
</div>

<!-- CONFIRM DB RESTORE -->
<div class="modal-overlay" id="modal-db">
  <div class="modal">
    <h3>Восстановить базу данных?</h3>
    <p id="modal-db-text"></p>
    <div class="btns">
      <button class="btn btn-danger" id="modal-db-btn">Восстановить</button>
      <button class="btn" style="background:#333;color:#aaa" onclick="closeModals()">Отмена</button>
    </div>
  </div>
</div>

<!-- CONFIRM EMC RESTORE -->
<div class="modal-overlay" id="modal-emmc">
  <div class="modal">
    <h3>Восстановить eMMC?</h3>
    <p>Устройство будет перезагружено. Это займёт несколько минут.</p>
    <div class="btns">
      <button class="btn btn-danger" onclick="doEmmcRestore()">Да, восстановить</button>
      <button class="btn" style="background:#333;color:#aaa" onclick="closeModals()">Отмена</button>
    </div>
  </div>
</div>

<script>
function closeModals() {
  document.querySelectorAll('.modal-overlay').forEach(m => m.classList.remove('active'));
}

function confirmDbRestore(file) {
  document.getElementById('modal-db-text').textContent = 'Восстановить из ' + file + '? Текущая БД будет заменена.';
  document.getElementById('modal-db-btn').onclick = function() { doDbRestore(file); };
  document.getElementById('modal-db').classList.add('active');
}

function doDbRestore(file) {
  closeModals();
  fetch('/api/restore/db', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({file: file})
  }).then(r => r.json()).then(d => {
    if (d.ok) {
      showFlash(d.message, 'ok');
      setTimeout(() => location.reload(), 2000);
    } else {
      showFlash(d.error, 'err');
    }
  }).catch(e => showFlash('Ошибка сети: ' + e, 'err'));
}

function confirmEmmcRestore() {
  document.getElementById('modal-emmc').classList.add('active');
}

function doEmmcRestore() {
  closeModals();
  fetch('/api/restore/emmc', {method: 'POST'}).then(r => r.json()).then(d => {
    if (d.ok) {
      showFlash(d.message, 'ok');
    } else {
      showFlash(d.error, 'err');
    }
  }).catch(e => showFlash('Ошибка сети: ' + e, 'err'));
}

function restartLan() {
  fetch('/api/service/restart', {method: 'POST'}).then(r => r.json()).then(d => {
    if (d.ok) {
      showFlash(d.message, 'ok');
      setTimeout(() => location.reload(), 2000);
    } else {
      showFlash(d.error, 'err');
    }
  }).catch(e => showFlash('Ошибка сети: ' + e, 'err'));
}

function showFlash(text, type) {
  const existing = document.querySelector('.flash-dynamic');
  if (existing) existing.remove();
  const div = document.createElement('div');
  div.className = 'flash flash-' + type + ' flash-dynamic';
  div.textContent = text;
  document.querySelector('.container').prepend(div);
  setTimeout(() => div.remove(), 5000);
}
</script>

</body></html>"""


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    print(f"RESTORE SERVER: Starting on port {PORT}", flush=True)
    print(f"RESTORE SERVER: Credentials file: {CREDS_FILE}", flush=True)
    print(f"RESTORE SERVER: DB backups dir: {DB_BACKUP_DIR}", flush=True)
    app.run(host="0.0.0.0", port=PORT, debug=False)
