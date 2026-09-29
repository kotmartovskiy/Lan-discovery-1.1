#!/bin/bash
# Работник для systemd-run (кнопка «Обновить» у плейлиста в панели):
# systemd-run --unit=update-iptv-one-<idx> /usr/local/sbin/update-iptv-one-worker.sh <idx>
exec /usr/local/sbin/update-iptv.sh "$1"
