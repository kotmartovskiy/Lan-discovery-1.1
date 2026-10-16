#!/bin/sh
# Kodi-набор lan-discovery: автозапуск Kodi + Wi-Fi-аддон + SDR-радио.
# Полностью повторяем на аналогичном устройстве Armbian/Debian:
#   sh install.sh [--user <юзер>] [--no-enable]
#
# Ставит (если нет): kodi, ffmpeg, rtl-sdr, python3.
# Конфиги: kodi.service, sudoers nmcli, udev rtl-sdr, addons, favorites.
set -e

KODI_USER=kot
ENABLE=1
while [ $# -gt 0 ]; do
  case "$1" in
    --user) KODI_USER="$2"; shift 2 ;;
    --no-enable) ENABLE=0; shift ;;
    *) echo "unknown arg: $1"; exit 2 ;;
  esac
done

HERE=$(cd "$(dirname "$0")" && pwd)
KODI_HOME=$(getent passwd "$KODI_USER" | cut -d: -f6)
[ -n "$KODI_HOME" ] || { echo "нет юзера $KODI_USER"; exit 1; }

[ "$(id -u)" = "0" ] || { echo "запускать от root"; exit 1; }

echo "== apt (только недостающее) =="
MISSING=""
for p in kodi ffmpeg rtl-sdr python3; do
  dpkg -s "$p" >/dev/null 2>&1 || MISSING="$MISSING $p"
done
if [ -n "$MISSING" ]; then
  apt-get update -o Acquire::ForceIPv4=true
  DEBIAN_FRONTEND=noninteractive apt-get install -y -o Acquire::ForceIPv4=true $MISSING
else
  echo "всё установлено"
fi

echo "== стример =="
install -m 755 "$HERE/sdr_radio.py" /usr/local/bin/sdr_radio.py

echo "== udev rtl-sdr =="
rm -f /etc/udev/rules.d/20-rtlsdr.rules
install -m 644 "$HERE/90-rtlsdr.rules" /etc/udev/rules.d/90-rtlsdr.rules
udevadm control --reload-rules
udevadm trigger --subsystem-match=usb || true

echo "== группа plugdev =="
id -nG "$KODI_USER" | grep -qw plugdev || usermod -aG plugdev "$KODI_USER"

echo "== sudoers nmcli =="
visudo -cf "$HERE/sudoers-lan-bridge" >/dev/null
install -m 440 "$HERE/sudoers-lan-bridge" /etc/sudoers.d/lan-bridge

echo "== аддоны Kodi =="
install -d -o "$KODI_USER" -g "$KODI_USER" "$KODI_HOME/.kodi/addons"
rm -rf "$KODI_HOME/.kodi/addons/plugin.program.wifi-settings" \
       "$KODI_HOME/.kodi/addons/plugin.program.sdr-radio"
cp -r "$HERE/addon-wifi/plugin.program.wifi-settings" "$KODI_HOME/.kodi/addons/"
cp -r "$HERE/addon-sdr/plugin.program.sdr-radio" "$KODI_HOME/.kodi/addons/"
python3 "$HERE/make_icons.py" \
  "$KODI_HOME/.kodi/addons/plugin.program.wifi-settings/icon.png" \
  "$KODI_HOME/.kodi/addons/plugin.program.sdr-radio/icon.png"

echo "== избранное (ярлыки в главном меню) =="
install -d -o "$KODI_USER" -g "$KODI_USER" "$KODI_HOME/.kodi/userdata"
if [ -f "$KODI_HOME/.kodi/userdata/favorites.xml" ]; then
  cp "$KODI_HOME/.kodi/userdata/favorites.xml" "$KODI_HOME/.kodi/userdata/favorites.xml.bak-$(date +%s)"
fi
install -o "$KODI_USER" -g "$KODI_USER" -m 644 "$HERE/favorites.xml" \
  "$KODI_HOME/.kodi/userdata/favorites.xml"

echo "== systemd kodi =="
install -m 644 "$HERE/kodi.service" /etc/systemd/system/kodi.service
systemctl daemon-reload
if [ "$ENABLE" = "1" ]; then
  systemctl enable kodi.service
fi

echo
echo "Готово. Kodi-юзер: $KODI_USER ($KODI_HOME)"
echo "Автозапуск: $(systemctl is-enabled kodi.service 2>/dev/null || echo 'выключен (--no-enable)')"
echo "Запуск сейчас: systemctl start kodi  |  остановка: systemctl stop kodi"
echo "В Kodi: Избранное -> 📶 Wi-Fi / 📻 SDR Радио (или Программы)"
