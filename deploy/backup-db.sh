#!/bin/bash
# Ежедневный бэкап devices.db + конфига панели в /srv/backup-db
# (ротация: старше 14 дней). PHASE 11: config_*.tar.gz — тар
# /etc/lan-discovery, проверка tar tzf; UI-список читает devices_*.db.
set -e
exec /opt/lan-discovery/venv/bin/python - <<'PY'
import glob, os, shutil, tarfile, time, sqlite3
from datetime import datetime

db = "/opt/lan-discovery/devices.db"
cfg_dir = "/etc/lan-discovery"
d = "/srv/backup-db"
os.makedirs(d, exist_ok=True)
ts = datetime.now().strftime("%Y%m%d-%H%M%S")
out = os.path.join(d, "devices_%s.db" % ts)

# --- sqlite online backup + integrity ---
src = sqlite3.connect(db)
dst = sqlite3.connect(out)
src.backup(dst)
dst.close()
src.close()

chk = sqlite3.connect(out).execute("PRAGMA integrity_check").fetchone()[0]
if str(chk).lower() != "ok":
    os.remove(out)
    raise SystemExit("integrity_check failed: %s" % chk)

# --- тар конфига (PHASE 11) ---
cfg_out = os.path.join(d, "config_%s.tar.gz" % ts)
if os.path.isdir(cfg_dir):
    with tarfile.open(cfg_out, "w:gz") as tar:
        tar.add(cfg_dir, arcname="etc-lan-discovery")
    if not tarfile.is_tarfile(cfg_out):
        raise SystemExit("config tar failed: %s" % cfg_out)

# --- ротация 14 дней ---
cutoff = time.time() - 14 * 86400
for pat in ("devices_*.db", "config_*.tar.gz"):
    for f in glob.glob(os.path.join(d, pat)):
        if os.path.getmtime(f) < cutoff:
            os.remove(f)

print("=== DB BACKUP OK: %s -> %s" % (
    datetime.now().strftime("%d.%m.%Y %H:%M:%S"), out))
print("=== CONFIG BACKUP OK: %s" % cfg_out)
PY
