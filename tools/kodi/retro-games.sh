#!/bin/sh
# Запуск RetroArch вместо kodi (оба — GBM, DRM-конкуренция):
# останавливаем kodi, гоняем RetroArch, kodi возвращается сам после выхода.
# Запускается из kodi от юзера kot — systemctl только через sudo -n
# (права выдаёт sudoers-lan-bridge).
CORE="$1"
ROM="$2"

# Отвязка от cgroup kodi.service: иначе systemctl stop kodi убивает этот
# скрипт (и retroarch) по KillMode=control-group, и kodi не возвращается.
sudo -n /usr/local/bin/cgroup-escape "$$"
# Страховка: kodi поднимается при любом выходе скрипта
trap 'sudo -n systemctl start kodi' EXIT

sudo -n systemctl stop kodi
sleep 2
if [ -n "$CORE" ] && [ -f "$CORE" ] && [ -n "$ROM" ] && [ -f "$ROM" ]; then
  retroarch -L "$CORE" "$ROM"
else
  # без content ядра не стартуют — открываем меню RetroArch (Load Content)
  retroarch
fi
