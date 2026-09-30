import sqlite3
import threading
import logging
from datetime import datetime
from flask import render_template, request, redirect, url_for, jsonify

log = logging.getLogger("lan-discovery")

DB = "/opt/lan-discovery/devices.db"

# Discovery engine (PHASE 6): движок вынесен в core/discovery.py.
# Реэкспорт — обратная совместимость: app.py / system_routes импортируют
# эти символы из devices_routes.
from core.discovery import (  # noqa: F401
    get_hostname,
    get_scan_status,
    parse_scan,
    run_scan,
    scan_loop,
    start_scan_thread,
)

SCHEMA_VERSION = 1
_init_lock = threading.Lock()
_init_done = False


def init_db_schema(force=False):
    """Однократная инициализация схемы (P1-7).

    DDL, миграции колонок, индекс events(ip,id) и PRAGMA user_version
    выполняются только здесь — не в каждом get_db().
    """
    global _init_done
    with _init_lock:
        if _init_done and not force:
            return False
        con = sqlite3.connect(DB, timeout=30)
        try:
            con.execute("PRAGMA busy_timeout=30000")
            con.execute("PRAGMA journal_mode=WAL")

            con.execute("""
                CREATE TABLE IF NOT EXISTS devices (
                    ip TEXT PRIMARY KEY,
                    online INTEGER DEFAULT 0,
                    hostname TEXT,
                    mac TEXT,
                    vendor TEXT,
                    first_seen TEXT,
                    last_seen TEXT,
                    is_new INTEGER DEFAULT 0,
                    appearances INTEGER DEFAULT 0,
                    misses INTEGER DEFAULT 0,
                    name TEXT
                )
            """)

            con.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    ip TEXT,
                    hostname TEXT,
                    mac TEXT,
                    event TEXT
                )
            """)

            columns = {
                row[1]
                for row in con.execute(
                    "PRAGMA table_info(devices)"
                ).fetchall()
            }

            migrations = (
                ("hostname", "ALTER TABLE devices ADD COLUMN hostname TEXT"),
                ("is_new", "ALTER TABLE devices ADD COLUMN is_new INTEGER DEFAULT 0"),
                ("appearances", "ALTER TABLE devices ADD COLUMN appearances INTEGER DEFAULT 0"),
                ("misses", "ALTER TABLE devices ADD COLUMN misses INTEGER DEFAULT 0"),
                ("name", "ALTER TABLE devices ADD COLUMN name TEXT"),
                ("device_type", "ALTER TABLE devices ADD COLUMN device_type TEXT"),
            )
            for col, stmt in migrations:
                if col not in columns:
                    con.execute(stmt)

            con.execute(
                "CREATE INDEX IF NOT EXISTS idx_events_ip_id "
                "ON events(ip, id)"
            )

            version = con.execute("PRAGMA user_version").fetchone()[0]
            if version < SCHEMA_VERSION:
                con.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

            con.commit()
            _init_done = True
            log.info(f"DB SCHEMA INIT: version={SCHEMA_VERSION}")
            return True
        finally:
            con.close()


def get_db():
    if not _init_done:
        init_db_schema()
    con = sqlite3.connect(
        DB,
        timeout=30
    )

    con.execute("PRAGMA busy_timeout=30000")
    con.execute("PRAGMA journal_mode=WAL")

    return con


def register_routes(app):
    from modules.auth import login_required, can_edit, admin_required

    @app.route("/")
    @login_required
    def index():

        con = get_db()
        try:
            devices = con.execute(
                """
                SELECT
                    ip,
                    online,
                    name,
                    hostname,
                    mac,
                    vendor,
                    first_seen,
                    last_seen,
                    misses,
                    appearances,
                    is_new,
                    device_type
                FROM devices

                ORDER BY
                    is_new DESC,
                    online DESC,
                    ip
                """
            ).fetchall()

            total = len(devices)

            online = sum(
                1
                for d in devices
                if d[1]
            )
        finally:
            con.close()

        prepared = []

        for d in devices:

            prepared.append(
                (
                    d[0],
                    d[1],
                    d[2],
                    d[3],
                    d[4],
                    d[5],
                    d[6],
                    d[7],
                    d[8],
                    d[9],
                    d[10]
                )
            )

        from app import page_data
        data = page_data()

        return render_template("devices.html",
            devices=prepared,
            total=total,
            online=online,
            **data
        )

    @app.route("/history")
    @login_required
    def history():

        con = get_db()
        try:
            events = con.execute(
                """
                SELECT
                    timestamp,
                    ip,
                    hostname,
                    mac,
                    event

                FROM events

                ORDER BY id DESC

                LIMIT 500
                """
            ).fetchall()
        finally:
            con.close()

        from app import page_data
        data = page_data()

        return render_template("history.html",
            events=events,
            **data
        )

    @app.route("/device/<ip>")
    @login_required
    def device(ip):

        con = get_db()
        try:
            device = con.execute(
                """
                SELECT
                    ip,
                    online,
                    name,
                    hostname,
                    mac,
                    vendor,
                    first_seen,
                    last_seen,
                    misses,
                    appearances,
                    is_new,
                    device_type
                FROM devices
                WHERE ip=?
                """,
                (ip,)
            ).fetchone()

            if not device:

                return "Устройство не найдено", 404

            events = con.execute(
                """
                SELECT
                    timestamp,
                    event

                FROM events

                WHERE ip=?

                ORDER BY id DESC

                LIMIT 100
                """,
                (ip,)
            ).fetchall()
        finally:
            con.close()

        from app import page_data
        data = page_data()

        return render_template("device.html",
            device=device,
            events=events,
            **data
        )

    @app.route("/device/<ip>/name", methods=["POST"])
    @can_edit
    @login_required
    def set_name(ip):

        name = request.form.get(
            "name",
            ""
        ).strip()

        device_type = request.form.get(
            "device_type",
            ""
        ).strip()

        con = get_db()
        try:
            con.execute(
                """
                UPDATE devices
                SET name=?, device_type=?
                WHERE ip=?
                """,
                (
                    name if name else None,
                    device_type if device_type else None,
                    ip
                )
            )

            con.commit()
        finally:
            con.close()

        return redirect(
            url_for(
                "device",
                ip=ip
            )
        )

    @app.route("/api/device/<ip>/dismiss-new", methods=["POST"])
    @can_edit
    @login_required
    def dismiss_new(ip):
        con = get_db()
        try:
            con.execute("UPDATE devices SET is_new=0 WHERE ip=?", (ip,))
            con.commit()
        finally:
            con.close()
        return jsonify({"ok": True})

    @app.route("/api/scan", methods=["POST"])
    @admin_required
    def api_scan():
        """Ручное сканирование (P6-2): one-shot, не пишет settings.

        Тело (JSON, опционально): {"subnet": "192.168.1.0/24",
        "ifaces": ["eth0"]}. Без параметров — текущая конфигурация.
        """
        from core.discovery import reconcile

        data = request.get_json(silent=True) or {}
        subnet = (data.get("subnet") or "").strip() or None
        ifaces = data.get("ifaces")
        if ifaces is not None and (
            not isinstance(ifaces, list)
            or not ifaces
            or not all(isinstance(i, str) and i.strip() for i in ifaces)
        ):
            return jsonify(
                {"ok": False, "error": "ifaces: непустой список строк"}
            ), 400
        if ifaces:
            ifaces = [i.strip() for i in ifaces]

        out = run_scan(subnet=subnet, ifaces=ifaces)
        if out is None:
            return jsonify({
                "ok": False,
                "error": "сканирование недоступно (см. журнал)",
            }), 503

        current = parse_scan(out)
        now = datetime.now().strftime("%d.%m.%Y %H:%M:%S")

        con = get_db()
        try:
            stats = reconcile(con, current, now)
            con.commit()
        finally:
            con.close()

        return jsonify({
            "ok": True,
            "devices": len(current),
            "stats": stats,
            "subnet": subnet or _current_subnet(),
        })


def _current_subnet():
    from app import _cfg
    return _cfg("network", "subnet", "192.168.3.0/24")
