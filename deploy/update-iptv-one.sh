#!/bin/bash
# Обновление одного плейлиста по индексу (обёртка над update-iptv.sh).
exec /usr/local/sbin/update-iptv.sh "$1"
