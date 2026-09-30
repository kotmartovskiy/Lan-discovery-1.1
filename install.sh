#!/usr/bin/env bash
# LAN Discovery — installer для чистых Debian/Armbian систем (PHASE 9).
#
# Идемпотентен: повторный запусок поверх существующей установки ничего
# не ломает (код не перезаписывается, config/БД/юнит только дополняются).
#
# Флаги:
#   --prefix DIR     куда ставить (default: /opt/lan-discovery)
#   --unit-dir DIR   куда класть systemd-юнит (default: /etc/systemd/system)
#   --skip-apt       не трогать apt (пакеты уже есть / тестовое окружение)
#   --no-enable      не делать systemctl enable --now
#   --dry-run        только показать план, ничего не менять
#
# Запуск: sudo ./install.sh   (из каталога с кодом) либо с флагами выше.
set -euo pipefail

PREFIX="/opt/lan-discovery"
UNIT_DIR="/etc/systemd/system"
SETTINGS="/etc/lan-discovery/settings.json"
SKIP_APT=0
NO_ENABLE=0
DRY_RUN=0

usage() {
    sed -n '2,15p' "$0" | sed 's/^# \{0,1\}//'
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --prefix)    PREFIX="${2:?--prefix требует значение}"; shift 2 ;;
        --unit-dir)  UNIT_DIR="${2:?--unit-dir требует значение}"; shift 2 ;;
        --skip-apt)  SKIP_APT=1; shift ;;
        --no-enable) NO_ENABLE=1; shift ;;
        --dry-run)   DRY_RUN=1; shift ;;
        -h|--help)   usage; exit 0 ;;
        *) echo "[install] ERROR: неизвестный флаг: $1" >&2; usage; exit 1 ;;
    esac
done

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

log()  { printf '[install] %s\n' "$*"; }
warn() { printf '[install] WARN: %s\n' "$*" >&2; }
die()  { printf '[install] ERROR: %s\n' "$*" >&2; exit 1; }

# run — в dry-run только печатает план
run() {
    if [[ $DRY_RUN -eq 1 ]]; then
        log "DRY: $*"
    else
        "$@"
    fi
}

need_root() {
    # root нужен для apt и/или юнита в /etc
    if [[ $DRY_RUN -eq 1 ]]; then return 0; fi
    if [[ $SKIP_APT -eq 1 && "$UNIT_DIR" != /etc/* ]]; then return 0; fi
    [[ $EUID -eq 0 ]] || die "нужен root (sudo), либо --skip-apt с пользовательским --unit-dir"
}

# ---------------------------------------------------------------- preflight
step_preflight() {
    log "step: preflight"
    command -v python3 >/dev/null 2>&1 || die "python3 не найден"
    python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' \
        || die "нужен Python >= 3.9 (есть: $(python3 -V))"
    [[ -f "$SCRIPT_DIR/app.py" ]] || die "app.py не найден рядом со install.sh ($SCRIPT_DIR)"
    [[ -f "$SCRIPT_DIR/requirements.txt" ]] || die "requirements.txt не найден рядом со install.sh"
    [[ -f "$SCRIPT_DIR/deploy/lan-discovery.service" ]] \
        || die "deploy/lan-discovery.service не найден"
    need_root
    log "  python $(python3 -V 2>&1 | awk '{print $2}'), prefix=$PREFIX, unit-dir=$UNIT_DIR"
}

# -------------------------------------------------------------------- code
step_code() {
    if [[ "$SCRIPT_DIR" -ef "$PREFIX" ]]; then
        log "step: code — код уже в $PREFIX"
        return
    fi
    if [[ -f "$PREFIX/app.py" ]]; then
        log "step: code — в $PREFIX уже есть app.py, не перезаписываю (обновление — см. docs/Обновление.md)"
        return
    fi
    log "step: code — копирую код в $PREFIX"
    run mkdir -p "$PREFIX"
    for item in app.py core modules templates static games tools deploy \
                requirements.txt requirements-dev.txt pytest.ini install.sh \
                tests; do
        if [[ -e "$SCRIPT_DIR/$item" ]]; then
            run cp -r "$SCRIPT_DIR/$item" "$PREFIX/"
        fi
    done
}

# ------------------------------------------------------------------- deps
step_deps() {
    if [[ $SKIP_APT -eq 1 ]]; then
        log "step: deps — пропущено (--skip-apt)"
        return
    fi
    # python3-cffi/cryptography/bcrypt — без wheel на armhf (armv7l):
    # pip падает на сборке cffi без компилятора, ставим из Debian в
    # системный site, venv создаётся с --system-site-packages (PHASE 4).
    local pkgs=(nmap traceroute dnsutils iw bluez smartmontools ffmpeg mpv
                python3-venv python3-cffi python3-cryptography python3-bcrypt)
    local missing=()
    for p in "${pkgs[@]}"; do
        dpkg -s "$p" >/dev/null 2>&1 || missing+=("$p")
    done
    if [[ ${#missing[@]} -eq 0 ]]; then
        log "step: deps — все пакеты уже установлены"
        return
    fi
    log "step: deps — apt-get install ${missing[*]}"
    run apt-get update -qq
    run apt-get install -y "${missing[@]}"
}

# ------------------------------------------------------------------- venv
step_venv() {
    local venv="$PREFIX/venv"
    if [[ ! -x "$venv/bin/python" ]]; then
        log "step: venv — создаю $venv (--system-site-packages: apt-пакеты cffi/cryptography/bcrypt)"
        run python3 -m venv --system-site-packages "$venv"
    else
        log "step: venv — уже есть"
    fi
    log "step: pip — установка зависимостей (requirements.txt)"
    run "$venv/bin/python" -m pip install --quiet -r "$PREFIX/requirements.txt"
}

# ------------------------------------------------------------------ config
step_config() {
    if [[ -f "$SETTINGS" ]]; then
        log "step: config — уже есть ($SETTINGS), не трогаю"
        return
    fi
    log "step: config — создаю базовый $SETTINGS (авто-subnet из интерфейсов)"
    if [[ $DRY_RUN -eq 1 ]]; then
        log "DRY: запись базового settings.json в $SETTINGS"
        return
    fi
    mkdir -p "$(dirname "$SETTINGS")"
    python3 - "$SETTINGS" <<'PYEOF'
import ipaddress, json, subprocess, sys

subnet = None
self_ips = []
try:
    out = subprocess.run(
        ["ip", "-4", "-o", "addr", "show", "scope", "global"],
        capture_output=True, text=True, timeout=10,
    ).stdout
except Exception:
    out = ""
pref = "24"
for line in out.splitlines():
    parts = line.split()
    if "inet" not in parts:
        continue
    cidr = parts[parts.index("inet") + 1]
    ip, pref = cidr.split("/")
    self_ips.append(ip)
if self_ips:
    subnet = str(ipaddress.ip_network(f"{self_ips[0]}/{pref}", strict=False))

cfg = {
    "network": {
        "subnet": subnet or "192.168.3.0/24",
        "scan_interval": 30,
        "max_misses": 6,
        "self_ips": self_ips,
    },
    "web": {"flask_port": 8080},
}
with open(sys.argv[1], "w", encoding="utf-8") as f:
    json.dump(cfg, f, indent=2, ensure_ascii=False)
print(f"[install]   subnet={cfg['network']['subnet']} self_ips={self_ips}")
PYEOF
}

# --------------------------------------------------------------------- db
step_db() {
    log "step: db — init схемы (миграции/ensure/retention; идемпотентно)"
    [[ "$PREFIX" == "/opt/lan-discovery" ]] \
        || warn "префикс нестандартный ($PREFIX): БД создаётся по пути из кода /opt/lan-discovery/devices.db"
    run bash -c "cd '$PREFIX' && ./venv/bin/python -c 'from modules.devices_routes import init_db_schema; init_db_schema()'"
}

# -------------------------------------------------------------------- unit
step_unit() {
    local src="$PREFIX/deploy/lan-discovery.service"
    [[ -f "$src" ]] || src="$SCRIPT_DIR/deploy/lan-discovery.service"
    local dst="$UNIT_DIR/lan-discovery.service"
    [[ -f "$src" ]] || die "нет шаблона юнита: $src"
    log "step: unit — установка $dst (ExecStart: $PREFIX/venv/...)"
    if [[ $DRY_RUN -eq 1 ]]; then
        log "DRY: sed '{PREFIX}→$PREFIX' $src > $dst"
        return
    fi
    mkdir -p "$UNIT_DIR"
    sed "s|{PREFIX}|$PREFIX|g" "$src" > "$dst"
    if [[ "$UNIT_DIR" == /etc/* ]] && command -v systemctl >/dev/null 2>&1; then
        systemctl daemon-reload
        if [[ $NO_ENABLE -eq 1 ]]; then
            log "step: unit — enable пропущен (--no-enable)"
        else
            systemctl enable --now lan-discovery
            log "step: unit — enable --now выполнен"
        fi
    else
        log "step: unit — systemd-шаг пропущен (нет systemctl или не-/etc unit-dir)"
    fi
}

# ------------------------------------------------------------------ health
step_health() {
    local port="${2:-8080}"
    log "step: health — жду http://127.0.0.1:$port/api/health (до 60 с)"
    if [[ $DRY_RUN -eq 1 ]]; then
        log "DRY: curl -fsS http://127.0.0.1:$port/api/health"
        return
    fi
    local i
    for i in $(seq 1 30); do
        if curl -fsS --max-time 3 "http://127.0.0.1:$port/api/health" >/dev/null 2>&1; then
            log "step: health — OK (панель отвечает)"
            return
        fi
        sleep 2
    done
    die "панель не отвечает на 127.0.0.1:$port — см. systemctl status lan-discovery / journalctl -u lan-discovery"
}

# ------------------------------------------------------------------ итог
summary() {
    log "----------------------------------------------------------"
    log "Готово: LAN Discovery установлен в $PREFIX"
    log "  статус:   systemctl status lan-discovery"
    log "  журнал:   journalctl -u lan-discovery -f"
    log "  панель:   http://<IP-машины>:8080  (admin/1234 — смените пароль!)"
    if [[ $DRY_RUN -eq 1 ]]; then
        log "  (dry-run: изменения не применялись)"
    fi
    return 0
}

main() {
    log "LAN Discovery installer$([[ $DRY_RUN -eq 1 ]] && echo ' [DRY-RUN]')"
    step_preflight
    step_code
    step_deps
    step_venv
    step_config
    step_db
    step_unit
    step_health
    summary
}

main
