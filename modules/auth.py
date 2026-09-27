import hashlib
import json
import os
import time

USERS_PATH = "/etc/lan-discovery/users.json"
SECRET_KEY_PATH = "/etc/lan-discovery/secret.key"

_login_attempts = {}  # ip -> [count, first_attempt_time]


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
    return hashlib.sha256(pw.encode()).hexdigest() == stored_hash


def load_users():
    try:
        with open(USERS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_users(data):
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


def login_required(f):
    from functools import wraps
    from flask import redirect, url_for
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not get_current_user():
            return redirect(url_for("login_page"))
        return f(*args, **kwargs)
    return wrapped


def admin_required(f):
    from functools import wraps
    from flask import jsonify
    @wraps(f)
    def wrapped(*args, **kwargs):
        u = get_current_user()
        if not u or u.role != "admin":
            return jsonify({"error": "forbidden"}), 403
        return f(*args, **kwargs)
    return wrapped


def can_edit(f):
    from functools import wraps
    from flask import jsonify
    @wraps(f)
    def wrapped(*args, **kwargs):
        u = get_current_user()
        if not u or u.role == "guest":
            return jsonify({"error": "forbidden"}), 403
        return f(*args, **kwargs)
    return wrapped


def _check_rate_limit(ip, max_attempts=5, window=300):
    now = time.time()
    if ip in _login_attempts:
        count, first = _login_attempts[ip]
        if now - first > window:
            _login_attempts[ip] = [1, now]
            return True
        if count >= max_attempts:
            return False
        _login_attempts[ip] = [count + 1, first]
        return True
    _login_attempts[ip] = [1, now]
    return True


def _reset_rate_limit(ip):
    _login_attempts.pop(ip, None)


def register_routes(app):
    from flask import request, redirect, url_for, render_template, session, jsonify

    @app.route("/login", methods=["GET", "POST"])
    def login_page():
        error = None
        if request.method == "POST":
            ip = request.remote_addr
            if not _check_rate_limit(ip):
                error = "Слишком много попыток. Подождите 5 минут."
                return render_template("login.html", error=error)
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            users = load_users()
            u = users.get(username)
            if u and u.get("enabled") and _verify_hash(password, u.get("password_hash", "")):
                _reset_rate_limit(ip)
                session["user"] = username
                return redirect(url_for("index"))
            error = "Неверное имя пользователя или пароль"
        return render_template("login.html", error=error)

    @app.route("/logout")
    def logout():
        session.pop("user", None)
        return redirect(url_for("login_page"))
