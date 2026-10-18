#!/bin/sh
# tvheadend: пользователь kodi для клиента PVR (htsp).
# Пароль kodi/kodi: passwd-запись (plaintext: клиент шлёт sha1(pass+challenge))
# + ACL-запись (streaming/htsp).
set -e
CONF=/usr/local/share/tvheadend
[ -d "$CONF" ] || { echo "конфиг tvheadend не найден ($CONF)"; exit 1; }
mkdir -p "$CONF/accesscontrol" "$CONF/passwd"
printf '%s\n' "{\"allow\":[\"streaming\",\"htsp\",\"dvr\"],\"enabled\":true,\"index\":\"87a714f0000000000000000000000000\",\"prefix\":[\"0.0.0.0/0\",\"::/0\"],\"username\":\"kodi\"}" > "$CONF/accesscontrol/a0000000000000000000000000000001"
printf '%s\n' "{\"comment\":\"kodi pvr client\",\"enabled\":true,\"password\":\"kodi\",\"username\":\"kodi\"}" > "$CONF/passwd/a0000000000000000000000000000002"
rm -rf "$CONF/access"
rm -f "$CONF/superuser"
chown -R tvheadend:tvheadend "$CONF/accesscontrol" "$CONF/passwd"
systemctl restart tvheadend
echo "tvheadend: пользователь kodi (пароль kodi) создан"
