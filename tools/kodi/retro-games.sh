#!/bin/sh
# Запуск RetroArch вместо kodi (оба — GBM, DRM-конкуренция):
# останавливаем kodi, гоняем RetroArch, kodi возвращается сам после выхода.
# Запускается из kodi от юзера kot — systemctl только через sudo -n
# (права выдаёт sudoers-lan-bridge).
CORE="$1"
sudo -n systemctl stop kodi
sleep 2
if [ -n "$CORE" ] && [ -f "$CORE" ]; then
  retroarch -L "$CORE"
else
  retroarch
fi
sudo -n systemctl start kodi
