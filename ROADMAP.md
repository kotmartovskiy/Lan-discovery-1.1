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
| **Configuration** | hardcoded: `NETWORK=192.168.3.0/24`, интерфейсы `end0/wlan0/wlan1/eth0`, IP хостов в `monitoring_routes.py:22`, `inventory_routes.py:28`, fallback `.234/.235`, порт 8080, пути `/opt|/etc|/srv` — разбросаны по 15+ файлам | единый конфиг: defaults + `/etc/lan-discovery/settings.json` overrides | переносимость на другую сеть/платформу требует правки кода | **P2** |
| **Hardware abstraction** | platform-specific жёстко вшит: `end0` vs `eth0` перебором (`system_routes.py:1436`), thermal `thermal_zone0`, `/dev/mmcblk2`, `dd if=/dev/mmcblk…` | `detect_platform()` + capabilities + адаптеры | новый SoC/дистрибутив = правки в многих файлах | **P2** |
| **Переносимость (X96)** | новый код **уже работает** на aarch64/Debian 12; старый — на armv7l/Debian 13 | один код на обеих | две версии в проде (§9) | **P2** |
| **Database** | WAL + busy_timeout есть в ключевых точках; **нет** версионирования схемы (`user_version=0`), **нет** индекса `events(ip)`, **нет** retention (events = 36 327 строк), идентичность = **IP** (не MAC); 8 таблиц weather не имеют CREATE в репо (схема живёт только на серверах) | `user_version` + миграции, индексы, retention, идентичность MAC+IP+hostname | рост БД бесконечен; восстановление на чистой машине может создать неполную схему | **P1** |
| **Discovery engine** | скан плотно связан с UI-роутами (`devices_routes.py`), сеть захардкожена, ручного выбора подсети/интерфейса нет, MAC-смена **не пишется в events** (`devices_routes.py:354-386`) | scanner → normalizer → DB → events → API, manual/scheduled scan по выбору | нет гибкости сканирования, слабая трассируемость изменений | **P2** |
| **Event system** | только 3 типа (`NEW/ONLINE/OFFLINE`) в таблице `events`; нет severity/source/metadata | формализованные события (device_missing, ip_changed, disk_warning…) | нет фундамента для уведомлений | **P3** |
| **Observability** | `/api/health` есть (unauth, `system_routes.py:1636`), `/api/status`, `/api/system/health` — но **нет version/uptime/last-discovery в одном месте** | `/api/health` + `/api/version` + `/api/discovery/status` | состояние видно только через UI | **P1** |
| **Installer** | нет: установка вручную по `docs/Установка.md` (venv + systemd вручную) | `install.sh`: dep-check → config → systemd → db init → health | воспроизводимость установки на новое устройство | **P3** |
| **Update/rollback** | деплой вручную (`deploy.py`: бэкап → SFTP → py_compile → restart); бэкап БД автоматический + integrity_check + restore из UI — **это уже работает** | версия → backup → update → health → rollback | нет версий/отката кода (только бэкап файлов) | **P3** |
| **Backup/recovery** | БД: Online Backup API + integrity_check + ротация 14 дней + restore через UI (`system_routes.py:1936`); на OP эММС-бэкапы; **restore на чистую систему не проверен** | документированная и проверенная процедура restore | «production ready только после проверенного restore» | **P2** |
| **Testing** | 3 ad-hoc скрипта `test_*.py` (захардкожены admin/1234, требуют живой панели); pytest/CI нет | unit-тесты (parsers/config/db/events/platform) + интеграционные | регрессии ловятся только вручную | **P2** |
| **Documentation** | `docs/` (9 страниц, wiki), `README.md`, `AGENTS.md`; `docs/Архитектура.md:81` **устарел** (11 таблиц vs 16 фактических), нет ARCHITECTURE/SECURITY/CONFIGURATION/API | комплект 1.0 (см. PHASE 14) | документация отстаёт от кода | **P3** |
| **Repo hygiene** | в корне 60+ одноразовых скриптов (`check_*`, `debug*`, `verify*` — большая часть в `.gitignore`, часть трекается: `patch_app.py`, `ssh_query.py`…); трекаются `modules/*_b64.txt`; `.gitattributes` нет (EOL-шум: 13/19 расхождений — только перевод строки) | мусор вне корня/git, `.gitattributes` | грязь в репозитории, шум при сверке с сервером | **P4** |

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
| B1 | Веб-терминал без авторизации, root-PTY, CORS `*` | `core_routes.py:906-956`, `app.py:336` | RCE от root для любого, кто достучится до :8080 |
| B2 | Filemanager: корень `/`, guest может удалять/перемещать файлы | `core_routes.py:655-761` | потеря данных от root |
| B3 | `POST /api/network/check_host` без авторизации (host → внешняя команда) | `network_routes.py:82-93` | неаутентифицированный SSRF/DoS-прокси |
| B4 | Сейф паролей: base64, HMAC игнорируется, guest читает | `core_routes.py:793-816` | пароли открыты |
| B5 | Отключённый пользователь не выкидывается из сессии; SHA-256-фолбэк пароля | `auth.py:35-42,85-93` | обход блокировки учётки |
| B6 | CSRF-meta отсутствует в `base_app.html` **в репозитории** (на X96 уже исправлено, не закоммичено) | `templates/base_app.html` | регресс CSRF при следующем деплое |

Не P0, но рядом: dev-Werkzeug на `0.0.0.0`, нет security-заголовков, root-сервис.

---

## 5. Синхронизация «репозиторий ↔ серверы» (факт)

- `app.py`: **репозиторий == X96** (md5 совпадает). OP — старая версия.
- Расхождения репозиторий ↔ X96 (19 файлов):
  - **X96 впереди (не закоммичено):** `templates/base_app.html` (+24 строки — CSRF-fix),
    `modules/recycling.py` (3 попытки запроса), `templates/login.html` (favicon).
  - **Репозиторий впереди (не задеплоено):** `modules/monitor.py` (ThreadPoolExecutor,
    cpu-cache, timeout=3 вместо 5), `templates/apps/terminal.html` (на X96 — **мозги
    повреждены кодировкой**: «вљ пёЏ РўРµСЂРјРёРЅР°Р»…»).
  - 13 файлов — **только перевод строки** (CRLF↔LF) → нужен `.gitattributes`.
- Мусор на X96: 7 файлов `templates/apps\*.html` (буквальный backslash в имени,
  артефакт загрузки с Windows, 21.09) — не используются, удалить.
- `deploy/`, `docs/` — только в репозитории (units ставятся в `/etc/systemd` напрямую).
- Репозиторий чистый (`git status` = 0), последний коммит 30.09.2026 02:35.

**Риски:** пуш «как есть» сломает CSRF во вкладках (B6) и терминал-строку; деплой
«как есть» затрёт monitor.py/terminal.html.

---

## 6. Первые задачи (P0/P1), к выполнению

1. **[P0][DONE — 30.09.2026]** Закрыть терминал: авторизация SocketIO-подключений
   (session/user + admin), ограничить `cors_allowed_origins` → см. журнал §9.
2. **[P0] Filemanager:** admin-only (или отдельное право) + базовое ограничение корня
   (`FILEMANAGER_ROOT`, реально используется только как объявление).
3. **[P0] Закрыть неавторизованные роуты** `/api/network/check*`; валидация `host`
   (IP/hostname, без `-`-префикса) во всех nettools.
4. **[P0] Сейф:** честное шифрование (Fernet на отдельном ключе) + миграция существующих
   записей + доступ не ниже `can_edit`.
5. **[P0] Auth:** проверка `enabled` в `login_required`/`get_current_user`, отказ от
   SHA-256-фолбэка (массовый re-hash при первом входе), min. длина пароля, TTL сессии.
6. **[P0] Синхронизация:** закоммитить X96-правки (CSRF base_app, recycling, favicon),
   починить `terminal.html` на X96, добавить `.gitattributes`, удалить `apps\*.html`.
7. **[P1] Схема БД:** перенести DDL из `get_db()` в однократную инициализацию
   (startup), `PRAGMA user_version`, индекс `events(ip, id)`, `finally`-закрытие коннектов.
8. **[P1] Фоновые задачи:** guard от повторного запуска сканов (inventory/bluetooth),
   удалить мёртвый `init_background_tasks` и дубли функций.
9. **[P1] Observability:** `/api/health` → добавить version/uptime/last-discovery/
   db-status в один ответ.
10. **[P1] Безопасность окружения:** security-заголовки, cookie-флаги, вычистить
    root/1234 и IP из отслеживаемых файлов (включить `templates/help.html` в sanitize).

---

## 7. Статусы фаз roadmap

| Фаза | Статус | Комментарий |
|---|---|---|
| PHASE 0 Audit | **DONE** | этот документ; код не менялся |
| PHASE 1 Stabilization | **IN PROGRESS** | задачи 7–9 + обработка отсутствующих подсистем |
| PHASE 2 Configuration | **PENDING** | см. §2 «Configuration» (P2) |
| PHASE 3 Hardware abstraction | **PENDING** | platform detection/ capabilities |
| PHASE 4 X96 Max port | **IN PROGRESS (частично)** | новый код уже работает на aarch64; блокер — расхождение двух версий (§5) |
| PHASE 5 Database | **PENDING** | задача 7 — первые шаги |
| PHASE 6 Discovery engine | **PENDING** | |
| PHASE 7 Event engine | **PENDING** | |
| PHASE 8 Security hardening | **IN PROGRESS** | задачи 1–6 (P0) |
| PHASE 9 Installer | **PENDING** | |
| PHASE 10 Update/rollback | **PENDING** | |
| PHASE 11 Backup/Recovery | **PARTIAL** | бэкап БД готов; restore на чистую систему не проверен → не DONE |
| PHASE 12 Observability | **PARTIAL** | `/api/health` есть, version/discovery-status нет |
| PHASE 13 Testing | **PENDING** | pytest/CI нет |
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
