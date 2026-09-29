# AGENTS.md — Инструкции для AI-ассистента

## Обязательные правила

### БЭКАПЫ ПЕРЕД ЛЮБЫМ ИЗМЕНЕНИЕМ
**ПЕРЕД КАЖДЫМ РЕДАКТИРОВАНИЕМ app.py (или любого другого файла):**
1. Сделать бэкап через SSH:
   ```
   cp /opt/lan-discovery/app.py /opt/lan-discovery/app.py.backup-$(date +%Y%m%d-%H%M%S)
   ```
2. Убедиться что бэкап создан успешно
3. Только потом делать изменение

Это правило НЕОБХОДИМО соблюдать всегда без исключений.

### ГИТХАБ: ОБЯЗАТЕЛЬНО ВНОСИТЬ ИЗМЕНЕНИЯ В ПРОЕКТ И ДОКУМЕНТАЦИЮ
**Любые дополнения и изменения кода, шаблонов и документации нужно коммитить и пушить на GitHub — иначе репозиторий отстаёт от работающей системы.**

Репозитории:
- **`Lan-discovery-ARM`** (приватный) — https://github.com/kotmartovskiy/Lan-discovery-ARM — код (`app.py`, `modules/`, `templates/`, `games/`, `static/`, `weather-monitor/`), документация `docs/`, `README.md`, `AGENTS.md`. Ветка `main`.
- **`Lan-discovery-docs`** (публичный) — https://github.com/kotmartovskiy/Lan-discovery-docs — очищенная от рабочих IP/паролей копия `docs/`.
- **`Lan-discovery-modules`** (публичный) — https://github.com/kotmartovskiy/Lan-discovery-modules — каталог модулей для вкладки «Модули» (`index.json` + `<id>/` с `module.json`); панель ставляет/обновляет модули из этой ветки (настройка `modules_catalog` в `/etc/lan-discovery/settings.json`).

Порядок действий:
1. `git status` → `git add <изменённые файлы>` (мусор типа `check_*`, `debug*`, `verify*`, `__pycache__` отфильтровывается `.gitignore`).
2. Коммит — сообщение по-русски с префиксом: `core:` `ui:` `docs:` `fix:` `tools:` `weather:` `chore:`.
3. `git push origin main`.
4. Если менялся `docs/` — обновить публичную версию:
   ```
   python tools/sanitize_docs.py        # выход 0 = утечек нет
   cd <temp>/docs-public && git add -A && git commit -m "docs: ..." && git push
   ```
5. Если правки вносились на сервер (`/opt/lan-discovery/*`) — сначала подтянуть их в локальную копию (SFTP read → правка → commit), чтобы репозиторий соответствовал проду.

## Рабочее окружение
- **Web panel: `http://192.168.3.243:8080`** (X96 Max / Armbian, hostname `armbian`)
  — lan-discovery **переехал сюда** 28.09.2026 (venv: `/opt/lan-discovery/venv`,
  systemd `lan-discovery` enabled, данные `devices.db` перенесены)
- X96 Max: IP `192.168.3.243`, SSH root/1234 (hostkey `SHA256:TpeCxMP+...`)
- Orange Pi: `192.168.3.234` (LAN) **не отвечает** (кабель/интерфейс отвал),
  доступен через WiFi AP `192.168.3.235` (hostkey `SHA256:fwnWkNuM+...`);
  сервис `lan-discovery` на OP ещё активен — при необходимости остановить
  (`systemctl disable --now lan-discovery`), чтобы не сканировали сеть дважды
- Thinkpad T480: IP `192.168.3.236` (WiFi) / `192.168.3.239` (LAN)
- Flask app: `/opt/lan-discovery/app.py` (на боксе — внутри venv)
- Systemd service: `lan-discovery`

## Процесс редактирования app.py
1. SFTP read → Python string replace → SFTP write → syntax check → `systemctl restart lan-discovery`
2. Синтакс-проверка: `python3 -c "import py_compile; py_compile.compile('/opt/lan-discovery/app.py', doraise=True)"`
3. Рестарт: `systemctl restart lan-discovery`
4. venv-пакеты: `/opt/lan-discovery/venv/bin/pip install -r requirements.txt`

## Сетевые устройства
- Known web ports: `{"192.168.3.234": 8080, "192.168.3.235": 8080, "192.168.3.51": 8080}`
- Server IPs to skip web probing: `{"192.168.3.234", ".235", ".51"}`
- Orange Pi: `192.168.3.234` (LAN), `192.168.3.235` (WiFi AP)
- Disk: eMMC `/dev/mmcblk2` (14.6G), HDD `/dev/sda` (232.9G), SD `/dev/mmcblk0` (29.1G)

## Форматы
- Дата/время: DD.MM.YYYY HH:MM:SS
- Сетевые проверки: `network_check.py` + HTTP fallback
- Погода: Open-Meteo (57.0, 41.0), timezone Europe/Moscow
