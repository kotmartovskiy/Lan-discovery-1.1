"""Админка модулей: страница /modules, установка зависимостей, вкл/выкл.

Регистрирует:
  - context_processor: nav_items / help_sections / page (активная вкладка)
  - before_request:    404 для маршрутов выключенных модулей
  - GET  /modules                 — список модулей (только admin)
  - POST /modules/<mid>/install   — установка deps (apt/pip/services/dirs)
  - POST /modules/<mid>/toggle    — включение/выключение модуля
"""
import os
import subprocess
import sys
import time

from flask import redirect, render_template, request

from core.module_loader import (
    discover_modules,
    disabled_prefixes,
    get_module,
    help_sections,
    load_state,
    module_status,
    nav_items,
    active_page,
    record_install_result,
    set_module_status,
)


def _run(cmd, timeout=600):
    try:
        env = dict(os.environ, DEBIAN_FRONTEND="noninteractive")
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)
        out = (p.stdout or "") + (p.stderr or "")
        return p.returncode == 0, out[-4000:]
    except Exception as e:
        return False, str(e)


def _install_manifest(m):
    deps = m.get("deps") or {}
    steps = []
    ok_all = True

    pkgs = deps.get("apt") or []
    if pkgs:
        ok, out = _run(["apt-get", "install", "-y"] + pkgs)
        steps.append("apt install " + " ".join(pkgs) + ": " + ("OK" if ok else "FAIL"))
        if not ok:
            ok_all = False
            steps.append(out[-1500:])

    pypkgs = deps.get("pip") or []
    if pypkgs:
        ok, out = _run([sys.executable, "-m", "pip", "install"] + pypkgs)
        steps.append("pip install " + " ".join(pypkgs) + ": " + ("OK" if ok else "FAIL"))
        if not ok:
            ok_all = False
            steps.append(out[-1500:])

    for d in deps.get("dirs") or []:
        try:
            os.makedirs(d, exist_ok=True)
            steps.append("mkdir %s: OK" % d)
        except Exception as e:
            ok_all = False
            steps.append("mkdir %s: FAIL (%s)" % (d, e))

    for svc in deps.get("services") or []:
        ok, out = _run(["systemctl", "enable", "--now", svc])
        steps.append("service %s: " % svc + ("OK" if ok else "FAIL"))
        if not ok:
            ok_all = False
            steps.append(out[-1500:])

    return {
        "ts": time.strftime("%d.%m.%Y %H:%M:%S"),
        "ok": ok_all,
        "log": steps,
    }


def register_routes(app, login_required, admin_required, page_data):
    @app.context_processor
    def _inject_modules_context():
        return {
            "nav_items": nav_items(),
            "help_sections": help_sections(),
            "page": active_page(request.path),
        }

    @app.before_request
    def _gate_disabled_modules():
        if request.method != "GET":
            return None
        path = request.path
        if path.startswith("/static/") or path == "/login":
            return None
        for pfx in disabled_prefixes():
            if path == pfx or path.startswith(pfx + "/"):
                return ("Модуль отключен", 404)
        return None

    @app.route("/modules")
    @admin_required
    def modules_page():
        state = load_state()
        mods = []
        for m in discover_modules():
            installed, enabled = module_status(m["id"])
            mods.append({
                "m": m,
                "installed": installed,
                "enabled": enabled,
                "last": (state.get(m["id"]) or {}).get("last"),
            })
        return render_template("modules.html", mods=mods, **page_data())

    @app.route("/modules/<mid>/toggle", methods=["POST"])
    @admin_required
    def modules_toggle(mid):
        m = get_module(mid)
        if not m:
            return ("Модуль не найден", 404)
        installed, enabled = module_status(mid)
        if installed:
            set_module_status(mid, enabled=not enabled)
        return redirect("/modules")

    @app.route("/modules/<mid>/install", methods=["POST"])
    @admin_required
    def modules_install(mid):
        m = get_module(mid)
        if not m:
            return ("Модуль не найден", 404)
        installed_before, _ = module_status(mid)
        result = _install_manifest(m)
        record_install_result(mid, result)
        if not installed_before:
            set_module_status(mid, installed=True, enabled=True)
        return redirect("/modules")
