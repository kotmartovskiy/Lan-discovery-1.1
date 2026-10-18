#!/bin/sh
# Kodi-набор lan-discovery: автозапуск Kodi + Wi-Fi + SDR-радио + ретроигры + ТВ (PVR).
# Полностью повторяем на аналогичном устройстве Armbian/Debian (arm64):
#   sh install.sh [--user <юзер>] [--no-enable]
#
# Ставит (если нет): kodi, ffmpeg, rtl-sdr, python3, retroarch + libretro-ядра.
# Конфиги: kodi.service, hdmi-watch, sudoers nmcli, udev rtl-sdr, addons,
# PVR tvheadend (127.0.0.1:9981), web-управление на 8085, favorites.
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
for p in kodi ffmpeg rtl-sdr python3 retroarch \
         libretro-nestopia libretro-snes9x libretro-gambatte \
         libretro-mgba libretro-genesisplusgx libretro-beetle-psx; do
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

echo "== hdmi-watch (автоперезапуск kodi при появлении дисплея) =="
install -m 755 "$HERE/hdmi-watch.sh" /usr/local/bin/hdmi-watch.sh
install -m 644 "$HERE/hdmi-watch.service" /etc/systemd/system/hdmi-watch.service
systemctl daemon-reload
systemctl enable --now hdmi-watch.service

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
       "$KODI_HOME/.kodi/addons/plugin.program.sdr-radio" \
       "$KODI_HOME/.kodi/addons/plugin.program.retro-games"
cp -r "$HERE/addon-wifi/plugin.program.wifi-settings" "$KODI_HOME/.kodi/addons/"
cp -r "$HERE/addon-sdr/plugin.program.sdr-radio" "$KODI_HOME/.kodi/addons/"
cp -r "$HERE/addon-retro/plugin.program.retro-games" "$KODI_HOME/.kodi/addons/"
python3 "$HERE/make_icons.py" \
  "$KODI_HOME/.kodi/addons/plugin.program.wifi-settings/icon.png" \
  "$KODI_HOME/.kodi/addons/plugin.program.sdr-radio/icon.png" \
  "$KODI_HOME/.kodi/addons/plugin.program.retro-games/icon.png"
chown -R "$KODI_USER:$KODI_USER" "$KODI_HOME/.kodi/addons"
# иконка для ярлыка «ТВ» (pvr.hts — системный аддон, иконка из /usr/share)
if [ -f /usr/share/kodi/addons/pvr.hts/icon.png ]; then
  install -d -o "$KODI_USER" -g "$KODI_USER" "$KODI_HOME/.kodi/addons/pvr.hts"
  install -o "$KODI_USER" -g "$KODI_USER" -m 644 /usr/share/kodi/addons/pvr.hts/icon.png \
    "$KODI_HOME/.kodi/addons/pvr.hts/icon.png"
fi

echo "== RetroArch =="
install -m 755 "$HERE/retro-games.sh" /usr/local/bin/retro-games.sh
# retroarch от kot должен открывать DRM: те же группы, что у kodi.service
for g in video render audio input; do
  getent group "$g" >/dev/null && usermod -aG "$g" "$KODI_USER"
done
install -d -o "$KODI_USER" -g "$KODI_USER" "$KODI_HOME/roms"
install -d -o "$KODI_USER" -g "$KODI_USER" "$KODI_HOME/.config/retroarch"
if [ ! -f "$KODI_HOME/.config/retroarch/retroarch.cfg" ]; then
  install -o "$KODI_USER" -g "$KODI_USER" -m 644 "$HERE/retroarch.cfg" \
    "$KODI_HOME/.config/retroarch/retroarch.cfg"
fi

echo "== избранное (ярлыки в главном меню) =="
install -d -o "$KODI_USER" -g "$KODI_USER" "$KODI_HOME/.kodi/userdata"
if [ -f "$KODI_HOME/.kodi/userdata/favourites.xml" ]; then
  cp "$KODI_HOME/.kodi/userdata/favourites.xml" "$KODI_HOME/.kodi/userdata/favourites.xml.bak-$(date +%s)"
fi
rm -f "$KODI_HOME/.kodi/userdata/favorites.xml"
install -o "$KODI_USER" -g "$KODI_USER" -m 644 "$HERE/favourites.xml" \
  "$KODI_HOME/.kodi/userdata/favourites.xml"

echo "== PVR tvheadend =="
install -d -o "$KODI_USER" -g "$KODI_USER" "$KODI_HOME/.kodi/userdata/addon_data/pvr.hts"
install -o "$KODI_USER" -g "$KODI_USER" -m 644 "$HERE/pvr-hts-settings.xml" \
  "$KODI_HOME/.kodi/userdata/addon_data/pvr.hts/instance-settings-1.xml"
rm -f "$KODI_HOME/.kodi/userdata/addon_data/pvr.hts/settings.xml"
if [ ! -f "$KODI_HOME/.kodi/userdata/advancedsettings.xml" ]; then
  install -o "$KODI_USER" -g "$KODI_USER" -m 644 "$HERE/advancedsettings.xml" \
    "$KODI_HOME/.kodi/userdata/advancedsettings.xml"
fi
if [ ! -f "$KODI_HOME/.kodi/userdata/settings.xml" ]; then
  install -o "$KODI_USER" -g "$KODI_USER" -m 644 "$HERE/settings-webserver.xml" \
    "$KODI_HOME/.kodi/userdata/settings.xml"
fi
install -m 755 "$HERE/enable-pvr.sh" /usr/local/bin/enable-pvr.sh
install -m 755 "$HERE/tvh-access.sh" /usr/local/bin/tvh-access.sh
if command -v tvheadend >/dev/null 2>&1; then
  sh "$HERE/tvh-access.sh"
else
  echo "tvheadend не установлен — пункт ТВ в kodi будет без каналов"
fi
if ls "$KODI_HOME"/.kodi/userdata/Database/Addons*.db >/dev/null 2>&1; then
  sh "$HERE/enable-pvr.sh" || true
else
  echo "ПЕРВЫЙ ЗАПУСК: после старта kodi выполните: sh $HERE/enable-pvr.sh"
fi

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
echo "В Kodi: главное меню -> Избранное (📶 Wi-Fi, 📻 SDR/FM, 🎮 Ретроигры, 📺 ТВ)"
