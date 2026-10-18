#!/bin/sh
# Следит за HDMI-коннектором: при появлении дисплея (disconnected -> connected)
# перезапускает kodi, иначе на Amlogic/GBM картинка не появляется без reboot.
LOG_TAG=hdmi-watch
prev=$(cat /sys/class/drm/card0-HDMI-A-1/status 2>/dev/null)
while true; do
  cur=$(cat /sys/class/drm/card0-HDMI-A-1/status 2>/dev/null)
  if [ "$cur" = "connected" ] && [ "$prev" != "connected" ]; then
    logger -t "$LOG_TAG" "HDMI connected, restarting kodi"
    # физическая страховка: если висит RetroArch (чёрный экран/пульт не отвечает) —
    # выдернуть-воткнуть HDMI убивает его и возвращает kodi
    pkill -u kot -x retroarch 2>/dev/null
    sleep 1
    systemctl restart kodi
    sleep 5
    cur=$(cat /sys/class/drm/card0-HDMI-A-1/status 2>/dev/null)
  fi
  prev=$cur
  sleep 3
done
