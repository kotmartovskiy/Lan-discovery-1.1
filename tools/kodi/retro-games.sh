#!/bin/sh
# Запуск RetroArch вместо kodi (оба — GBM, DRM-конкуренция):
# останавливаем kodi, гоняем RetroArch, kodi возвращается сам после выхода.
CORE="$1"
systemctl stop kodi
sleep 2
if [ -n "$CORE" ] && [ -f "$CORE" ]; then
  retroarch -L "$CORE"
else
  retroarch
fi
systemctl start kodi
