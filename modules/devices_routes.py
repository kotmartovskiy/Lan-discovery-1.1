import sqlite3
import re
import subprocess
import threading
import time
import socket
import logging
from datetime import datetime
from flask import render_template, request, redirect, url_for, jsonify

log = logging.getLogger("lan-discovery")

DB = "/opt/lan-discovery/devices.db"


def _subnet():
    from app import _cfg
    return _cfg("network", "subnet", "192.168.3.0/24")


def _scan_interval():
    from app import _cfg
    return int(_cfg("network", "scan_interval", 30) or 30)


def _max_misses():
    from app import _cfg
    return int(_cfg("network", "max_misses", 6) or 6)

_hostname_cache = {}


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


def get_hostname(ip):
    if ip in _hostname_cache:
        return _hostname_cache[ip]

    old_timeout = socket.getdefaulttimeout()
    try:
        socket.setdefaulttimeout(1.5)
        result = socket.gethostbyaddr(ip)[0]
        _hostname_cache[ip] = result
        return result
    except Exception:
        _hostname_cache[ip] = None
        return None
    finally:
        socket.setdefaulttimeout(old_timeout)



def parse_scan(output):

    devices = {}

    current_ip = None

    for line in output.splitlines():

        line = line.strip()

        match = re.search(
            r"Nmap scan report for (.+)",
            line
        )

        if match:

            value = match.group(1)

            ip_match = re.search(
                r"\(([\d.]+)\)",
                value
            )

            if ip_match:

                hostname = value.rsplit(
                    "(",
                    1
                )[0].strip()

                ip = ip_match.group(1)

            else:

                hostname = None
                ip = value.strip()

            current_ip = ip

            devices[ip] = {
                "hostname": hostname,
                "mac": None,
                "vendor": None
            }

            continue

        if current_ip:

            match = re.search(
                r"MAC Address:\s+([0-9A-Fa-f:]{17})\s+\((.*?)\)",
                line
            )

            if match:

                devices[current_ip]["mac"] = \
                    match.group(1).upper()

                devices[current_ip]["vendor"] = \
                    match.group(2)

    return devices


def run_scan():
    import subprocess

    devices = {}
    subnet = _subnet()

    for iface in ["end0", "eth0"]:
        try:
            r = subprocess.run(
                ["nmap", "-sn", "-PR", "-e", iface, "--host-timeout", "3s", subnet],
                capture_output=True, text=True, timeout=45
            )
            if r.returncode == 0:
                ip = None
                for line in r.stdout.splitlines():
                    m = re.search(r"Nmap scan report for (.+)", line)
                    if m:
                        v = m.group(1).strip()
                        ip_m = re.search(r"\(([\d.]+)\)", v)
                        ip = ip_m.group(1) if ip_m else v.strip()
                    elif "MAC Address:" in line and ip:
                        mp = line.split("MAC Address:")[1].strip().split("(")
                        devices[ip] = mp[0].strip()
                        ip = None
                if devices:
                    break
        except FileNotFoundError:
            log.error("SCAN: nmap не установлен — сканирование недоступно")
            return None
        except Exception:
            pass

    if not devices:
        for iface in ["wlan1", "wlan0"]:
            try:
                r = subprocess.run(
                    ["nmap", "-sn", "-PR", "-e", iface, "--host-timeout", "3s", subnet],
                    capture_output=True, text=True, timeout=45
                )
                if r.returncode == 0:
                    ip = None
                    for line in r.stdout.splitlines():
                        m = re.search(r"Nmap scan report for (.+)", line)
                        if m:
                            v = m.group(1).strip()
                            ip_m = re.search(r"\(([\d.]+)\)", v)
                            ip = ip_m.group(1) if ip_m else v.strip()
                        elif "MAC Address:" in line and ip:
                            mp = line.split("MAC Address:")[1].strip().split("(")
                            devices[ip] = mp[0].strip()
                            ip = None
                    if devices:
                        break
            except FileNotFoundError:
                log.error("SCAN: nmap не установлен — сканирование недоступно")
                return None
            except Exception:
                pass

    from app import _cfg
    for self_ip in _cfg("network", "self_ips", ["192.168.3.234", "192.168.3.235"]):
        if self_ip not in devices:
            devices[self_ip] = ""

    if not devices:
        log.warning("SCAN: no hosts found")
        return None

    output = ""
    for ip, mac in devices.items():
        output += f"\nNmap scan report for {ip}\n"
        output += "Host is up.\n"
        if mac:
            output += f"MAC Address: {mac} (Unknown)\n"
    return output.strip()


_scan_status = {"last_scan": None, "last_ok": None, "last_error": None, "errors": 0}


def get_scan_status():
    """Статус скан-потока для /api/health (P1-9)."""
    st = dict(_scan_status)
    st["interval_sec"] = _scan_interval()
    st["thread_alive"] = bool(_scan_thread and _scan_thread.is_alive())
    return st


def scan_loop():

    while True:

        con = None

        try:

            output = run_scan()

            if output is None:

                _scan_status["last_scan"] = datetime.now().strftime(
                    "%d.%m.%Y %H:%M:%S"
                )
                _scan_status["last_error"] = (
                    "сканирование недоступно (см. журнал)"
                )
                _scan_status["errors"] += 1
                time.sleep(_scan_interval())
                continue

            current_devices = parse_scan(output)

            now = datetime.now().strftime(
                "%d.%m.%Y %H:%M:%S"
            )

            con = get_db()

            previous = {

                row[0]: {
                    "online": bool(row[1]),
                    "misses": row[2]
                }

                for row in con.execute(
                    """
                    SELECT ip, online, misses
                    FROM devices
                    """
                ).fetchall()

            }

            # ОБНАРУЖЕННЫЕ УСТРОЙСТВА

            for ip, info in current_devices.items():

                hostname = (
                    info["hostname"]
                    or get_hostname(ip)
                )

                mac = info["mac"]
                vendor = info["vendor"]

                row = con.execute(
                    """
                    SELECT
                        online,
                        hostname,
                        mac,
                        vendor,
                        first_seen,
                        appearances,
                        misses,
                        name
                    FROM devices
                    WHERE ip=?
                    """,
                    (ip,)
                ).fetchone()

                if row:

                    was_online = bool(row[0])

                    old_mac = row[2]
                    mac_changed = (
                        bool(mac) and bool(old_mac)
                        and str(mac).lower() != str(old_mac).lower()
                    )

                    con.execute(
                        """
                        UPDATE devices

                        SET
                            online=1,
                            hostname=?,
                            mac=COALESCE(?, mac),
                            vendor=COALESCE(?, vendor),
                            last_seen=?,
                            misses=0,
                            appearances=appearances+1,
                            name=CASE WHEN ?=1 THEN NULL ELSE name END,
                            device_type=CASE WHEN ?=1 THEN NULL ELSE device_type END

                        WHERE ip=?
                        """,
                        (
                            hostname,
                            mac,
                            vendor,
                            now,
                            1 if mac_changed else 0,
                            1 if mac_changed else 0,
                            ip
                        )
                    )

                    if not was_online:

                        con.execute(
                            """
                            INSERT INTO events
                            (timestamp, ip, hostname, mac, event)

                            VALUES (?, ?, ?, ?, 'ONLINE')
                            """,
                            (
                                now,
                                ip,
                                hostname,
                                mac
                            )
                        )

                else:

                    con.execute(
                        """
                        INSERT INTO devices
                        (
                            ip,
                            online,
                            hostname,
                            mac,
                            vendor,
                            first_seen,
                            last_seen,
                            is_new,
                            appearances,
                            misses,
                            name
                        )

                        VALUES (
                            ?, 1, ?, ?, ?, ?, ?, 1, 1, 0, NULL
                        )
                        """,
                        (
                            ip,
                            hostname,
                            mac,
                            vendor,
                            now,
                            now
                        )
                    )

                    con.execute(
                        """
                        INSERT INTO events
                        (timestamp, ip, hostname, mac, event)

                        VALUES (?, ?, ?, ?, 'NEW')
                        """,
                        (
                            now,
                            ip,
                            hostname,
                            mac
                        )
                    )

            # НЕ ОБНАРУЖЕННЫЕ УСТРОЙСТВА

            for ip, state in previous.items():

                if ip in current_devices:
                    continue

                if not state["online"]:
                    continue

                new_misses = state["misses"] + 1

                if new_misses >= _max_misses():

                    con.execute(
                        """
                        UPDATE devices

                        SET
                            online=0,
                            misses=?

                        WHERE ip=?
                        """,
                        (
                            new_misses,
                            ip
                        )
                    )

                    row = con.execute(
                        """
                        SELECT hostname, mac
                        FROM devices
                        WHERE ip=?
                        """,
                        (ip,)
                    ).fetchone()

                    hostname = row[0] if row else None
                    mac = row[1] if row else None

                    con.execute(
                        """
                        INSERT INTO events
                        (timestamp, ip, hostname, mac, event)

                        VALUES (?, ?, ?, ?, 'OFFLINE')
                        """,
                        (
                            now,
                            ip,
                            hostname,
                            mac
                        )
                    )

                else:

                    con.execute(
                        """
                        UPDATE devices

                        SET misses=?

                        WHERE ip=?
                        """,
                        (
                            new_misses,
                            ip
                        )
                    )

            con.commit()

            _scan_status["last_scan"] = now
            _scan_status["last_ok"] = now

            log.info(f"SCAN OK: {len(current_devices)} devices")

        except Exception as e:

            _scan_status["last_scan"] = datetime.now().strftime(
                "%d.%m.%Y %H:%M:%S"
            )
            _scan_status["last_error"] = str(e)
            _scan_status["errors"] += 1

            log.error(f"SCAN ERROR: {e}")

        finally:
            if con is not None:
                try:
                    con.close()
                except Exception:
                    pass

        time.sleep(_scan_interval())


def register_routes(app):
    from modules.auth import login_required, can_edit

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


_scan_lock = threading.Lock()
_scan_thread = None


def start_scan_thread():
    """Запустить скан-поток; повторный вызов — no-op (P1-8 guard)."""
    global _scan_thread
    with _scan_lock:
        if _scan_thread is not None and _scan_thread.is_alive():
            return _scan_thread
        _scan_thread = threading.Thread(target=scan_loop, daemon=True)
        _scan_thread.start()
        return _scan_thread
