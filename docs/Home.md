# LAN Discovery — веб-панель управления домашней сетью

Веб-панель для одноплатного компьютера (X96 Max, ARM/Armbian, hostname `armbian`), которая собирает в одном интерфейсе всё, что связано с домашней LAN: обнаружение устройств, мониторинг железа и сервисов, IPTV/радио/медиаплеер, сетевые инструменты, файлы, заметки и бэкапы.

- **Репозиторий:** https://github.com/kotmartovskiy/Lan-discovery-ARM
- **Каталог модулей:** https://github.com/kotmartovskiy/Lan-discovery-modules
- **Панель:** `http://192.168.3.243:8080` (X96 Max / Armbian; с 28.09.2026 панель переехала сюда с Orange Pi)
- **Стек:** Python 3.11 (venv), Flask 3, Flask-SocketIO, Flask-WTF (CSRF), bcrypt, SQLite, Jinja2

## Что умеет

| Раздел | Возможности |
|---|---|
| **Сеть** | Автосканирование LAN, карточки устройств, история, веб-порты, Netdata-метрики |
| **Система** | CPU/RAM/диск/температура, health-check, перезагрузка, бэкапы БД и eMMC, клонирование eMMC → SD |
| **Медиа** | IPTV-плейлисты, радио, локальный плеер, будильники, IP-камеры, Transmission, DLNA/UPnP |
| **Инструменты** | ping / DNS / traceroute / скан портов, WiFi-анализатор, Bluetooth |
| **Приложения** | Заметки, менеджер паролей, файловый менеджер, терминал, игры |
| **Модули** | Вкл/выкл разделов (вкладки/блоки/плитки), установка зависимостей, каталог из GitHub-репозитория |
| **Прочее** | Курсы валют, цены переработки, погода и МЧС-оповещения |

## Быстрый старт

1. [Установка и развёртывание](https://github.com/kotmartovskiy/Lan-discovery-ARM/wiki/Установка) — зависимости, systemd, деплой.
2. [Архитектура](https://github.com/kotmartovskiy/Lan-discovery-ARM/wiki/Архитектура) — как устроен код.
3. [Модули и роуты](https://github.com/kotmartovskiy/Lan-discovery-ARM/wiki/Модули) — таблица всех endpoint'ов.
4. [IPTV](https://github.com/kotmartovskiy/Lan-discovery-ARM/wiki/IPTV) · [SD-клонирование](https://github.com/kotmartovskiy/Lan-discovery-ARM/wiki/SD-клонирование) · [Погода](https://github.com/kotmartovskiy/Lan-discovery-ARM/wiki/Погода) — отдельные подсистемы.
5. [Полезные команды](https://github.com/kotmartovskiy/Lan-discovery-ARM/wiki/Полезные-команды) — SSH, логи, бэкапы, отладка.

## Ключевые файлы

```
/opt/lan-discovery/app.py            # точка входа: инициализация, фон, main
/opt/lan-discovery/modules/          # роуты и логика разделов + модули-компоненты
/opt/lan-discovery/core/             # module_loader (манифесты), module_catalog (каталог GitHub)
/opt/lan-discovery/venv/             # виртуальное окружение Python
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
