# LAN Discovery — веб-панель управления домашней сетью

Веб-панель для одноплатного компьютера (Orange Pi Plus, ARM/Armbian), которая собирает в одном интерфейсе всё, что связано с домашней LAN: обнаружение устройств, мониторинг железа и сервисов, IPTV/радио/медиаплеер, сетевые инструменты, файлы, заметки и бэкапы.

- **Репозиторий:** https://github.com/kotmartovskiy/Lan-discovery-ARM
- **Панель:** `http://<ip>:8080` (основной хост — `192.168.3.234`, WiFi AP — `192.168.3.235`)
- **Стек:** Python 3.12, Flask 3, Flask-SocketIO, Flask-WTF (CSRF), bcrypt, SQLite, Jinja2

## Что умеет

| Раздел | Возможности |
|---|---|
| **Сеть** | Автосканирование LAN, карточки устройств, история, веб-порты, Netdata-метрики |
| **Система** | CPU/RAM/диск/температура, health-check, перезагрузка, бэкапы БД и eMMC, клонирование eMMC → SD |
| **Медиа** | IPTV-плейлисты, радио, локальный плеер, будильники, IP-камеры, Transmission, DLNA/UPnP |
| **Инструменты** | ping / DNS / traceroute / скан портов, WiFi-анализатор, Bluetooth |
| **Приложения** | Замотки, менеджер паролей, файловый менеджер, терминал, игры |
| **Прочее** | Курсы валют, цены переработки, погода и МЧС-оповещения |

## Быстрый старт

1. [Установка и развёртывание](https://github.com/kotmartovskiy/Lan-discovery-ARM/wiki/Установка) — зависимости, systemd, деплой.
2. [Архитектура](https://github.com/kotmartovskiy/Lan-discovery-ARM/wiki/Архитектура) — как устроен код.
3. [Модули и роуты](https://github.com/kotmartovskiy/Lan-discovery-ARM/wiki/Модули) — таблица всех endpoint'ов.
4. [IPTV](https://github.com/kotmartovskiy/Lan-discovery-ARM/wiki/IPTV) · [SD-клонирование](https://github.com/kotmartovskiy/Lan-discovery-ARM/wiki/SD-клонирование) · [Погода](https://github.com/kotmartovskiy/Lan-discovery-ARM/wiki/Погода) — отдельные подсистемы.
5. [Полезные команды](https://github.com/kotmartovskiy/Lan-discovery-ARM/wiki/Полезные-команды) — SSH, логи, бэкапы, отладка.

## Ключевые файлы

```
/opt/lan-discovery/app.py            # точка входа (и весь прод-код)
/opt/lan-discovery/devices.db        # SQLite: устройства, погода, курсы, инвентарь
/etc/lan-discovery/                  # users.json, settings.json, iptv-playlists.json, notes, secrets
/usr/local/sbin/                     # update-iptv*.sh, weather-update.py, backup-*.sh
/etc/systemd/system/                 # lan-discovery.service, *.timer
```

## Учётные записи и роли

Пользователи хранятся в `/etc/lan-discovery/users.json`, пароли — bcrypt. Роли:

- `admin` — всё, включая пользователей, сервисы, диск;
- `editor` — изменение данных (заметки, устройства, плейлисты);
- `guest` — только просмотр.

`SECRET_KEY` для CSRF — `/etc/lan-discovery/secret.key`.

## История версий

Код версионируется в git (ветка `main`), изменения — коммитами с понятными сообщениями. Сами правки на сервере делаются по правилу: **бэкап → правка → синтакс-проверка → рестарт сервиса** (см. [Установка](https://github.com/kotmartovskiy/Lan-discovery-ARM/wiki/Установка)).
