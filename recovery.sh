#!/usr/bin/env bash
# LAN Discovery — восстановление из бэкапов (PHASE 11).
#
# Собирает систему из трёх частей: код (tar из update.sh-бэкапа),
# конфиг (/etc/lan-discovery из config_*.tar.gz) и БД (devices_*.db из
# /srv/backup-db). Verify: py_compile + sqlite integrity/версия/счётчики.
#
# Флаги:
#   --db FILE         файл БД (default: последний /srv/backup-db/devices_*.db)
#   --code-tar FILE   tar кода (default: последний
#                     /var/backups/lan-discovery/*/code.tar.gz)
#   --config-tar FILE tar конфига (default: последний
#                     /srv/backup-db/config_*.tar.gz)
#   --config-dir DIR  куда распаковать конфиг (default: /etc/lan-discovery)
#   --prefix DIR      куда восстановить код+БД (default: /opt/lan-discovery)
#   --unit            восстановить и systemd-юнит (ExecStart под --prefix)
#   --unit-dir DIR    куда класть юнит (default: /etc/systemd/system)
#   --no-restart      не рестартовать/не health-чекать сервис
#   --dry-run         только показать план
#
# Запуск: sudo ./recovery.sh          (боевое восстановление)
#         sudo ./recovery.sh --prefix /tmp/drill --config-dir /tmp/drill/etc \
#             --unit --no-restart     (дрил, боевые данные не трогаются)
set -euo pipefail

PREFIX="/opt/lan-discovery"
CONFIG_DIR="/etc/lan-discovery"
UNIT_DIR="/etc/systemd/system"
DB_SRC=""
CODE_TAR=""
CONFIG_TAR=""
DO_UNIT=0
DO_RESTART=1
DRY_RUN=0

usage() { sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; }

while [[ $# -gt 0 ]]; do
    case "$1" in
        --db)         DB_SRC="${2:?}"; shift 2 ;;
        --code-tar)   CODE_TAR="${2:?}"; shift 2 ;;
        --config-tar) CONFIG_TAR="${2:?}"; shift 2 ;;
        --config-dir) CONFIG_DIR="${2:?}"; shift 2 ;;
        --prefix)     PREFIX="${2:?}"; shift 2 ;;
        --unit)       DO_UNIT=1; shift ;;
        --unit-dir)   UNIT_DIR="${2:?}"; shift 2 ;;
        --no-restart) DO_RESTART=0; shift ;;
        --dry-run)    DRY_RUN=1; shift ;;
        -h|--help)    usage; exit 0 ;;
        *) echo "[recovery] ERROR: неизвестный флаг: $1" >&2; usage; exit 1 ;;
    esac
done

log()  { printf '[recovery] %s\n' "$*"; }
warn() { printf '[recovery] WARN: %s\n' "$*" >&2; }
die()  { printf '[recovery] ERROR: %s\n' "$*" >&2; exit 1; }

run() { if [[ $DRY_RUN -eq 1 ]]; then log "DRY: $*"; else "$@"; fi; }

latest() {  # latest <dir> <glob> — последний путь (ls -1d: без листинга
            # содержимого каталогов и без multi-arg заголовков)
    ls -1d "$1"/$2 2>/dev/null | sort | tail -1
}

[[ $EUID -eq 0 || $DRY_RUN -eq 1 ]] \
    || die "нужен root (sudo)"

# --------------------------------------------------------------- источники
resolve_sources() {
    log "step: sources"
    if [[ -z "$DB_SRC" ]]; then
        DB_SRC=$(latest /srv/backup-db 'devices_*.db')
        [[ -n "$DB_SRC" ]] || die "нет бэкапов devices_*.db в /srv/backup-db (укажите --db)"
    fi
    [[ -f "$DB_SRC" ]] || die "нет файла БД: $DB_SRC"

    if [[ -z "$CODE_TAR" ]]; then
        local bdir
        bdir=$(latest /var/backups/lan-discovery '20*')
        if [[ -n "$bdir" ]]; then
            # bdir — уже полный путь каталога-бэкапа
            CODE_TAR=$(latest "$bdir" 'code.tar.gz')
        fi
        [[ -n "$CODE_TAR" ]] || die "нет code.tar.gz в /var/backups/lan-discovery (укажите --code-tar)"
    fi
    [[ -f "$CODE_TAR" ]] || die "нет файла: $CODE_TAR"

    if [[ -z "$CONFIG_TAR" ]]; then
        CONFIG_TAR=$(latest /srv/backup-db 'config_*.tar.gz')
        if [[ -z "$CONFIG_TAR" ]]; then
            warn "config_*.tar.gz не найден — конфиг восстановлен не будет"
        fi
    fi
    if [[ -n "$CONFIG_TAR" && ! -f "$CONFIG_TAR" ]]; then
        die "нет файла: $CONFIG_TAR"
    fi
    log "  db:     $DB_SRC"
    log "  code:   $CODE_TAR"
    log "  config: ${CONFIG_TAR:-—}"
    log "  prefix: $PREFIX"
    log "  config-dir: $CONFIG_DIR"
}

# ------------------------------------------------------------------ restore
restore_code() {
    log "step: code — распаковка в $PREFIX"
    run mkdir -p "$PREFIX"
    run tar xzf "$CODE_TAR" -C "$PREFIX"
}

restore_db() {
    log "step: db — копия в $PREFIX/devices.db"
    run cp "$DB_SRC" "$PREFIX/devices.db"
}

restore_config() {
    if [[ -z "$CONFIG_TAR" ]]; then
        log "step: config — пропущен (нет tar)"
        return
    fi
    log "step: config — распаковка в $CONFIG_DIR"
    if [[ $DRY_RUN -eq 1 ]]; then
        log "DRY: tar xzf $CONFIG_TAR → $CONFIG_DIR"
        return
    fi
    local tmp
    tmp=$(mktemp -d)
    tar xzf "$CONFIG_TAR" -C "$tmp"
    mkdir -p "$CONFIG_DIR"
    cp -r "$tmp"/etc-lan-discovery/. "$CONFIG_DIR/"
    rm -rf "$tmp"
    log "  восстановлено $(ls -1 "$CONFIG_DIR" | wc -l) элементов"
}

restore_unit() {
    local src="$PREFIX/deploy/lan-discovery.service"
    [[ -f "$src" ]] || src="$(dirname "$0")/deploy/lan-discovery.service"
    [[ -f "$src" ]] || die "нет шаблона юнита"
    local dst="$UNIT_DIR/lan-discovery.service"
    log "step: unit — $dst (ExecStart: $PREFIX/venv/...)"
    if [[ $DRY_RUN -eq 1 ]]; then log "DRY: sed + cp → $dst"; return; fi
    mkdir -p "$UNIT_DIR"
    sed "s|{PREFIX}|$PREFIX|g" "$src" > "$dst"
    if [[ "$UNIT_DIR" == /etc/* ]] && command -v systemctl >/dev/null 2>&1; then
        systemctl daemon-reload
    fi
    log "  юнит записан"
}

# ------------------------------------------------------------------- verify
do_verify() {
    log "step: verify — py_compile + sqlite integrity"
    if [[ $DRY_RUN -eq 1 ]]; then
        log "DRY: python3 -m py_compile + PRAGMA integrity_check"
        return 0
    fi
    python3 - "$PREFIX" <<'EOF'
import pathlib, py_compile, sqlite3, sys

root = pathlib.Path(sys.argv[1])
files = [root / "app.py"]
files += sorted((root / "core").rglob("*.py"))
files += sorted((root / "modules").rglob("*.py"))
bad = []
for f in files:
    try:
        py_compile.compile(str(f), doraise=True)
    except Exception as e:
        bad.append(f"{f}: {e}")
if bad:
    print("SYNTAX FAIL:\n" + "\n".join(bad), file=sys.stderr)
    sys.exit(1)
print(f"SYNTAX OK ({len(files)} files)")

db = root / "devices.db"
con = sqlite3.connect(db)
chk = con.execute("PRAGMA integrity_check").fetchone()[0]
ver = con.execute("PRAGMA user_version").fetchone()[0]
dev = con.execute("SELECT COUNT(*) FROM devices").fetchone()[0]
ev = con.execute("SELECT COUNT(*) FROM events").fetchone()[0]
con.close()
if str(chk).lower() != "ok":
    print(f"DB INTEGRITY FAIL: {chk}", file=sys.stderr)
    sys.exit(1)
if dev <= 0:
    print("DB EMPTY: devices=0", file=sys.stderr)
    sys.exit(1)
print(f"DB OK (integrity=ok user_version={ver} devices={dev} events={ev})")
EOF
}

restart_health() {
    if [[ $DO_RESTART -eq 0 ]]; then
        log "step: restart — пропущен (--no-restart)"
        return
    fi
    [[ "$PREFIX" == "/opt/lan-discovery" ]] \
        || { warn "префикс нестандартный — restart/health пропущены"; return; }
    log "step: restart — systemctl restart lan-discovery"
    systemctl restart lan-discovery
    log "step: health — жду http://127.0.0.1:8080/api/health (до 60 с)"
    local i
    for i in $(seq 1 30); do
        curl -fsS --max-time 3 http://127.0.0.1:8080/api/health \
            >/dev/null 2>&1 && { log "step: health — OK"; return 0; }
        sleep 2
    done
    die "health не прошёл — см. journalctl -u lan-discovery"
}

main() {
    log "LAN Discovery recovery$([[ $DRY_RUN -eq 1 ]] && echo ' [DRY-RUN]')"
    resolve_sources
    restore_code
    restore_db
    restore_config
    if [[ $DO_UNIT -eq 1 ]]; then
        restore_unit
    fi
    do_verify
    restart_health
    log "----------------------------------------------------------"
    log "Готово: восстановление завершено в $PREFIX"
    log "  БД: $DB_SRC"
    log "  конфиг: ${CONFIG_TAR:-—}"
    log "  проверка: systemctl status lan-discovery; curl /api/health"
    return 0
}

main
