**Где это:** вкладка «Торрент» в верхнем меню.

- Веб-интерфейс Transmission v4 встроен прямо во вкладку (порт `9091`).
- Скачанные файлы: `/srv/downloads` (общий шары также видны в Samba/DLNA).
- Входящие соединения: TCP/UDP `51413`.
- RPC без пароля — только для локальной сети; из интернета порт не открывать.

**Сервис и конфиг:**

- `systemctl status transmission-daemon` — состояние.
- `/etc/transmission-daemon/settings.json` — настройки; после правки: `systemctl restart transmission-daemon`.

**Очередь и управление** — через API панели: `/api/transmission/queue`, `/api/transmission/action`, `/api/transmission/add`.

**Зависимости модуля:** `transmission-daemon` (apt), сервис `transmission-daemon`, папка `/srv/downloads` — ставятся кнопкой «Установить зависимости» на странице «Модули».

**Если вкладка выключена:** страница и API `/torrent`, `/api/transmission` отвечают 404, пункт меню скрыт. Включить обратно можно на странице «Модули» (админ).
