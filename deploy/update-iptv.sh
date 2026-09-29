#!/bin/bash
# Обновление IPTV-плейлистов из /etc/lan-discovery/iptv-playlists.json.
# Аргумент не обязателен: без него — все включённые, с индексом — один плейлист.
# Контракт панели (journal юнита update-iptv.service):
#   === IPTV UPDATE OK: <дд.мм.гггг чч:мм:сс> ===
#   === IPTV UPDATE WITH ERRORS: <дд.мм.гггг чч:мм:сс> ===
# Статус каждого плейлиста — iptv-update-status.json {idx: {status,time,exit_code}}.
set -u
CFG=/etc/lan-discovery/iptv-playlists.json
DEST=/srv/media/IPTV
STATUS=/etc/lan-discovery/iptv-update-status.json
ONLY_INDEX="${1:-}"
NOW_STR="$(date '+%d.%m.%Y %H:%M:%S')"
ERRORS=0
mkdir -p "$DEST"

set_status() { # idx status exit_code
    python3 - "$STATUS" "$1" "$2" "$3" <<'PY'
import datetime
import json
import os
import sys
import tempfile

path, idx, status, code = sys.argv[1:5]
try:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
except Exception:
    data = {}
data[idx] = {
    "status": status,
    "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "exit_code": int(code),
}
d = os.path.dirname(path) or "."
fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
with os.fdopen(fd, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=4)
os.replace(tmp, path)
PY
}

update_one() { # idx url file
    local idx="$1" url="$2" file="$3"
    local dest="$DEST/$(basename "$file")"
    local tmp="$dest.tmp"
    if curl -fL --connect-timeout 15 --max-time 120 -o "$tmp" "$url"; then
        if [ -s "$tmp" ] && ! head -c 512 "$tmp" | grep -qiE '<(!doctype|html)'; then
            mv "$tmp" "$dest"
            chown kot:kot "$dest"
            chmod 664 "$dest"
            sync
            set_status "$idx" "ok" 0
            echo "  [$idx] OK: $(basename "$file")"
            return 0
        fi
        echo "  [$idx] FAIL (пустой файл или HTML): $(basename "$file")"
        set_status "$idx" "error" 2
    else
        echo "  [$idx] FAIL (curl): $(basename "$file")"
        set_status "$idx" "error" 1
    fi
    rm -f "$tmp"
    ERRORS=$((ERRORS + 1))
    return 1
}

FOUND=0
while IFS=$'\t' read -r idx name url file enabled; do
    [ -n "$idx" ] || continue
    if [ -n "$ONLY_INDEX" ] && [ "$idx" != "$ONLY_INDEX" ]; then
        continue
    fi
    FOUND=1
    if [ "$enabled" != "1" ]; then
        echo "  [$idx] пропущен (выключен): $name"
        continue
    fi
    update_one "$idx" "$url" "$file"
done < <(python3 - "$CFG" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as f:
    playlists = json.load(f)
for i, p in enumerate(playlists):
    row = (
        str(i),
        str(p.get("name", "")).replace("\t", " ").replace("\n", " "),
        str(p.get("url", "")).replace("\t", " "),
        str(p.get("file", "")).replace("\t", " ").replace("\n", ""),
        "1" if p.get("enabled") else "0",
    )
    print("\t".join(row))
PY
)

if [ "$FOUND" -eq 0 ]; then
    echo "  плейлист с индексом $ONLY_INDEX не найден"
    exit 1
fi

if [ "$ERRORS" -gt 0 ]; then
    echo "=== IPTV UPDATE WITH ERRORS: $NOW_STR ==="
    exit 1
fi
echo "=== IPTV UPDATE OK: $NOW_STR ==="
exit 0
