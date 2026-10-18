#!/bin/sh
# Включает PVR-клиент tvheadend (pvr.hts) и все plugin.program.* (Wi-Fi, SDR,
# ретро) в БД аддонов kodi: kodi помечает посторонние аддоны enabled=0.
# Нужно после первого старта kodi (когда создана Database/Addons*.db).
# Затем перезапускает kodi.
set -e
KODI_USER=kot
KODI_HOME=$(getent passwd "$KODI_USER" | cut -d: -f6)
DB=$(ls "$KODI_HOME"/.kodi/userdata/Database/Addons*.db 2>/dev/null | tail -1)
if [ -z "$DB" ]; then
  echo "БД аддонов нет — запустите kodi один раз и повторите"
  exit 1
fi
dpkg -s sqlite3 >/dev/null 2>&1 || DEBIAN_FRONTEND=noninteractive apt-get install -y -o Acquire::ForceIPv4=true sqlite3
systemctl stop kodi
sleep 3
sqlite3 "$DB" "UPDATE installed SET enabled=1 WHERE addonID='pvr.hts' OR addonID LIKE 'plugin.program.%';"
systemctl start kodi
echo "pvr.hts и plugin.program.* включены в $DB, kodi перезапущен"
