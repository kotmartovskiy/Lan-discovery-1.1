#!/bin/bash
# Ежедневный бэкап devices.db панели в /srv/backup-db (ротация: старше 14 дней)
set -e
exec /opt/lan-discovery/venv/bin/python - <<'PY'
import glob, os, time, sqlite3
from datetime import datetime

db = "/opt/lan-discovery/devices.db"
d = "/srv/backup-db"
os.makedirs(d, exist_ok=True)
out = os.path.join(d, "devices_%s.db" % datetime.now().strftime("%Y%m%d-%H%M%S"))

src = sqlite3.connect(db)
dst = sqlite3.connect(out)
src.backup(dst)
dst.close()
src.close()

chk = sqlite3.connect(out).execute("PRAGMA integrity_check").fetchone()[0]
if str(chk).lower() != "ok":
    raise SystemExit("integrity_check failed: %s" % chk)

cutoff = time.time() - 14 * 86400
for f in glob.glob(os.path.join(d, "devices_*.db")):
    if os.path.getmtime(f) < cutoff:
        os.remove(f)

print("=== DB BACKUP OK: %s -> %s" % (datetime.now().strftime("%d.%m.%Y %H:%M:%S"), out))
PY
