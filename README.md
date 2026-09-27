# Lan-discovery-ARM

Веб-панель управления домашней сетью для Orange Pi (ARM/Armbian): обнаружение устройств, мониторинг, IPTV/радио/плеер, сетевые инструменты, файлы, заметки, бэкапы и клонирование eMMC → SD.

- **Панель:** `http://<ip>:8080` (Flask, Python 3.12)
- **Сервис:** `systemctl status lan-discovery`, код — `/opt/lan-discovery/app.py`

## Документация

Полные инструкции — в [`docs/`](docs/):

| Страница | О чём |
|---|---|
| [Home](docs/Home.md) | Обзор возможностей |
| [Установка](docs/Установка.md) | Зависимости, systemd, таймеры, деплой |
| [Архитектура](docs/Архитектура.md) | Структура кода, данные, фоновые задачи |
| [Модули](docs/Модули.md) | Таблица всех роутов |
| [IPTV](docs/IPTV.md) | Плейлисты, таймер 04:15, диагностика |
| [SD-клонирование](docs/SD-клонирование.md) | Копирование eMMC → SD, API, осторожности |
| [Погода](docs/Погода.md) | Open-Meteo, таймеры, weather-monitor |
| [Полезные команды](docs/Полезные-команды.md) | SSH, логи, бэкапы, типовые неполадки |

Публичная (очищенная от рабочих адресов и паролей) версия документации: **https://github.com/kotmartovskiy/Lan-discovery-docs**

## Стек

Python 3 · Flask 3 · Flask-SocketIO · Flask-WTF · bcrypt · SQLite · Jinja2 · systemd

## Быстрый старт

```bash
cd /opt/lan-discovery
pip3 install -r requirements.txt
python3 -c "import py_compile; py_compile.compile('app.py', doraise=True)"
systemctl enable --now lan-discovery
```

Правки на сервере — только по регламенту: **бэкап → правка → `py_compile` → `systemctl restart lan-discovery`** (см. [Установка](docs/Установка.md)).

## Структура репозитория

```
app.py            точка входа
modules/          роуты и логика (auth, devices, system, network, media, weather, core)
templates/        Jinja2-шаблоны (base.html — каркас панели)
games/, static/   игры и статика
weather-monitor/  отдельное приложение для экспериментов с погодой
docs/             документация
deploy.py         деплой на сервер: бэкап → SFTP → проверка → рестарт
```
