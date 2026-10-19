#!/bin/sh
# Рабочий стол LXDE вместо kodi (оба — GBM/DRM, одновременно не работают).
# Запуск: ярлык в kodi «🖥 Рабочий стол» или sh /usr/local/bin/lxde.sh из SSH.
# Выход: LXDE → Menu → Logout (или убить X) — kodi вернётся сам (trap EXIT).
sudo -n /usr/local/bin/cgroup-escape "$$"
trap 'sudo -n systemctl start kodi' EXIT
sudo -n systemctl stop kodi
sleep 2
export XDG_RUNTIME_DIR="/run/user/$(id -u)"
export DISPLAY=:0
startx /usr/bin/startlxde -- :0 -nolisten tcp >/tmp/lxde-x.log 2>&1
