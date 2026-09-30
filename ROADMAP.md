# ROADMAP.md — LAN Discovery → production-quality portable appliance

**Дата аудита (PHASE 0):** 30.09.2026
**Статус аудита:** DONE (код не менялся)
**Область:** локальный репозиторий + обе платформы (X96 Max, Orange Pi Plus) по SSH (read-only).

---

## 0. Охват аудита

Проверено:
- структура репозитория, git-состояние, точка входа `app.py`;
- зависимости (`requirements.txt`, venv на платформах);
- systemd units и таймеры на обеих платформах;
- SQLite: схема, индексы, WAL/busy_timeout, миграции, retention, бэкапы;
- все 161 web-роут, декораторы авторизации, CSRF, SocketIO;
- вызовы `subprocess`/shell, path traversal, секреты, привязка адреса;
- hardcoded IP/интерфейсы/пути, platform-specific код;
- фоновые потоки и планировщики;
- синхронизация репозиторий ↔ серверы (помд5 всех файлов);
- тесты, CI, документация.

Не проверялось (требует отдельной работы): нагрузочные/конкурентные тесты, реальный
security pentest, восстановление из backup на чистую систему, поведение после reboot
(по логам — сервис auto-start есть, фактический reboot-тест не проводился).

---

## 1. Платформы (факт на 30.09.2026)

| | **X96 Max** | **Orange Pi Plus 2** |
|---|---|---|
| Hostname / IP | `armbian` / 192.168.3.243 | `orangepiplus` / 192.168.3.234 (LAN) |
| SoC / arch | Amlogic S905X2, **aarch64** | Allwinner H3, **armv7l** |
| OS | Armbian 26.11 **bookworm (Debian 12)**, kernel 6.18.51-ophub | Armbian 26.11 **trixie (Debian 13)**, kernel 6.18.46-sunxi |
| Питание/загрузка | **boot с SD-карты, временно без HDD — тестовый/резервный вариант** | основной носитель (eMMC + HDD, backup-emmc таймеры) |
| Код панели | **новая версия** (модульная: `core/`, `modules/` 111 файлов) | **старая версия** (`core/` отсутствует, `modules/` 22 файла) |
| `app.py` | md5 `ede31088…` == репозиторий | md5 `004fea92…` — другой (старый) |
| Service | enabled/active, NRestarts=0, RAM ~68 МБ | enabled/active, NRestarts=0, RAM ~43 МБ |
| RAM всего | 3309 МБ | 2006 МБ |
| Бэкап БД | `/srv/backup-db` — 3 файла (таймер 03:30, **timer ещё не срабатывал**) | `/srv/backup-db` — 182 файла (часовые, идёт давно) |
| Таймеры | weather-update, backup-db, update-iptv, env-data | + backup-emmc, backup-emmc-test |

**Вывод:** сейчас в работе **две разные версии приложения** на двух платформах, обе
активно сканируют одну подсеть. Это главный источник дрейфа (см. §9).

---

## 2. Сводная таблица

| Area | Current state | Target | Gap | Priority |
|---|---|---|---|---|
| **Security: веб-терминал** | SocketIO `terminal_start` **без авторизации** → PTY `/bin/bash` **от root** (`core_routes.py:906-956`); `cors_allowed_origins="*"` (`app.py:336`) | только admin, Origin ограничен |任何人 с доступом к порту получает root-shell | **P0** |
| **Security: filemanager** | корень `/`, операции только под `@login_required` (гость может `shutil.rmtree`) — `core_routes.py:655-761` | admin-only + корень-ограничение | полное управление ФС от root | **P0** |
| **Security: неавторизованные роуты** | `/api/network/check`, `/api/network/check_host` (POST, user host → команда), `/api/health` — без декораторов (`network_routes.py:73,82`) | авторизация (health — по решению) | DoS/SSRF-вектор без входа | **P0** |
| **Security: сейф паролей** | «шифрование» = base64 + HMAC, который **игнорируется при несовпадении**; ключ = `secret.key`; чтение доступно guest — `core_routes.py:793-816` | настоящее шифрование (Fernet/AES-GCM) или явно «не секреты» | пароли в открытом виде (+base64) | **P0** |
| **Security: авторизация** | `enabled` не проверяется в `login_required` (`auth.py:85-93`); SHA-256-фолбэк пароля (`auth.py:35-42`); нет session timeout; смена пароля без мин. длины (`core_routes.py:525`) | отключённый юзер = 401, только bcrypt, TTL сессии | отключённый пользователь остаётся в системе | **P0** |
| **Security: CSRF во вкладках** | `base_app.html` **без csrf-meta** в репозитории → 11 шаблонов `/apps/*` POST без токена (на X96 правка уже есть, **в git не закоммичена**) | csrf-meta + fetch-wrapper в обеих базовых шаблонаках | POST-запросы из вкладок падают/незащищены | **P0** |
| **Security: заголовки/HOST** | нет X-Frame-Options/CSP/X-Content-Type; `SESSION_COOKIE_*` не настроены; dev-Werkzeug `allow_unsafe_werkzeug=True` на `0.0.0.0:8080` (`app.py:351`) | заголовки, cookie-флаги, (опц.) reverse-proxy | clickjacking/доп. экспозиция | **P1** |
| **Security: секреты в git** | `AGENTS.md`, `docs/*`, `templates/help.html:96,627` — root/1234, рабочие IP; 8 скриптов с `password='1234'`; `sanitize_docs.py` чистит **только `docs/`** | чистка всех отслеживаемых файлов | утечка реквизитов в публичные репо (docs/demo) | **P1** |
| **Stability: изоляция сбоев** | большинство роутов в `try/except`, но: DDL в `get_db()` на **каждый запрос** (`devices_routes.py:22-98`); утечки `con.close()` при исключениях (нет `finally`); падение импорта модуля валит всё приложение | схема один раз при старте; context manager; тест «SMART/Wi-Fi/nmap нет» | часы/диски/сеть отсутствуют → 500 в отдельных роутах (не фатально), но нет системного барьера | **P1** |
| **Stability: фоновые задачи** | `start_scan_thread()` без guard от повторного запуска (`devices_routes.py:756`); `/inventory/scan` и bluetooth-scan без lock → параллельные прогоны по повторному POST; дубли функций (`app.py` ↔ `core_routes.py`), **мёртвый код** `init_background_tasks` (`core_routes.py:1009`) | lock/flag на каждую задачу, один источник истины | race: параллельные nmap/сканы, лишняя нагрузка | **P1** |
| **Stability: systemd** | `Restart=always`, `RestartSec=5`, `After=network-online` — корректно; **но** сервис работает **от root** и dev-сервер Werkzeug | non-root пользователь + (wsgi) либо задокументированное «root by design» | root-веб-сервер | **P1** |
| **Configuration** | сеть/скан/интерфейсы/порт подключены к `/etc/lan-discovery/settings.json` через `_cfg` (P2: `subnet`, `scan_interval`/`max_misses`, `wifi_ifaces`, `traffic_ifaces`, `self_ips`, `web.flask_host`/`flask_port`; удалён мёртвый `app.NETWORK`); пути `/opt|/etc|/srv` остаются в коде (задокументированы в `docs/Конфигурация.md`) | единый конфиг: defaults + settings.json overrides | частично: пути захардкожены осознанно | **P2** (закрыта) |
| **Hardware abstraction** | `core/hardware.py`: `detect_platform()`/`thermal_temp()`/`hdd_device()`/`emmc_device()`/`sd_device()` — thermal-перебор зон и динамический детект дисков вместо хардкодов (`thermal_zone0`, `mmcblk2`, `/dev/sda`); `platform`-блок в `/api/health`; остаток: пути `/opt|/etc|/srv` (конфиг, PHASE 2) | `detect_platform()` + capabilities + адаптеры | закрыта (пути — в PHASE 2) | **P2** (закрыта) |
| **Переносимость (X96)** | новый код **уже работает** на aarch64/Debian 12; старый — на armv7l/Debian 13 | один код на обеих | две версии в проде (§9) | **P2** |
| **Database** | ~~нет версионирования/индексов/retention, 8 таблиц без CREATE в репо~~ **закрыта (P5, 30.09)**: нумерованные `MIGRATIONS` по `user_version` (v1 базовая, v2 events), ensure 8 «серверных» таблиц (DDL из боевой БД) + индексы `events(ip,id)`/`events(event,id)`/`weather_observations`, retention `events.retention_days` (180д, чистка при старте + ежедневный поток); WAL + busy_timeout | `user_version` + миграции, индексы, retention, идентичность MAC+IP+hostname | идентичность = IP (не MAC) — отложено до нужды | **P5** (закрыта частично: identity отложен) |
| **Discovery engine** | ~~скан плотно связан с UI-роутами, сеть захардкожена, нет ручного выбора, MAC-смена не пишется в events~~ **закрыта (P6, 30.09)**: движок вынесен в `core/discovery.py` (scanner `run_scan` → normalizer `parse_scan` → `reconcile` → events), интерфейсы/подсеть из `network.scan_ifaces`/`subnet`, ручной `POST /api/scan` + кнопка в UI, событие `MAC_CHANGED` | scanner → normalizer → DB → events → API, manual/scheduled scan по выбору | ручной скан и scheduled есть; выбор интерфейса — через `scan_ifaces` (не через UI-форму) | **P6** (закрыта) |
| **Event system** | ~~только 3 типа, нет severity/source/metadata~~ **закрыта (P7, 30.09)**: events v2 — `severity`/`source`/`metadata` (JSON), фабрика `core/events.py` (`add_event`), `GET /api/events` с фильтрами, бейджи в `/history`; типы событий: NEW/ONLINE/OFFLINE/MAC_CHANGED | формализованные события (device_missing, ip_changed, disk_warning…) | severity/источник/фильтры есть; новые типы (disk_warning, ip_changed) подключаются через `add_event` одной строкой | **P7** (закрыта) |
| **Observability** | `/api/health` есть (unauth, `system_routes.py:1636`), `/api/status`, `/api/system/health` — но **нет version/uptime/last-discovery в одном месте** | `/api/health` + `/api/version` + `/api/discovery/status` | состояние видно только через UI | **P1** |
| **Installer** | нет: установка вручную по `docs/Установка.md` (venv + systemd вручную) | `install.sh`: dep-check → config → systemd → db init → health | воспроизводимость установки на новое устройство | **P3** |
| **Update/rollback** | деплой вручную (`deploy.py`: бэкап → SFTP → py_compile → restart); бэкап БД автоматический + integrity_check + restore из UI — **это уже работает** | версия → backup → update → health → rollback | нет версий/отката кода (только бэкап файлов) | **P3** |
| **Backup/recovery** | БД: Online Backup API + integrity_check + ротация 14 дней + restore через UI (`system_routes.py:1936`); на OP эММС-бэкапы; **restore на чистую систему не проверен** | документированная и проверенная процедура restore | «production ready только после проверенного restore» | **P2** |
| **Testing** | ~~pytest/CI нет; 3 ad-hoc скрипта требуют живой панели~~ **закрыта (P13, 30.09)**: `tests/` в репо — 42 unit (discovery/events/hardware/migrations/config, без сети) + 5 live (маркер `live`, скип при недоступности панели), `pytest.ini`+`requirements-dev.txt`, CI на каждый push/PR (ubuntu/py3.11: pytest unit + py_compile); ad-hoc `/tmp/test_p*`-скрипты остались как deploy-проверки фаз | unit + интеграционные в одном прогоне | живые ad-hoc-скрипты фаз не в git (deploy-only) | **P13** (закрыта) |
| **Documentation** | `docs/` (9 страниц, wiki), `README.md`, `AGENTS.md`; `docs/Архитектура.md:81` **устарел** (11 таблиц vs 16 фактических), нет ARCHITECTURE/SECURITY/CONFIGURATION/API | комплект 1.0 (см. PHASE 14) | документация отстаёт от кода | **P3** |
| **Repo hygiene** | в корне 60+ одноразовых скриптов (`check_*`, `debug*`, `verify*` — большая часть в `.gitignore`, часть трекается: `patch_app.py`, `ssh_query.py`…); трекаются `modules/*_b64.txt`; ~~`.gitattributes` нет~~ **добавлен 30.09 (P0-6)** | мусор вне корня/git | грязь в репозитории | **P4** |

---

## 3. Что уже работает хорошо (НЕ ломать)

1. **Модульная система** (`core/module_loader.py`, `core/module_catalog.py`): манифесты,
   вкладки/блоки/плитки, установка зависимостей, защита от path traversal в каталоге
   модулей, кэш 5 мин — зрелая и полезная конструкция.
2. **Бэкап БД** — эталон для проекта: `backup-db.sh` (Online Backup API →
   `PRAGMA integrity_check` → ротация), таймер, restore из UI с проверкой.
3. **CSRFProtect глобально** + fetch-обёртка в `base.html`; `@csrf.exempt` отсутствует.
4. **Авторизация**: bcrypt, роли admin/editor/guest, rate-limit логина (5/300с по IP).
5. **Каталог модулей**: валидация id, проверка путей в архиве, лимит файлов, токен из конфига.
6. **systemd**: `Restart=always`/`RestartSec=5`, таймеры с `Persistent=true`.
7. **SQLite**: WAL + `busy_timeout=30000` в горячих путях, все DDL `IF NOT EXISTS`.
8. **Service management**: allowlist имён/действий в `/api/service/<svc>/<action>`.
9. **Код в основном работает через argv-списки** (`shell=False`): `os.system`/`shell=True`
   буквально нет; единственный скрытый `shell=` — `app.py:82` (срабатывает только при
   строковом аргументе, сейчас все вызовы — списки).
10. Обе платформы: сервисы active, NRestarts=0, integrity БД `ok`.

---

## 4. Blockers (P0) — найденные проблемы

| # | Проблема | Место | Эффект |
|---|---|---|---|
| B1 | ~~Веб-терминал без авторизации, root-PTY, CORS `*`~~ **РЕШЁН (P0-1)** — SocketIO admin-only, CORS same-origin; root-PTY и dev-Werkzeug остались (деферт вне scope задачи 10) | `core_routes.py`, `app.py` | RCE закрыт для не-admin |
| B2 | ~~Filemanager: корень `/`, guest может удалять/перемещать файлы~~ **РЕШЁН (P0-2)** — 7 API → `@admin_required`, нормализация путей; корень `/` оставлен для admin | `core_routes.py` | потеря данных закрыта |
| B3 | ~~`POST /api/network/check_host` без авторизации (host → внешняя команда)~~ **РЕШЁН (P0-3)** — `@login_required` + `_valid_host` во всех nettools | `network_routes.py` | неаутентифицированный SSRF/DoS закрыт |
| B4 | ~~Сейф паролей: base64, HMAC игнорируется, guest читает~~ **РЕШЁН (30.09.2026, P0-4)** — Fernet + `@can_edit` | `core_routes.py` secrets-helpers | пароли открыты — закрыто |
| B5 | ~~Отключённый пользователь не выкидывается из сессии; SHA-256-фолбэк пароля~~ **РЕШЁН (30.09.2026, P0-5)** — enabled+TTL в `get_current_user`, lazy re-hash bcrypt, min 8 | `auth.py` | обход блокировки учётки — закрыт |
| B6 | ~~CSRF-meta отсутствует в `base_app.html` **в репозитории**~~ **РЕШЁН (30.09.2026, P0-6)** — правки X96 забраны в репо | `templates/base_app.html` | регресс CSRF при следующем деплое — закрыт |

Не P0, но рядом: dev-Werkzeug на `0.0.0.0`, нет security-заголовков, root-сервис.

---

## 5. Синхронизация «репозиторий ↔ серверы»

**Статус: ВЫПОЛНЕНО (30.09.2026, P0-6) — repo == X96, content_diff=0.**

Итоговая сверка md5 (127 файлов): **exact=120, EOL-only=0, content diff=0,
только на сервере=0**. Что было сделано:
- забраны в репо правки X96: `templates/base_app.html` (+24 CSRF-fix, B6),
  `modules/recycling.py` (retry-логика vitaminstir), `templates/login.html` (favicon);
- задеплоены с X96: `modules/monitor.py` (ThreadPoolExecutor) и
  `templates/apps/terminal.html` (восстановлен из репо — на X96 была повреждена
  кодировка) → md5 байт-в-байт;
- 14 EOL-only файлов перезалиты (LF→LF), добавлен `.gitattributes` (`eol=lf`);
- 7 junk-файлов `templates/apps\*.html` (буквальный backslash, артефакт
  загрузки с Windows) перемещены в `/tmp/junk-templates-20260930-034105/`;
- только в git (ожидаемо, не код панели): `docs/`, `deploy/`, `AGENTS.md`,
  `ROADMAP.md`, разовые скрипты, `modules/*_b64.txt` (кандидат на чистку P4).
- OP (Orange Pi) — **другая, старая версия** (нет `modules/`), отдельная задача.

---

## 6. Первые задачи (P0/P1), к выполнению

1. **[P0][DONE — 30.09.2026]** Закрыть терминал: авторизация SocketIO-подключений
   (session/user + admin), ограничить `cors_allowed_origins` → см. журнал §9.
2. **[P0][DONE — 30.09.2026]** Filemanager: все 7 API-роутов → `@admin_required`,
   нормализация путей (`_fm_path`: строка/abs/null-байт), запрет `delete /` и
   `move /`, заглушка «только для admin» в шаблоне — см. журнал §9.
   Решение: корень `/` для admin оставлен (эквивалентен уже имеющемуся у admin
   root-терминалу; ограничение корня сломало бы назначение инструмента).
3. **[P0][DONE — 30.09.2026]** Закрыты `/api/network/check`, `/api/network/check_host`
   (`@login_required`); валидация `host` (`_valid_host`: имя/IPv4/IPv6, без пробелов,
   `/`, ведущего `-`) во всех nettools; валидация MAC (`_valid_mac`) в bluetooth —
   см. журнал §9.
4. **[P0][DONE — 30.09.2026]** Сейф: Fernet (authenticated encryption) на
   отдельном ключе `/etc/lan-discovery/secret.key` (chmod 600), миграция legacy
   base64+HMAC-записей (HMAC теперь реально проверяется), битые записи не
   двойношифруются, все 4 API → `@can_edit` — см. журнал §9.
5. **[P0][DONE — 30.09.2026]** Auth: `enabled` + TTL сессии (12ч) проверяются
   в `get_current_user` (сессия выкидывается), SHA-256 — только на первом входе
   с мгновенным re-hash в bcrypt, мин. длина пароля 8, дубли хелперов в
   `core_routes` заменены импортом из `modules.auth` — см. журнал §9.
6. **[P0][DONE — 30.09.2026]** Синхронизация: X96-правки (CSRF base_app,
   recycling, favicon) забраны в репо, `terminal.html` починен на X96,
   `monitor.py` задеплоен, `.gitattributes` добавлен, `apps\*.html` удалены —
   см. журнал §9.
7. **[P1][DONE — 30.09.2026]** Схема БД: DDL из `get_db()` → однократная
   инициализация (startup), `PRAGMA user_version`, индекс `events(ip, id)`,
   `finally`-закрытие коннектов — см. журнал §9.
8. **[P1][DONE — 30.09.2026]** Фоновые задачи: guard от повторного запуска
   сканов (scan/inventory/bluetooth), удалён мёртвый `init_background_tasks`
   и дубли функций (`app.py` ↔ `core_routes.py`) — см. журнал §9.
9. **[P1][DONE — 30.09.2026]** Observability: `/api/health` → version/
   uptime/last-discovery/db-status в один ответ — см. журнал §9.
10. **[P1][DONE — 30.09.2026]** Безопасность окружения: security-заголовки,
     cookie-флаги, чистка root/1234 и IP из отслеживаемых файлов (help.html,
     скрипты, демо-пайплайн) — см. журнал §9.
11. **[P1][DONE — 30.09.2026]** Обработка отсутствующих подсистем: probe
     capabilities (nmap/iw/smartctl/…) → `/api/health`, глобальный
     `FileNotFoundError` → дружелюбный 503 (JSON для API), честный отказ
     discovery без nmap (фикс фиктивного `SCAN OK` + интерфейсы `eth0/wlan0`)
     — см. журнал §9.

**PHASE 2 — Configuration (задачи P2):**

12. **[P2][DONE — 30.09.2026]** Хардкоды → `_cfg` (см. §2 строка «Configuration»):
     подключены уже существующие ключи `settings.json` — `network.subnet` в
     сканере/inventory, `scan_interval`/`max_misses` (вместо мёртвых констант
     app/devices/system), `wifi_ifaces` в iw-scan, `traffic_ifaces` в
     мониторинге трафика, self-check IP через `self_ips`,
     `web.flask_host`/`flask_port` в `socketio.run`, удалён мёртвый
     `app.NETWORK` — см. журнал §9.
13. **[P2][DONE — 30.09.2026]** Тест override-конфига: подменённый
     `settings.json` → ленивые хелперы читают новые значения
     (subnet/interval/self_ips), регрессии P1-9/P1-11, восстановление боевых
     настроек — 18/18 PASS, см. журнал §9.
14. **[P2][DONE — 30.09.2026]** Документация: `docs/Конфигурация.md` (все ключи
     `settings.json`, отдельный `network.json`, how-to «новая сеть/платформа»),
     прогон `sanitize_docs` (leaks 0), журнал §9 — см. журнал §9.

**PHASE 3 — Hardware abstraction (задачи P3):**

15. **[P3][DONE — 30.09.2026]** `core/hardware.py`: `thermal_zone_path()`
     (перебор зон, не только `zone0`), `thermal_temp()`, `hdd_device()`,
     `emmc_device()`, `sd_device()`, `board_model()`, `detect_platform()`;
     убраны хардкоды `thermal_zone0`/`mmcblk2`/`/dev/sda` в `system_routes`
     (status/health/disks/smart/io-ticks) и `monitor`; clone-watcher берёт
     устройство цели из cmdline `dd of=`; `platform`-блок в `/api/health` —
     см. журнал §9.
16. **[P3][DONE — 30.09.2026]** Тест PHASE 3 — 22/22 PASS (unit + API + live;
     на X96: eMMC=`mmcblk2`, SD=`mmcblk1`, hdd=None, thermal 48°C,
     smart → «диск не обнаружен»), см. журнал §9.

**PHASE 6 — Discovery engine (задачи P6):**

17. **[P6][DONE — 30.09.2026]** Выделен движок: новый `core/discovery.py` —
     `parse_scan` (normalizer), `run_scan` (scanner: один цикл по
     `network.scan_ifaces`, raw-вывод nmap **без двойного парсинга/синтеза**,
     FileNotFoundError → None), `reconcile(con, current, now)` (вся DB-логика:
     NEW/ONLINE/OFFLINE/misses + **MAC_CHANGED**), `scan_loop`, статус,
     `start_scan_thread`; `devices_routes.py` → реэкспорт + роуты; импорты
     `app.py`/`system_routes` не изменились — см. журнал §9.
18. **[P6][DONE — 30.09.2026]** Manual scan: `POST /api/scan`
     (`{subnet?, ifaces?}` one-shot, admin-only, не пишет settings) →
     run_scan + reconcile, JSON `{ok, devices, stats, subnet}`; кнопка
     «🔍 Сканировать» в `templates/devices.html` (только admin;
     fetch-wrapper base.html сам ставит X-CSRFToken).
19. **[P6][DONE — 30.09.2026]** Трассируемость: смена MAC → событие
     `MAC_CHANGED` в `events` (name/device_type по-прежнему обнуляются);
     видно в `/history` и на странице устройства.
20. **[P6][DONE — 30.09.2026]** Тест PHASE 6 — 30/30 PASS (unit parse_scan/
     reconcile на временной БД: NEW → MAC_CHANGED → misses → OFFLINE → ONLINE,
     живой run_scan 22 хоста, POST /api/scan 403/400/ok, кнопка в devices,
     регрессии health/platform), см. журнал §9.

**PHASE 7 — Event engine (задачи P7):**

21. **[P7][DONE — 30.09.2026]** Схема events v2: `SCHEMA_VERSION = 2` —
     колонки `severity`/`source`/`metadata` (JSON), backfill старых строк по
     типу события, индекс `idx_events_event(event)`; боевые 37 119 событий
     сохранены, `integrity_check` ok — см. журнал §9.
22. **[P7][DONE — 30.09.2026]** Фабрика `core/events.py`: `EVENT_SEVERITY`,
     `add_event` (единая точка INSERT, metadata → JSON), `list_events`,
     `event_to_dict`; `core/discovery.py` пишет NEW/ONLINE/OFFLINE/
     MAC_CHANGED через фабрику (severity: info/warning, source: discovery).
23. **[P7][DONE — 30.09.2026]** `GET /api/events` (login; `limit`/`event`/
     `severity`/`ip`/`source`, JSON с парсингом metadata) + колонка «Уровень»
     (цветовой бейдж) в `/history`.
24. **[P7][DONE — 30.09.2026]** Тест PHASE 7 — 30/30 PASS (unit фабрики и
     reconcile, миграция v2 на боевой БД, API-фильтры, UI, регрессии P6/P3,
     live health `user_version=2`), см. журнал §9.

**PHASE 5 — Database (задачи P5):**

25. **[P5][DONE — 30.09.2026]** Формальная система миграций:
     `MIGRATIONS = ((1, _m1), (2, _m2))` в `init_db_schema` — строго по
     `PRAGMA user_version`, каждый шаг своя функция с логом; v1 = базовая
     схема devices/events, v2 = severity/source/metadata + `idx_events_event`
     + backfill; на чистой БД путь 0→1→2 исполняется пошагово — см. §9.
26. **[P5][DONE — 30.09.2026]** Ensure-таблиц: `CREATE TABLE IF NOT EXISTS`
     для 8 таблиц, у которых CREATE жил только на сервере (env_data,
     mchs_alerts, weather_alerts/daily/forecast/forecast_history/hourly/
     observations — точный DDL из боевой БД) + индекс
     `idx_weather_observations_timestamp_unique` — восстановление на чистой
     системе даёт полную схему — см. §9.
27. **[P5][DONE — 30.09.2026]** Retention событий: settings
     `events.retention_days` (default 180, 0 = выкл),
     `core/events.cleanup_old_events()` (парсинг DD.MM.YYYY, DELETE
     батчами) — чистка при старте + ежедневный daemon-поток
     `retention_loop` из `app.py __main__` — см. §9.
28. **[P5][DONE — 30.09.2026]** Тест PHASE 5 — 24/24 PASS (пошаговый путь
     v1→v2 на чистой БД с логами `DB MIGRATION`, ensure 8 таблиц, retention
     unit, боевая БД integrity ok, health/user_version=2, регрессии,
     live) — см. журнал §9.
29. **[P13][DONE — 30.09.2026]** pytest-структура в репо: `tests/unit`
     (не требуют сети/панели) + `tests/live` (маркер `live`, скипаются,
     если панель недоступна), `tests/conftest.py` (фикстуры events_con /
     devices_db / no_dns), `pytest.ini` (по умолчанию `-m "not live"`),
     `requirements-dev.txt` (pytest) — см. §9.
30. **[P13][DONE — 30.09.2026]** Набор тестов: **42 unit** — discovery
     (parse_scan, run_scan с моками subprocess, reconcile NEW/ONLINE/
     misses/OFFLINE/MAC_CHANGED, get_scan_status, guard scan-потока),
     events (severity-карта, фильтры, JSON metadata, retention unit),
     hardware (переносимые проверки Win/CI/X96), миграции (шаги v1/v2,
     идемпотентность, полный init, ensure-таблицы, retention_days),
     config (`_cfg`/`_scan_interval`/`_max_misses` через monkeypatch
     load_settings); **5 live** — health-форма, anon-редирект,
     login+`/api/events`, страницы, `/api/currencies`. Прогнано локально
     (Win/py3.12/pytest 8) и на X96 (venv/pytest 9) — см. §9.
31. **[P13][DONE — 30.09.2026]** CI: `.github/workflows/ci.yml` — на
     push/PR в main: ubuntu + Python 3.11 + `pip install -r
     requirements.txt -r requirements-dev.txt` → `pytest tests/unit -v` +
     py_compile core/app/modules; timeout 15 мин, cache pip — см. §9.

---

## 7. Статусы фаз roadmap

| Фаза | Статус | Комментарий |
|---|---|---|
| PHASE 0 Audit | **DONE** | этот документ; код не менялся |
| PHASE 1 Stabilization | **DONE** | задачи 7–11 done |
| PHASE 2 Configuration | **DONE** | задачи 12–14: хардкоды → `_cfg`, тест override, docs/Конфигурация.md |
| PHASE 3 Hardware abstraction | **DONE** | задачи 15–16: `core/hardware.py` (detect_platform/thermal/storage), убраны хардкоды thermal_zone0/mmcblk2/sda, platform в health |
| PHASE 4 X96 Max port | **IN PROGRESS (частично)** | новый код уже работает на aarch64; расхождение repo↔X96 устранено (§5); остаётся OP (старая версия) |
| PHASE 5 Database | **DONE** | задачи 25–28: MIGRATIONS-карта по user_version, ensure 8 «серверных» таблиц, retention events (180д), тест 24/24 |
| PHASE 6 Discovery engine | **DONE** | задачи 17–20: `core/discovery.py` (scanner/normalizer/reconcile), `POST /api/scan` + кнопка, событие MAC_CHANGED |
| PHASE 7 Event engine | **DONE** | задачи 21–24: events v2 (severity/source/metadata, SCHEMA_VERSION=2), `core/events.py`, `GET /api/events`, бейджи в /history |
| PHASE 8 Security hardening | **IN PROGRESS** | задачи 1–6 (P0) + 10 (P1-10); root-PTY/dev-Werkzeug дефернуты |
| PHASE 9 Installer | **PENDING** | |
| PHASE 10 Update/rollback | **PENDING** | |
| PHASE 11 Backup/Recovery | **PARTIAL** | бэкап БД готов; restore на чистую систему не проверен → не DONE |
| PHASE 12 Observability | **DONE** | P1-9: `/api/health` + version/uptime/last-discovery/db-status |
| PHASE 13 Testing | **DONE** | задачи 29–31: pytest-структура (unit 42 / live 5, маркер `live`), CI GitHub Actions (ubuntu/py3.11: pytest unit + py_compile) на каждый push/PR |
| PHASE 14 Documentation | **PARTIAL** | docs/ есть, `Архитектура.md` устарел, комплекта нет |
| PHASE 15 Production 1.0 | **PENDING** | зависит от P0/P1 выше |
| PHASE 16 After 1.0 | **DEFERRED** | по правилу — после стабильного ядра |

---

## 8. Остаточные риски

1. **Двойное сканирование:** обе платформы активны и сканируют одну подсеть каждые 30 с
   (см. AGENTS.md — «остановить на OP при необходимости»). Решение: определить, какая
   копия основная, вторую — остановить либо вынести скан в «только одна».
2. **Дрейф кода:** правки на серверах без коммита (и наоборот) уже случились (§5);
   текущий регламент (ручной) не гарантирует синхронизацию.
3. **Werkzeug dev-сервер под root на 0.0.0.0** — терпимо только в закрытой LAN до P1.
4. **X96 без HDD, boot с SD** — тестовый режим: эММС/диск-функции (clone/backup-emmc)
   на нём неприменимы, UI-блоки должны корректно прятаться (частично решено модулями).
5. **Внешние CDN** (xterm.js, socket.io) — терминал не работает без интернета;
   local-first-принцип нарушается для этой функции.

---

## 9. Журнал выполнения

### 30.09.2026 — P0-1: авторизация веб-терминала и SocketIO CORS — **DONE**

**Проблема (B1):** `terminal_start` без авторизации → root-PTY `/bin/bash`;
`cors_allowed_origins="*"` → любой origin мог держать socketio-соединение.

**Изменения:**
- `app.py` — `SocketIO(app, async_mode="threading")`: убран `cors_allowed_origins="*"`
  (default python-socketio = same-origin only, проверено по source venv);
- `modules/core_routes.py` — `_socket_is_admin()` (session → admin + enabled),
  `connect` возвращает `False` для не-admin; проверка на каждом terminal-событии
  (`terminal_start/input/resize`) с принудительным закрытием сессии; вычистка
  `terminal_stop`/`disconnect` через общий `_terminal_drop()`.

**Файлы:** `app.py`, `modules/core_routes.py` (repo == X96 после деплоя).

**Деплой:** бэкапы `app.py.backup-20260930-032130`, `core_routes.py.backup-20260930-032130`
→ pscp → `py_compile` OK → `systemctl restart lan-discovery` → active.

**Тесты (X96, `/tmp/test_terminal_auth.py`, 9/9 PASS):**
анонимный socketio-connect отклонён; admin login 302 + `GET /` 200;
admin socket connect + реальный вывод терминала (MOTD); после disconnect —
0 процессов `bash --login`; smoke: `/api/health` 200, `/login` 200, `/` 302 (неавториз.).

**Остаточные риски:** PTY по-прежнему от root (правка прав — отдельная задача);
`/apps/terminal` страница доступна не-admin (шаблон показывает заглушку) — ок;
socketio-события не покрываются CSRF (смягчено same-origin + session-auth);
Cross-Site WebSocket Hijacking закрыт Origin-проверкой python-socketio.

**Наблюдение (не блокер):** в первом bash-сеансе терминала появляется
«Waiting for system to finish booting…» и «Create root password:» —
армбиевский profile-sкрипт на медленном первом выводе; не связано с этим
изменением (логика `terminal_start` не менялась), вынести в отдельную проверку.

### 30.09.2026 — P0-2: filemanager admin-only + валидация путей — **DONE**

**Проблема (B2):** корень `/`, `shutil.rmtree`/`os.remove`/`shutil.move` под
только `@login_required` — guest мог изменять файловую систему от root.

**Изменения:**
- `modules/core_routes.py` — 7 роутов `/api/filemanager/*` → `@admin_required`;
  хелпер `_fm_path()` (строка, без null-байт, абсолютный после `normpath`) → 400;
  явный запрет `delete /` и `move /`;
- `templates/apps/filemanager.html` — `{% if current_user.role != 'admin' %}`
  заглушка (по образцу terminal).

**Файлы:** `modules/core_routes.py`, `templates/apps/filemanager.html`
(repo == X96 после деплоя). Бэкапы `*.backup-20260930-032856`.

**Тесты (X96, `/tmp/test_filemanager_auth.py`, 16/16 PASS):**
аноним: list→403, POST без CSRF→400 (CSRFProtect), POST с валидным CSRF→403;
admin: list→200, страница с UI; не-admin (`user`): list/read→403, страница→заглушка;
валидация: относительный путь→400, null-байт→400; регресс: health/login/apps.
Временный пароль `user` тест-account: users.json → бэкап → тест → **восстановлен**.

**Остаточные риски:** guest/editor больше не имеют доступа к filemanager
(изменение поведения — задокументировать); `/api/player/*` (browse/playlist без
нормализации путей) — отдельная задача hardening (см. P1-10).
(B6 про base_app CSRF — решён в P0-6.)

### 30.09.2026 — P0-3: авторизация network-роутов + валидация host/MAC — **DONE**

**Проблема (B3):** `/api/network/check` и `/api/network/check_host` (POST, host из
JSON → внешняя команда) были без авторизации; nettools передавали `host` в argv
без проверки (argument injection через ведущий `-`); bluetooth MAC уходил в stdin
`bluetoothctl` без проверки (инъекция команд).

**Изменения (только `modules/network_routes.py`):**
- оба `/api/network/check*` → `@login_required`;
- `_valid_host()`: `[A-Za-z0-9][A-Za-z0-9._:-]{0,252}`, без `/`, без ведущего `-`,
  без пробелов → иначе 400; применён к `check_host`, `ping`, `dns`, `ports`, `trace`;
- `_valid_mac()`: строгий формат `XX:XX:XX:XX:XX:XX` → иначе 400; применён к
  `connect`, `disconnect`, `pair`, `remove`.

**Файл:** `modules/network_routes.py` (repo == X96 после деплоя).
Бэкап `network_routes.py.backup-20260930-033214`.

**Тесты (X96, `/tmp/test_p03_network.py`, 29/29 PASS):**
аноним: GET check→302, POST no-csrf→400, POST с CSRF→302;
admin: check→200, check_host(127.0.0.1)→200 online=true;
инъекции: `-c`, `--help`, `a b`, `path`, tab, пустые → 400 (все 4 nettools тоже);
валидные host → работают (ping реальный вывод); bt-инъекция
`AA:BB\npower off` → 400; регресс: config/health/nettools/bluetooth/index.

**Остаточные риски:** `/api/monitoring/<ip>` (SSRF на `:19999`) и
`/api/nettools/ports` (произвольный target) — features, но нужна валидация/белый
список при hardening (P1-10); hosts из `/api/network/config` (user-editable)
проходят ту же валидацию при проверке — несовместимые старые значения дадут 400
(поведение видимое, не тихое).

### 30.09.2026 — P0-6: синхронизация repo ↔ X96 — **DONE**

**Проблема (B6 + §5):** репозиторий и X96 разошлись в 19 файлах: сервер впереди
(CSRF-meta в `base_app.html`, retry в `recycling.py`, favicon в `login.html`),
репо впереди (`monitor.py` с ThreadPoolExecutor, `terminal.html` без испорченной
кодировки), 14 файлов различались EOL, на сервере — 7 junk-файлов
`templates/apps\*.html` (буквальный backslash). Риск: любой пуш/деплой «как есть»
ломает CSRF во вкладках или терминал.

**Изменения:**
- **server→repo:** `templates/base_app.html` (+24: csrf-meta + fetch-обёртка),
  `modules/recycling.py` (3 попытки запроса vitaminstir), `templates/login.html` (+1 favicon);
- **repo→server:** `modules/monitor.py` (ThreadPoolExecutor, timeout=3),
  `templates/apps/terminal.html` (восстановлен), 14 EOL-only файлов;
- **новое:** `.gitattributes` (`* text=auto eol=lf`, бинарные исключения);
- **удалено с сервера:** 7 файлов `templates/apps\*.html` → перемещены
  (не удалены) в `/tmp/junk-templates-20260930-034105/`;
- бэкапы: `templates/apps/terminal.html.backup-20260930-033734`,
  `modules/monitor.py.backup-20260930-033734`.

**Тесты (X96, `/tmp/test_p06_sync.py`, 13/13 PASS):** admin login; terminal.html
содержит xterm-код без мозги; `/monitoring` 200; `/api/monitoring/127.0.0.1` →
JSON с `cpu`/`ram` (get_system_overview); csrf-meta и fetch-обёртка есть в
вкладках; регресс `/`, filemanager, nettools, bluetooth, health.
Загруженные `.py` прошли `py_compile`, сервис перезапущен, active.

**Сверка md5 (финальная, `filelist_host.py` + compare):** exact=120,
EOL-only=0, content_diff=0, только на сервере=0 — **repo == X96 байт-в-байт**.

**Остаточные риски:** OP (Orange Pi) остался на старой версии (нет `modules/`) —
отдельная задача (дублирование сканов, остановка сервиса на OP); junk-файлы
лежат в `/tmp` (перезагрузка сотрёт — ок); `modules/*_b64.txt` в git — чистка P4.

### 30.09.2026 — P0-4: сейф — Fernet + миграция + can_edit — **DONE**

**Проблема (B4):** «шифрование» сейфа = `b64(HMAC[:16] || plaintext)` — пароли
лежали открытым текстом (base64), HMAC при расшифровке **игнорировался**
(`if h == raw: return text; return text`), все 4 API — только `@login_required`
(guest читал все пароли), неудачная расшифровка приводила к двойному шифрованию
при следующем сохранении.

**Изменения:**
- `modules/core_routes.py`:
  - `_secrets_fernet()` — ключ из отдельного файла `secret.key` (32 байта;
    64-байтовый hex → fromhex; иначе sha256-дедукция; chmod 600 при создании);
  - `_secrets_encrypt/decrypt` — Fernet (AES-128-CBC + HMAC-SHA256);
    fallback на legacy base64+HMAC с **реальной** проверкой HMAC;
  - `_load_secrets` — legacy-записи мигрируют в Fernet при первом чтении
    (с бэкапом `secrets.json.backup-<ts>`); нечитаемые → id в `_enc_ids`,
    пишутся обратно без изменений (без двойного шифрования);
  - `_save_secrets` — не мутирует вход, атомарная запись (tmp+`os.replace`),
    chmod 600;
  - 4 роута `/api/secrets*` → `@login_required` + `@can_edit` (guest → 403);
    create/update сбрасывают флаг `_enc_ids` (новый пароль шифруется);
- `templates/apps/passwords.html` — UI-гейт `isRoot` admin → `!= 'guest'`
  (соответствует can_edit), текст заглушки;
- `requirements.txt` — `cryptography>=42,<47` (venv на X96: pip install OK).

**Файлы:** `modules/core_routes.py`, `templates/apps/passwords.html`,
`requirements.txt` (repo == X96). Бэкапы `*.backup-20260930-034959`.

**Тесты (X96):**
- миграция `/tmp/test_p04_migration.py` **18/18**: legacy→Fernet (бэкап 1 раз,
  без повторной миграции), mode 600, битая legacy-запись сохраняется как есть
  (без double-encrypt), roundtrip, мутации не утекают в вызывающий код;
- HTTP `/tmp/test_p04_secrets.py` **29/29**: аноним 302/400, guest все методы→403,
  user GET/POST/DELETE→200 (can_edit), admin CRUD, на диске — Fernet-токен
  `gAAAA…` вместо plaintext, mode 600, обновлённый пароль тоже шифруется;
  регресс страницы/health. users.json (пароли user/guest) — бэкап→тест→восстановлен.
- финальное состояние: `secrets.json` = `[]`, mode 600; лог без ошибок.

**Остаточные риски:** пароль пользователя при смене передаётся в открытом виде
по HTTP (панель без TLS — вне scope P0, см. hardening); `_fernet_cache` кэширует
ключ в памяти процесса (ok); конкурентная запись `secrets.json` двумя
запросами theoretically possible (single-process, низкий риск) — при необходимости
file-lock в P1.

### 30.09.2026 — P0-5: auth — enabled/TTL/мин. длина/re-hash — **DONE**

**Проблема (B5):** `get_current_user` не проверял `enabled` — отключённый
пользователь продолжал работать со старой сессией («выключение» не действовало
до истечения куки); `_verify_hash` принимал SHA-256 навсегда (fast-hash без
salt); смена пароля — `len(pw) < 1`; TTL сессий отсутствовал; в `core_routes`
жили дубли `_hash/_verify_hash/load_users/save_users/get_current_user`
(контекст-процессор мог расходиться с декораторами).

**Изменения:**
- `modules/auth.py`:
  - `SESSION_TTL = 12*3600`; `get_current_user` — нет `login_ts` (старые
    сессии)/истёк TTL/`enabled=false`/нет юзера → `session.pop` + None
    (logout для всех декораторов и SocketIO);
  - логин: `session["login_ts"] = now`; legacy SHA-256-хэш → **однократный
    re-hash bcrypt при первом успешном входе** (без локаута);
- `modules/core_routes.py`:
  - дубли хелперов → `from modules.auth import ...` (единый источник);
  - `POST /api/users/<u>/password`: `len(pw) < 8` → 400
    (UI `sys-users/block.html` показывает `d.error` — без правок);
- `requirements.txt` не менялся.

**Файлы:** `modules/auth.py`, `modules/core_routes.py` (repo == X96).
Бэкапы `*.backup-20260930-035630`.

**Тесты (X96):**
- юнит `/tmp/test_p05_unit.py` **17/17**: нет login_ts/TTL истёк/отключённый
  → None + pop; валидная сессия → admin; sha256/bcrypt verify; core делегирует
  в auth (`is`-идентичность); min-8 в исходнике;
- HTTP `/tmp/test_p05_auth.py` **23/23**: отключение юзера «вживую» выбивает
  старую сессию (302) и после включения сессия остаётся мёртвой (re-login);
  отключённый не может войти; пароль 7 симв. → 400, 8 → 200; вход с SHA-256 →
  302 и хэш в users.json становится `$2b$…`; регресс pages/health/api/users.
  users.json: бэкап → setup → тест → **восстановлен**.

**Остаточные риски:** все существующие на момент апгрейда сессии выкидываются
(нет login_ts) — однократный ре-логин; SHA-256-аккаунты, ни разу не вошедшие,
остаются sha256 до первого входа (детект: `grep -v '$2' users.json`); TTL
фиксированный 12ч (конфигурируемый — P2 Configuration).

### 30.09.2026 — P1-7: схема БД — однократный init, user_version, индекс — **DONE**

**Проблема:** DDL и ALTER-миграции колонок выполнялись в `get_db()` на **каждом**
подключении (лишняя работа + шум в логе); `PRAGMA user_version = 0` (аудит §3 —
миграции не версионированы); нет индекса `events(ip, id)` — `/history` и
`/device/<ip>` (35 836 событий) делают полный скан; `con.close()` без `finally`
— при исключении коннект утекал (scan_loop, все 5 роутов, `weather_current`
в `app.py` и `core_routes`).

**Изменения:**
- `modules/devices_routes.py`:
  - `init_db_schema(force=False)` — весь DDL + миграции колонок +
    `CREATE INDEX IF NOT EXISTS idx_events_ip_id ON events(ip, id)` +
    `PRAGMA user_version = 1` (если `< 1`), под `threading.Lock`, идемпотентна
    (повторный вызов → `False`), коннект закрывается в `finally`;
  - `get_db()` — только connect + `busy_timeout`/WAL + авто-вызов init, пока
    не done (после init DDL не выполняется — проверено: число объектов
    в `sqlite_master` не меняется);
  - `scan_loop` — `con = None` до `try`, закрытие в `finally` (устранена утечка
    при `SCAN ERROR`); роуты `index/history/device/set_name/dismiss_new` —
    `try/finally` (в `device` not-found return тоже через finally);
- `app.py`: `init_db_schema()` в `__main__` до `start_scan_thread()`;
  `weather_current()` — `close` в `finally` (при исключении в запросе утекал);
- `modules/core_routes.py`: `weather_current()` — вложенный `try/finally`
  вокруг запроса.

**Файлы:** `modules/devices_routes.py`, `app.py`, `modules/core_routes.py`
(repo == X96 после деплоя). Бэкапы: `*.backup-pre-p07-20260930-070508` (до
правки, из git HEAD), `*.backup-20260930-070645`; БД
`devices.db.backup-p07-*` (integrity ok, 40 devices / 35 836 events).

**Тесты (X96, `/tmp/test_p07_db.py` 22/22 PASS):**
- prod: `user_version = 1`, индекс существует и используется
  (`SEARCH events USING INDEX idx_events_ip_id (ip=?)`), integrity ok,
  данные не потеряны (40 / 35 836 → 40 / 35 836);
- fresh-DB (tmp): init создаёт таблицы, все колонки, индекс, version; повторный
  init — no-op; `get_db()` работает без DDL; `sqlite_master` count не растёт;
- HTTP: admin login 302, `/` `/history` `/device/<ip>` 200, unknown 404,
  `set_name`/`dismiss-new` на несуществующий IP 302/200 (без мутаций), health 200;
- после рестарта в журнале: `DB SCHEMA INIT: version=1` + `SCAN OK` каждые 30 с
  (скан-поток жив), без traceback.

**Остаточные риски:** OP работает со старой версией кода (нет `modules/`) —
при синке получит init автоматически при старте; DDL других модулей
(currencies/inventory/recycling/weather-monitor) — свой idempotent init вне
`get_db()`, не трогался (полноценная миграционная система — PHASE 5 позже).

### 30.09.2026 — P1-8: фоновые задачи — guard'ы + удаление мёртвого/дублей — **DONE**

**Проблема:** `start_scan_thread()` без guard — повторный вызов дал бы второй
скан-поток; `/inventory/scan` и `/api/bluetooth/scan` без lock — повторный
POST → параллельные nmap/bluetoothctl-прогоны (race + лишняя нагрузка);
в `core_routes.py` жил **мёртвый** `init_background_tasks` (не вызывается
нигде) вместе с мёртвыми дублями `update_currencies/recycling_background`,
блоком alarm-helpers (`_alarm_scheduler` и др. — живая копия в `media_routes`)
и дублями `weather_current`/`check_internet*`/`page_data` из `app.py`
(два независимых кэша, два источника weather/internet); в `devices_routes`
— мёртвая пара `check_internet*`.

**Изменения:**
- `modules/devices_routes.py` — `start_scan_thread()`: `_scan_lock` +
  `_scan_thread`, повторный вызов возвращает уже запущенный поток
  (no-op); удалены мёртвые `check_internet/check_internet_cached` + `_inet_cache`;
- `modules/inventory_routes.py` — модульный `_inv_scan_lock` +
  `_spawn_inventory_scan()`: `acquire(blocking=False)` → при занятости
  `False` (маршрут по-прежнему 302), `release` в `finally`; импорт
  `modules.inventory` вынесен на уровень модуля;
- `modules/network_routes.py` — `_bt_scan_lock` + `_spawn_bt_scan()`
  (scan on → 30 c → scan off, `release` в `finally`); ответ
  `{"ok": true, "already_running": <bool>}`;
- `modules/core_routes.py` — удалены `init_background_tasks`,
  `update_*_background`, alarm-блок (`ALARM_FILE/_load_alarms/_save_alarms/
  _alarm_scheduler` — полностью живёт в `media_routes`),
  `weather_current/check_internet*/_page_data_cache/_inet_cache`;
  `page_data()` → делегат `app.page_data` (единый кэш и источник).

**Файлы:** `modules/{core_routes,inventory_routes,network_routes,devices_routes}.py`
(repo == X96 после деплоя). Бэкапы `*.backup-pre-p08-20260930-072054` (4 файла).

**Тесты (X96, `/tmp/test_p08_guards.py` 32/32 PASS):**
- unit-guard: scan (повторный вызов → тот же thread), inventory
  (True → False → после завершения True, ровно 2 прогона, lock свободен),
  bluetooth (True → False, lock захвачен, `scan on` отдан потоку);
- удаление: 8 проверок отсутствия символов в core/devices; `media_routes`
  живой (alarm scheduler + helpers на месте);
- делегация: `core.page_data() is app.page_data()` (один кэш), ключи
  weather/internet/interval/max_misses;
- HTTP: login 302; `/` `/apps` `/currencies` `/inventory` `/history` 200;
  `/inventory/scan` x2 → 302/302; bt-scan 1-й `already_running:false`,
  2-й **`already_running:true` (guard подтверждён на сервисе)**;
  `/api/alarms` 200; health 200;
- журнал после рестарта: `SCAN OK` каждые 30 с (один поток), без
  Traceback/ImportError.

**Остаточные риски:** UI inventory-скана не показывает прогресс (вне scope);
`system_routes`/`weather_routes` имеют локальные обёртки `page_data/
weather_current`, но делегируют логику в `app`/`weather` — не дублируют её;
мусорные `app_copy.py`/`patch_app.py`/`app_remote.py` не трогались.

### 30.09.2026 — P1-9: Observability — /api/health: version/uptime/last-discovery/db — **DONE**

**Проблема:** `/api/health` отдавал только `checks` (database/disk/ram/cpu_temp)
+ timestamp — ни версии панели, ни аптайма, ни статуса discovery, ни состояния
БД (§2 Observability: «состояние видно только через UI»).

**Изменения:**
- `app.py` — `APP_VERSION = "0.9.0"` и `_SERVICE_START = time.time()`
  (единый источник версии и аптайма процесса);
- `modules/devices_routes.py` — `_scan_status`
  (`last_scan/last_ok/last_error/errors`) обновляется в `scan_loop`
  (успех / ошибка / пустой вывод); `get_scan_status()` добавляет
  `interval_sec` и `thread_alive`;
- `modules/system_routes.py` — `/api/health`:
  - db-check одним коннектом → объект `db` `{status, path, size_bytes,
    journal_mode, user_version, devices, events}`;
  - новые поля: `version`, `uptime` `{host_sec (/proc/uptime), service_sec}`,
    `last_discovery` `{scan, ok, error, errors, interval_sec, thread_alive}`,
    `db`;
  - легаси-ключи `ok/checks/timestamp` и коды 200/503 не менялись.

**Файлы:** `app.py`, `modules/devices_routes.py`, `modules/system_routes.py`
(repo == X96 после деплоя). Бэкапы `*.backup-pre-p09-20260930-072700` (3 файла).

**Тесты (X96, `/tmp/test_p09_health.py` 22/22 PASS):**
- health 200/`ok=true`; legacy `checks` (database="ok"+disk/ram/cpu_temp) и
  `timestamp` в прежнем формате;
- `version == 0.9.0`; uptime: host 118128 c, service 9.8 c (service ≤ host);
- `last_discovery`: scan/ok в формате DD.MM.YYYY HH:MM:SS (первый скан
  после рестарта отработал), `thread_alive=true`, `interval_sec=30`,
  `errors=0`, `error=null`;
- `db`: status ok, `user_version=1`, `journal_mode=wal`, devices=40,
  events=35836, size 6.3 МБ;
- `get_scan_status()` доступен из другого процесса; регрессии: login 302,
  `/` `/history` `/system` `/api/system/health` 200; журнал — `SCAN OK`,
  без Traceback.

**Остаточные риски:** version — константа в `app.py` (в settings переедет
в P2 Configuration); `service_sec` считается от импорта app.py (≈ старт
процесса); unauth-доступ `/api/health` сохранён осознанно (мониторинг
без входа в закрытой LAN; роут добавлен ещё в P0-3-регламенте «по решению»).


---

### 30.09.2026 — P1-10: Безопасность окружения — заголовки/куки/чистка секретов + фикс публичной утечки demo — **DONE**

**Проблема:** публичный демо-слепок (`kotmartovskiy.github.io/Lan-discovery-demo`)
отдавал `SSH root / 1234` и реальную топологию `192.168.3.x` (включая имена
файлов `device-192.168.3.x.html`); панель не ставила security-заголовков и
cookie-флагов; 10 отслеживаемых скриптов содержали `password='1234'` и
рабочие IP.

**Изменения:**
- `app.py`: `SESSION_COOKIE_HTTPONLY=True`, `SESSION_COOKIE_SAMESITE=Lax`,
  `SESSION_COOKIE_SECURE=False` (панель по HTTP в LAN — иначе вход сломается);
  after_request `_security_headers` → `X-Content-Type-Options: nosniff`,
  `X-Frame-Options: SAMEORIGIN`, `Referrer-Policy: same-origin` (setdefault,
  не дублирует чужие). CSP не вводится — CDN xterm/socket.io (residual).
- `templates/help.html`: `root / 1234` → «пароль задан при установке»;
  `(пароль: 1234)` → «пароль — от root-аккаунта…». IP-таблицы в исходнике
  сохранены (UX панели) — скрабятся при публикации.
- `tools/make_demo.py`: `scrub_net_secrets()` — `192.168.3.x → 192.168.1.x`,
  пароль-литералы → `••••`; применяется в HTML- и JSON-проходах **и в именах
  файлов** (`write_file`, ключи/значения `page_map` — синхронно со скрабом
  HTML до `transform`); логин генератора — env `LAN_PANEL_PASS` (без литерала).
- `tools/demo_lint.py`: `check_net_secrets()` — контент (html/json/js/css) и
  **имена файлов** на `192.168.3.` + паттерны `root/1234`, `пароль: 1234`,
  `password=1234`; позитив-контроль: старый слепок → 123 ошибки.
- Скрипты (env, без дефолтов): `deploy.py`, `deploy_templates.py`,
  `find_tv.py`, `install_xplore.py`, `remote_edit.py`, `ssh_query.py`,
  `tv_adb.py` → `LAN_SSH_HOST/LAN_SSH_USER/LAN_SSH_PASS` (+`LAN_TV_ADB`,
  `LAN_TV_IP`); `test_api_auth.py`/`test_status.py`/`test_sys.py` →
  `LAN_PANEL_PASS`.

**Деплой:** бэкапы `*.backup-pre-p10-20260930-074345` (app.py, help.html,
make_demo.py); демо регенерировано на боксе (`LAN_PANEL_PASS=…`), скачано,
`tools/demo_lint.py` → **LINT OK: 188 files, net/secret leaks: 0**.

**Тесты (X96, `/tmp/test_p10_env.py` 27/27 PASS):**
- заголовки на `/login`, `/api/health`, `/`, `/system`, `/static/style.css`;
- Set-Cookie: `HttpOnly` + `SameSite=Lax`, без `Secure`; login → 302;
- health: version 0.9.0, db {status ok, user_version 1, devices 40,
  events 35836}, uptime, last_discovery (P1-9-регрессия);
- `/help`: без `root / 1234` и `пароль: 1234`, IP-таблица сохранена (UX);
- регрессии: CSRF анонимный POST → 400, без сессии → 302, no-store на API,
  журнал без Traceback, `SCAN OK`.

**Публикация:** чистый слепок отправлен в `Lan-discovery-demo` (GitHub Pages)
— живая утечка `root/1234` + IP на публичном сайте закрыта.

**Остаточные риски:** root-PTY и dev-Werkzeug (`allow_unsafe_werkzeug`)
дефернуты вне scope задачи 10; IP в функциональных дефолтах кода
(`NETWORK`, monitoring/web-хосты, default hosts, `nettools` placeholder,
исходник `help.html`) — ок для приватного репо, скрабятся демо-пайплайном;
`patch_app.py`/`remote_edit.py` — исторические one-off (IP внутри payload);
`AGENTS.md` содержит SSH-креды осознанно (ops-файл приватного репо, не
публикуется; `sanitize_docs` его не трогает); CSP не введён; регенерация
демо требует `LAN_PANEL_PASS` в окружении.

### 30.09.2026 — P1-11: Изоляция сбоев — барьер отсутствующих подсистем + фикс фиктивного discovery — **DONE**

**Проблема:** панель не имела ни одного errorhandler; отсутствующий внешний
бинарь (nmap, iw, host, tracepath, smartctl…) давал грубый 500 с errno;
зависимости нигде не декларировались. В ходе задачи обнаружен скрытый баг:
на X96 discovery **фальшивил успех** — `SCAN OK: 4 devices` каждые 30с, при
этом nmap не был установлен вообще, а `run_scan` был захардкожен на интерфейсы
Orange Pi (`end0`/`wlan1`; на X96 — `eth0`/`wlan0`), поэтому реально сканировались
только `self_ips` — online держался 4 с 28.09 (реальные хосты заморожены в БД).

**Изменения:**
- `app.py`: `import shutil` + `from html import escape`; блок P1-11 перед Auth:
  `CAPABILITY_PROBES` (nmap, ping, tracepath, host, iw, bluetoothctl, smartctl,
  ffmpeg, mpv, lsblk) → `probe_capabilities()` → `app.config["CAPABILITIES"]` +
  warning `MISSING DEPS: …` при старте; глобальный
  `@app.errorhandler(FileNotFoundError)` → warning в журнал, `/api/*` → JSON 503
  `{ok:false, error:"не установлена зависимость: …", dependency}`,
  страницы → HTML 503 «функция недоступна» (экранировано, со ссылкой на главную).
- `modules/system_routes.py`: `current_app`; `/api/health` += `capabilities`
  (карта бинарей) и `missing_deps` (список отсутствующих) — легаси-ключи P1-9
  не тронуты.
- `modules/devices_routes.py`: `run_scan` — отдельный `except FileNotFoundError`
  → `log.error("SCAN: nmap не установлен …")` + `return None` (никакого
  фиктивного OK); ветка `output is None` в `scan_loop` → `last_error` +
  `errors += 1` (консистентно с обычной except-веткой); перебор интерфейсов
  `end0 → eth0` и `wlan1 → wlan0` с `break` при найденных хостах.
- На X96 установлена зависимость: `apt-get install nmap` (7.93).

**Деплой:** бэкапы `*.backup-pre-p11-20260930-082725` (app.py,
system_routes.py) + `*.backup-pre-p11-*` (devices_routes.py, два этапа),
py_compile OK, `systemctl restart lan-discovery` → active.

**Тесты (X96, `/tmp/test_p11_deps.py` 30/30 PASS):**
- Part A: capabilities == re-probe `shutil.which`; синтетические роуты с
  несуществующим бинарём → API 503 JSON (`ok:false`+`dependency`) и HTML 503;
- Part B: `PATH=""` — ping/dns/wifi-scan/inventory-scan/главная → **не 500**
  (ping/dns → `ok:false`, inventory → штатный 302); `run_scan()` без nmap →
  `None` (не строка self_ips);
- Part C: health в процессе — capabilities/missing_deps + все поля P1-9;
- Part D: живой сервис — health 200, `missing_deps: [tracepath, host]`,
  nosniff/X-Frame-Options (P1-10-регрессия);
- результат после фикса: `SCAN OK: 19 devices`, online 4 → 19, `last_seen`
  реальных хостов обновляется; журнал без Traceback/SCAN ERROR.

**Остаточные риски:** импорты Python-модулей остаются fail-fast (изоляция
импортов не вводилась — задокументировано); route-level broad except по-прежнему
возвращает 200 `ok:false` с текстом ошибки (криптический errno); барьер ловит
только `FileNotFoundError` (не OSError/TimeoutExpired); `tracepath`/`host` не
установлены и видны в `missing_deps` (демонстрация честной деградации);
`INVENTORY ERROR` печатается в лог фонового потока (не HTTP-статус).

### 30.09.2026 — P2: Configuration — хардкоды → `_cfg` (settings.json), тест override, docs — **DONE**

**Проблема (§2 «Configuration»):** сеть/скан/интерфейсы/порт были захардкожены
в коде при том, что `/etc/lan-discovery/settings.json` уже содержал
`network.subnet`, `scan_interval`, `max_misses`, `self_ips`, `web.flask_port` —
ключами никто не пользовались: настройки из UI «Система → Настройки»
сохранялись, но не применялись; `SCAN_INTERVAL`/`MAX_MISSES` дублировались в
трёх местах (app/devices/system); `app.NETWORK` был мёртвым; `monitor.py`
показывал трафик только `end0/wlan1` (на X96 — пусто).

**Изменения (задача 12):**
- `app.py`: удалены мёртвые `NETWORK` и константы `SCAN_INTERVAL`/`MAX_MISSES`;
  ленивые `_scan_interval()`/`_max_misses()` через `_cfg`; `/api/settings` и
  `socketio.run` → `_cfg("web", "flask_host"/"flask_port", …)`.
- `modules/devices_routes.py`: ленивые `_subnet()`/`_scan_interval()`/
  `_max_misses()` (правки применяются через 10-сек кэш, без рестарта);
  nmap-сканер и offline-логика читают их вместо констант.
- `modules/system_routes.py`: `page_data` (interval/max_misses) и мониторинг
  трафика → `_cfg("network", "traffic_ifaces", …)` (лейблы lan/wifi строятся
  правилом `wlan*` → wifi).
- `modules/inventory.py`: nmap-скан подсети → `_cfg("network", "subnet", …)`.
- `modules/network_routes.py`: `/api/wifi/scan` → перебор
  `_cfg("network", "wifi_ifaces", ["wlan1", "wlan0"])` (вместо двух разворотов).
- `modules/monitor.py`: трафик → `_cfg("network", "traffic_ifaces", …)`
  (дефолт покрывает `end0/eth0/wlan1/wlan0` — обе платформы).
- `modules/monitoring_routes.py`: self-check `/api/monitoring/<ip>` →
  `network.self_ips` вместо хардкода `192.168.3.243`.

**Деплой (задача 13):** бэкапы `*.backup-pre-p2-20260930-091449` (7 файлов),
py_compile OK, restart → active; тест `/tmp/test_p22_config.py` — **18/18 PASS**:
override-подмена settings (subnet `10.99.0.0/24`, interval 77, max_misses 9,
self_ips `10.99.0.5`, flask_port 9099) → все ленивые хелперы читают новые
значения; self-check по новому self_ips → 200 (локальный overview); после
восстановления — боевые 30/6/`192.168.3.0/24`; регрессии: health (P1-9/P1-11),
live-сервис, `SCAN OK: 8–15 devices`, журнал без Traceback.

**Документация (задача 14):** `docs/Конфигурация.md` — таблицы всех ключей
settings.json (кто читает, дефолт, когда применяется), отдельный `network.json`,
`server_ips` помечен «зарезервирован, кодом не читается», how-to «новая
сеть/платформа» + минимальный пример override; `tools/sanitize_docs.py` —
добавлена замена подсети `192.168.3.0/24 → 192.168.1.0/24`, прогон →
**leaks: 0, exit 0**.

**Остаточные риски:** пути `/opt|/etc|/srv` и `network_check.py` остаются
захардкожены (осознанно, задокументированы — правка только под другую структуру
установки); `network.json` исторически отдельный файл (не слит с settings);
`server_ips` в settings не читается кодом (задел); дубли `load_settings`
(app/core/system/weather) читают один файл, но имеют раздельные кэши (10 с);
смена `flask_port` требует рестарта сервиса и правки systemd-юнита/фаервола.

### 30.09.2026 — P3: Hardware abstraction — `core/hardware.py` (PHASE 3) — **DONE**

**Задачи 15–16 (PHASE 3).** Создан `core/hardware.py` — единая точка
hardware-абстракции (без зависимостей от app, module-level импорт безопасен):
- `thermal_zone_path()` — перебор `thermal_zone*/temp` с кэшем 60 с (не только
  `zone0`), `thermal_temp()` — °C или None;
- `hdd_device()` (первый `sd*` в `/sys/block`), `emmc_device()`/`sd_device()`
  (первая `mmcblk*` с `device/type` == MMC/SD, без boot-партиций);
- `board_model()` (device-tree → hostname), `detect_platform()` — кэшированный
  dict `{board, arch, system, emmc, sd, hdd, thermal_zone}`.

**Убранные хардкоды:**
- `modules/system_routes.py`: thermal в `/api/status`, `/api/system/health`,
  `/api/health` (checks.cpu_temp) → `thermal_temp()` (None → «unavailable»);
  io-ticks `(mmcblk2, sda)` → `(emmc_dev, hdd_device())` c guard пропуска;
  clone-watcher `_dd_progress_watcher` — устройство цели из cmdline `dd of=`
  (regex `of=/dev/(mmcblk\d+|sd[a-z])`) с fallback на `emmc_device()`;
  `lsblk SIZE /dev/sda` и `smartctl -a /dev/sda` → `hdd_device()` (нет диска →
  «диск не обнаружен», кэш size ставит «?» вместо вечного None); `api_health`
  += блок `platform`.
- `modules/monitor.py`: temp в `get_system_overview` → `thermal_temp() or 0`.

**Деплой:** бэкапы `*.backup-pre-p3-20260930-*` (system_routes, monitor;
app.py не менялся), py_compile 4 файлов OK, restart → active; тест
`/tmp/test_p31_platform.py` — **22/22 PASS**: unit (zone0/48.3°C, eMMC
`mmcblk2`, SD `mmcblk1`, hdd None, board «X96 Max», arch aarch64, кэш
detect), API (health.platform + регрессии P1-9/P1-11, status temperature,
system/health warnings, /api/disks smart → «диск не обнаружен», monitor
overview), live-сервис; журнал без Traceback, `SCAN OK: 6–8 devices`,
`MISSING DEPS: tracepath, host`.

**Остаточные риски:** thermal — только первая доступная зона (без агрегации
нескольких); clone-watcher при отсутствии `of=` в cmdline и без emmc молча
прекращается (прогресс недоступен, сама клонировка не затронута); платформенные
интерфейсы (`end0→eth0`, `wlan1→wlan0`) по-прежнему перебором в
`devices_routes.run_scan` (капабилити-уровень, не board-абстракция).

### 30.09.2026 — P6: Discovery engine — core/discovery.py + manual scan (PHASE 6) — **DONE**

**Задачи 17–20 (PHASE 6).** Движок сканирования вынесен из UI-роутов
в отдельный модуль:

- **`core/discovery.py` (новый):** `run_scan(subnet, ifaces)` — scanner:
  единый цикл по `network.scan_ifaces` (дефолт `end0/eth0/wlan1/wlan0`,
  вместо двух хардкод-списков wired/wifi), возвращает **raw-вывод nmap**
  (убран двойной парсинг: раньше run_scan парсил, синтезировал текст, а
  `parse_scan` парсил его обратно); None при отсутствии nmap (P1-11) или
  пустой сети; self_ips дописываются в том же формате. `parse_scan` —
  normalizer; `reconcile(con, current, now)` — вся DB-логика (upsert,
  NEW/ONLINE/OFFLINE/misses) с новым событием **MAC_CHANGED**; `scan_loop`,
  `_scan_status`/`get_scan_status`, `start_scan_thread` (guard P1-8).
- **`modules/devices_routes.py`:** только схема БД (`init_db_schema`/`get_db`)
  + роуты + реэкспорт движка — импорты `app.py` (`start_scan_thread`,
  `init_db_schema`) и `system_routes.get_scan_status` не изменились.
- **`POST /api/scan` (новый, admin-only):** one-shot ручной скан с
  опциональными `{subnet, ifaces}` (не пишет settings), возвращает
  `{ok, devices, stats, subnet}`; аноним → 403, мусорные ifaces → 400.
- **UI:** кнопка «🔍 Сканировать» в шапке `devices.html` (только admin);
  CSRF ставит глобальный fetch-wrapper `base.html`.
- **`docs/Конфигурация.md`:** строка `network.scan_ifaces`, ссылки на
  `core.discovery.*` вместо `devices_routes.*`.

**Деплой:** бэкапы `*.backup-pre-p6-*` (devices_routes, devices.html),
py_compile OK, restart → active; тест `/tmp/test_p61_discovery.py` —
**30/30 PASS**: unit (parse_scan 3 хоста/hostname/MAC-регистр; reconcile на
tmp-БД: NEW → без событий → MAC_CHANGED+сброс name → 6 пропусков → OFFLINE →
ONLINE; живой run_scan 22 хоста + self_ips), API (аноним 403, ifaces 400,
manual scan 22 devices + stats, кнопка в `/`, `/history`, health
`last_discovery.scan/thread_alive`, platform-регрессия P3), live-сервис
(`SCAN OK: 18–22 devices`, журнал без Traceback).

**Остаточные риски:** ручной скан не сериализован с фоновым (параллельный
nmap возможен — терпимо, busy_timeout защищает БД); выбор интерфейса/подсети
через API и settings, а не через UI-форму; хардкод интерфейсов `end0→eth0`
перебором закрыт (оставался после P3) — теперь единый `scan_ifaces`.

### 30.09.2026 — P7: Event engine — события v2, фабрика, API (PHASE 7) — **DONE**

**Задачи 21–24 (PHASE 7).** Система событий получила формализованный вид:

- **Схема events v2** (`modules/devices_routes.py`, `SCHEMA_VERSION = 2`):
  новые колонки `severity` (info/warning/critical), `source`
  (discovery/system/monitoring/user), `metadata` (JSON-текст); миграция —
  тем же паттерном PRAGMA table_info + ALTER, что и у `devices`;
  backfill старых строк по типу события (NEW/ONLINE → info, OFFLINE/
  MAC_CHANGED → warning, всё NULL → info/discovery); индекс
  `idx_events_event(event, id)`. Бэкап БД **до** миграции
  (`devices.db.backup-pre-p7-*`, integrity ok) — боевые 37 119 событий
  сохранены, `user_version=2`.
- **`core/events.py` (новый):** `EVENT_SEVERITY` (карта тип→severity),
  `add_event(con, ip, hostname, mac, event, source, metadata, severity)` —
  единственная точка INSERT (неизвестный тип → info, metadata → JSON),
  `list_events` (фильтры event/severity/ip/source, новые первыми),
  `event_to_dict` (metadata парсится обратно в dict).
- **`core/discovery.py`:** все 4 INSERT-а (NEW/ONLINE/OFFLINE/MAC_CHANGED)
  заменены на `add_event(..., timestamp=now)` — события автоматически
  получают severity и source=discovery.
- **`GET /api/events`** (login, в `devices_routes`): `?limit=&event=`
  `&severity=&ip=&source=`, JSON-лента с распарсенным metadata; аноним → 302.
- **UI:** колонка «Уровень» с цветовым бейджем (critical — красный,
  warning — оранжевый, info — серый) в `/history`.

**Деплой:** бэкапы файлов `*.backup-pre-p7-*` + бэкап БД до миграции
(в `p7_run.sh`: sqlite3 `.backup` через python, integrity ok), py_compile
OK, restart → active; тест `/tmp/test_p71_events.py` — **30/30 PASS**:
unit (карта severity, add_event override/metadata JSON, list_events-фильтры,
reconcile NEW → info/discovery и MAC_CHANGED → warning), миграция боевой БД
(колонки, backfill без NULL, 37 119 событий, оба индекса), API (аноним 302,
limit/fallback, фильтры severity=warning и event=NEW, `/history` с «Уровень»,
страница устройства), регрессии P6 (кнопка скана) и P3 (platform), live
health `user_version=2` (первый прогон упал на Part D — сервис биндил порт
на 4-й секунде после рестарта; в чек добавлен retry — прошёл).

**Остаточные риски:** события пишет только discovery (system/monitoring
пока молчат — подключаются одной строкой `add_event`); `metadata` не
индексируется (поиск по нему — полный проход); IP_CHANGED/disk_warning не
реализованы (отложены до нужды — карта и фабрика к ним готовы); уведомления
(notify) — отдельная фаза.

### 30.09.2026 — P5: Database — миграции, ensure-таблицы, retention (PHASE 5) — **DONE**

**Задачи 25–28 (PHASE 5).** Схема БД получила формальную миграционную
систему и полноту на чистой установке:

- **Нумерованные миграции** (`modules/devices_routes.py`): карта
  `MIGRATIONS = ((1, _migration_v1), (2, _migration_v2))` — шаги применяются
  строго по `PRAGMA user_version` (не по table_info-эвристике), каждый шаг —
  своя функция с логом `DB MIGRATION: applied vN`. Шаг v1 — базовая схема
  devices/events (старый DDL) + индекс `events(ip,id)`; шаг v2 — колонки
  devices (hostname/is_new/misses/name/device_type), события v2
  (severity/source/metadata), backfill и `idx_events_event(event,id)`.
  На чистой БД путь 0→1→2 исполняется пошагово (подтверждено тестом);
  на боевой (уже v2) шаги пропускаются. Старый монолитный блок
  (CREATE + «if колонка отсутствует») заменён шагами.
- **Ensure 8 таблиц (P5-26):** `_ensure_extra_tables()` — точный DDL из
  боевой БД для таблиц, чьи CREATE жили только на серверах: `env_data`,
  `mchs_alerts`, `weather_alerts`, `weather_daily`, `weather_forecast`,
  `weather_forecast_history`, `weather_hourly`, `weather_observations` +
  уникальный индекс `idx_weather_observations_timestamp_unique`.
  Их читает `weather_routes`/`app.py`, пишет `deploy/weather-update.py` —
  до P5 восстановление на чистой машине давало неполную схему
  (закрыт §2-gap «8 таблиц weather не имеют CREATE в репо»).
- **Retention (P5-27):** настройка `events.retention_days` (default 180,
  `0` = выкл) → `core/events.cleanup_old_events(con, days)` — парсинг
  `DD.MM.YYYY HH:MM:SS` в Python (строковое сравнение дат тут невозможно),
  DELETE батчами по 500 id, коммит внутри. Чистка выполняется при старте
  сервиса (в `init_db_schema`, ошибки не валят init) и ежедневно фоновым
  daemon-потоком `retention_loop` (запуск в `app.py __main__` рядом с
  остальными потоками).
- **`docs/Конфигурация.md`:** секция `events` с ключом `retention_days`.

**Деплой:** бэкапы файлов `*.backup-pre-p5-*` (app.py по регламенту) +
**бэкап БД до рестарта** (`devices.db.backup-pre-p5-*`, integrity ok);
py_compile OK, restart → active; тест `/tmp/test_p51_migrations.py` —
**24/24 PASS**: пошаговость (v1 без severity/v2 с ними, шаг не ставит
версию сам), полный init на чистой БД (`DB MIGRATION: applied v1/v2`,
user_version=2, ядро + 8 ensure-таблиц + 3 индекса), retention unit
(2 старых удалено / свежее цело / days=0 → выкл), боевая БД (все таблицы,
integrity ok, 37 129 событий и 40 устройств целы), API (health
`db.user_version=2`, `/`, `/history`, `/api/events`), live health.

**Остаточные риски:** идентичность устройства = IP (MAC+IP+hostname —
отложено, отдельный крупный рефакторинг); retention чистит только `events`
(другие растущие таблицы: `weather_forecast_history` 16 693 строк,
`currency_history` — под вопросом, нужны ли); DDL остальных таблиц
(currency/inventory/recycling) создаётся ленивыми init их модулей, а не
единой точкой — при чистом старте порядок зависит от вызова
`init_inventory_db`/first-use; временные метки событий строковые —
retention парсит их в Python.

### 30.09.2026 — P13: Testing — pytest-структура + CI (PHASE 13) — **DONE**

**Задачи 29–31 (PHASE 13).** Ad-hoc проверки предыдущих фаз
(`/tmp/test_p*`, живая панель, admin/1234) превращены в репозиторный
pytest-набор + CI:

- **Структура (P13-29):** `tests/conftest.py` — фикстуры `events_con`
  (tmp-схема events v2), `devices_db` (полный init на tmp-БД с
  monkeypatch `DB`/`_init_done`), `no_dns` (заглушка DNS в reconcile).
  `tests/unit` — без сети и панели; `tests/live` — маркер `live`
  (фикстуры `panel_url` скипают прогон при недоступности, `admin_session`
  — CSRF-логин сессией). `pytest.ini`: по умолчанию `-m "not live"`
  (unit-прогон детерминирован; live — явно `pytest -m live` или
  `LAN_PANEL_URL=... pytest -m live`). `requirements-dev.txt`:
  `pytest>=8,<10` (проверено на 8.4.2 локально и 9.1.1 на X96).
- **42 unit-теста (P13-30):**
  - `test_discovery.py` (15): `parse_scan` (hostname/IP/MAC/vendor, пусто,
    без MAC-блока), `run_scan` — subprocess замокан (self_ips дописываются,
    не дублируются, FileNotFoundError → None, все ifaces упали → None,
    пустой вывод → только self_ips); `reconcile` — NEW → повтор (без
    ONLINE-дубля, appearances+1) → пропуски (misses растут, OFFLINE на
    пороге `max_misses`, severity=warning) → возврат ONLINE-события;
    MAC_CHANGED (обнуление name, событие warning) и case-insensitive
    сравнение MAC; форма `get_scan_status`; guard `start_scan_thread`
    (повторный вызов → тот же поток).
  - `test_events.py` (10): severity-карта и override, персистентность
    колонок, фильтры `list_events`, порядок (новые первыми), JSON
    metadata (включая кириллицу и битый JSON без падения), retention unit
    (старое удалено/свежее цело/0=выкл/мусорная дата не роняет).
  - `test_hardware.py` (6): переносимые проверки Win/CI/X96 — path/None,
    типы, кэш `detect_platform`, форма словаря.
  - `test_migrations.py` (6): шаги v1/v2 изолированно, идемпотентность
    повторных вызовов (с commit — бэкфилл+индекс в одной транзакции),
    полный init на чистой БД (user_version=2, ядро + 8 ensure-таблиц +
    индексы), повторный init → False, `_retention_days` через
    monkeypatch `load_settings` (180/0/30).
  - `test_config.py` (5): `_cfg` default/секция/missing-key,
    `_scan_interval` (0 → default 30), `_max_misses` (default 6).
- **5 live-тестов:** форма `/api/health` (db.version=2, platform,
    capabilities, last_discovery), анонимный `/api/events` → 302, логин +
  авторизованный `/api/events`, страницы `/`/`/history`/`/currencies`/
  `/apps`, `/api/currencies`.
- **CI (P13-31):** `.github/workflows/ci.yml` — push/PR в main →
  ubuntu + Python 3.11 + pip cache → `pip install -r requirements.txt -r
  requirements-dev.txt` → `pytest tests/unit -v` + py_compile
  app/core/modules; timeout 15 мин.

**Проверки:** локально (Windows, py3.12, pytest 8.4.2) — 42 unit PASS,
5 live PASS (панель 192.168.3.243:8080 отвечает); на X96
(`/opt/lan-discovery/tests`, venv, pytest 9.1.1) — 42 unit PASS,
5 live PASS. Нюансы: ручной вызов `_migration_v2` без `commit` теряет
бэкфилл/индекс (в `init_db_schema` commit есть — тесты учли); MAC в
reconcile обновляется как есть (регистр ≠ смена).

**Остаточные риски:** live-тесты гоняются только при достижимой панели
(по умолчанию выключены); ад-hoc deploy-скрипты фаз (`/tmp/test_p*`) не в
git; негативные проверки (403/валидация форм) покрыты частично.
