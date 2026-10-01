# UI_UX_AUDIT — LAN Discovery (вход в версию 1.1)

Дата: 01.10.2026 · Основание: промпт «UI/UX Redesign + Capabilities/Modules/Roles»
(п.3: «до серьёзного изменения кода создай UI_UX_AUDIT.md»).
Метод: **только реальный код** (не README): 28 шаблонов (10 383 строк),
165 роутов, 33 модуля, `core/`, `modules/`. Коммит-основа: `2e9e297`.

---

## 1. Как устроен фронтенд сейчас (архитектура)

- **Jinja + vanilla JS, без сборки, без фреймворка.** Никакого npm/webpack;
  только внешние CDN: xterm + socket.io (`apps/terminal.html:5-7`).
- **`templates/base.html` — монолит 2 124 строки**: инлайн-CSS 467 строк
  (`base.html:34-501`), инлайн-JS ~1 572 строки, шапка с плоскими табами
  (`base.html:527-538`), нижний статус-бар, глобальные поллеры. Наследуется
  **14 страницами**.
- **`templates/base_app.html` (180 стр.)** — второй лейаут для 11 приложений
  `/apps/*`: своя тёмная тема GitHub-dark, **без шапки/навигации/статус-бара**.
- **`templates/login.html`** — третий standalone-лейаут (тема `#1a1a2e`).
- **`static/style.css` (442 стр.) НЕ подключён ни одним шаблоном** — мёртвый
  файл; его копия проинлайнена в `base.html`. Итого **4 параллельных
  «дизайн-системы»** + 20 самописных страниц.
- **Блочная система модулей**: `blocks_for(slot)` (`app.py:319`,
  `module_loader.block_items()`) — слоты `system` (9 блоков) и `currencies`
  (5 блоков) = 14 `modules/*/block.html`.
- **Навигация**: `nav_items()` (`module_loader.py:142`) = 5 core-пунктов +
  вкладки модулей из `module.json → tab` (фильтр installed+enabled, сортировка
  по order); единственный условный пункт — «Модули» для admin
  (`base.html:533`). Выключенные модули → 404 по префиксам
  (`module_manager.py:103-113`).
- **Транспорт**: только `fetch` + `setInterval` + HTML-формы + один
  socket.io (терминал). Нет jQuery/XHR/EventSource/WebSocket.
- **Роли UI**: `USER_ROLE` (`base.html:561`), декораторы backend
  (`@login_required`, `@admin_required`, `@can_edit`); гостевые ограничения
  разбросаны по страницам/блокам.

## 2. Навигация (текущее дерево)

```
header (sticky): h1 LAN Discovery {panel_name}
└── .tabs — плоский список, порядок по order:
     1  Устройства      /            (core)
     2  Инвентаризация  /inventory   (модуль inventory)
     3  Мониторинг      /monitoring  (модуль)
     4  Торрент         /torrent     (модуль)
     5  Валюты          /currencies  (модуль)
     6  Погода          /weather     (модуль)
     7  Приложения      /apps        (core)
     8  Система         /system      (core)
     9  О системе       /about       (core)
    10  Справка         /help        (core)
    11  Модули          /modules     (только admin)
└── .clock: дата/время (1 с) · погода (60 с) · ● Интернет · health (60 с)
system-status-bar (fixed bottom): CPU/RAM/eMMC/HDD/↓/↑ · restore:8081 · юзер/выход
```

Проблемы навигации: нет группировки (целевая модель §8 — HOME/NETWORK/
MONITORING/ROLES/SYSTEM/APPS/ADMIN), `/history` **не имеет ссылок нигде**
(сирота), «Модули» выпадает из порядка (вне order), гостевая видимость не
централизована, активная вкладка — по префиксу URL.

## 3. Каталог страниц

| Роут | Шаблон | Тип | Назначение | Особенности |
|---|---|---|---|---|
| `GET /` | `devices.html` | страница | Таблица скана LAN | свой JS (scan); guest-скрытие колонок; нет h1 |
| `GET /device/<ip>` | `device.html` | страница | Деталь устройства + переименование + история | форма POST; серверный рендер |
| `GET /history` | `history.html` | страница | Последние 500 событий (3 уровня: critical/warning/info) | **сирота — нет ссылок**; серверный рендер |
| `GET /inventory` | `inventory.html` | страница | Инвентаризация (accordion) | свой style+script |
| `GET /inventory/device/<ip>` | `inventory_device.html` | **заглушка 5 стр.** | «Информация загружается…» | **мёртвая: JS нет, ссылок нет** |
| `GET /monitoring` | `monitoring.html` | страница | Мониторинг устройств (Netdata) | 29 инлайн-стилей; пороги hex-инлайном |
| `GET /torrent` | `torrent.html` | страница | iframe Transmission :9091 | guest → «доступ запрещён» |
| `GET /currencies` | `currencies.html` | страница+блоки | Курсы (5 модульных блоков) | серверный рендер |
| `GET /weather` | `weather.html` | страница | Погода/предупреждения/UV/радиация | 33 inline; серверный рендер |
| `GET /apps` | `apps.html` | **хаб-монолит 1 812 стр.** | «Рабочий стол»: 23 плитки, 23 `.app-overlay` | 8 inline-приложений + 4 игры iframe + 11 iframe `/apps/*`; `<style>` 4-250, `<script>` 665-1811 |
| `GET /apps/{notes,passwords,filemanager,terminal,downloads,dlna,upnp,nettools,wifianalyzer,bluetooth,disks}` | `apps/*.html` (11) | отдельные страницы (`base_app`) | Приложения | **без шапки/навигации** при прямом заходе; свои style+script; терминал — socket.io |
| `GET /system` | `system.html` | **блочная контейнерная** (15 стр.) | Система | 9 блоков `sys-*` |
| `GET /about` | `about.html` | страница | О системе | серверный рендер, 12 inline-стилей |
| `GET /help` | `help.html` | страница | Справка (ядро 1-11 + 33 секции модулей) | липкий TOC; ручная копия API-каталога (уже разошлась с docs/API.md) |
| `GET /modules` | `modules.html` | страница | Установка/тумблеры/каталог (admin) | формы POST, inline onclick |
| `GET /login` | `login.html` | standalone | Вход | своя тема |
| `GET /games/<file>` | статика `games/*.html` | iframe-цели | 4 игры | send_file, без Jinja |
| `GET /503` | inline в `app.py:301-308` | заглушка | 503 | без шаблонизатора |

Слоты блоков: `system` — sys-board 10, sys-emmc 20, sys-db 30, sys-network 40,
sys-clone 50, sys-iptv 60, sys-power 70, sys-settings 80, sys-users 90;
`currencies` — curr-fiat 10 … curr-recycling 50.

## 4. API по страницам (сводно)

| Страница/слой | Endpoint'ы | Транспорт |
|---|---|---|
| `base.html` (все 14 страниц) | `GET /api/status` **×2**, `GET /api/weather-status` (60 с), `GET /api/system/health` (60 с), `GET/POST /api/samba/guest`, `POST /api/service/<svc>/<act>`, disk/clone/backup/network-check/restore операции | **4 фоновых poll** |
| `/` devices | `POST /api/scan`, `POST /api/device/<ip>/dismiss-new` | fetch |
| `/device/<ip>` | `POST /device/<ip>/name` | форма |
| `/inventory` | `POST /inventory/scan` | форма |
| `/history`, `/monitoring`, `/weather`, `/currencies`, `/about`, `/help` | **нет своих вызовов** (серверный рендер) | — |
| `/modules` | forms: `POST /modules/catalog/{refresh}`, `/modules/<id>/{install,toggle,catalog/update,catalog/remove,catalog/install}` | формы |
| `/apps` (хаб) | будильник `GET/POST /api/alarms*`, радио `/api/radio/*`, плеер `/api/player/*`, камеры `/api/cameras*` + 11 iframe | fetch |
| `apps/bluetooth` | `/api/bluetooth/*` (status/devices/power/scan/connect/…) | fetch + **poll 15 с**, во время скана **ещё poll 2 с (не глушится)** |
| `apps/downloads` | `/api/transmission/{torrents,action,queue,add}` | fetch + poll 5 с |
| `apps/upnp` | `/api/upnp/*` | fetch + poll 5 с (после выбора) |
| `apps/dlna`, `apps/wifianalyzer` | `/api/dlna/*`, `/api/wifi/scan` | fetch + opt-in poll 30 с |
| `apps/filemanager` | `/api/filemanager/{list,read,rename,delete,copy,move,mkdir}` | fetch |
| `apps/nettools` | `POST /api/nettools/{ping,dns,ports,trace}` | fetch |
| `apps/notes`, `apps/passwords` | `/api/notes*`, `/api/secrets*` CRUD | fetch |
| `apps/terminal` | socket.io `terminal_start/input/resize/output/error` | socketio |
| блоки `sys-*` | service control, samba guest, backup/restore, clone, network-check/config, settings, users, iptv, reboot/poweroff | fetch/формы |

**Polling-карта (проблемы):**

- 🔴 `GET /api/status` **каждые 3 с ДВАЖДЫ**: `updateSystemStatus`
  (`base.html:1790`) + `updateOrangePiStatus` (`base.html:2103`) — вторая на 13
  страницах из 14 работает впустую (`#pi-*` есть только на /system).
- 🔴 `apps.html` статически грузит **11 iframe** → поллеры downloads (5 с) и
  bluetooth (15 с) крутятся при закрытых модалках; bluetooth держит **два
  таймера одновременно** (2 с + 15 с).
- Итог на `/apps`: **~60–70 запросов/мин**, большая часть — фоновые.
- 🟡 3 разных поллера `/api/backup-status` (3 с/1,5 с/1 с), дубли
  `/api/clone/status`, `/api/network/check_host`.

**Неиспользуемые UI API (14 из ~140):** `GET /api/events`, `GET /api/currencies`,
`GET /api/health`, `GET /api/disk/info`, `GET /api/network/config`,
`GET /api/monitoring/<ip>`, `GET /api/inventory/<ip>`,
`POST /system/backup`, `POST /system/backup-test`, `POST /system/emmc-restore`
(**мёртвый JS — кнопок нет**, help обещает «Резервное копирование»),
`POST /system/iptv` (сохранить все), `DELETE /api/player/playlist/<fn>`,
`POST /api/cameras/<id>/{start,stop}`.

## 5. Компоненты и design system (что есть)

- Токенов/переменных: **0** (`:root` отсутствует; `var(--…)` 2 раза с
  fallback, определяется JS `base.html:1289`). 35 hex в style.css, **60
  уникальных background-hex в инлайне**, 487 объявлений `color:#…`, 232
  `style="`-атрибута.
- Есть: `.card`, `.info-row`, `.service-row`, `.badge`, `.mono`,
  `.status-ok/-error/-running/-warn/-critical` (в `style.css`/`base.html`,
  дубли), `table`-стили, `.tabs`, `.system-status-bar`.
- **Нет**: `.btn`-универсала (173 `<button>`, ~17 разных компонентных классов
  кнопок, 2 несовместимых определения `.btn`), `.modal`/`.toast`-единого
  (3 кастомные модалки + 3 тоста, `<dialog>` = 0), `.empty-state`
  (5 разных определений), `.loading/.spinner/.skeleton`, графиков
  (**0 canvas, 0 chart-библиотек** — только CSS-бары в wifianalyzer),
  focus-стилей (`:focus-visible` = 0; 8× `outline:none`).
- Диалоги: **27 нативных `alert/confirm/prompt`** (в т.ч. подтверждение
  выключения питания); у `base.html` собственных тостов нет вообще.
- Semantic states: названы ok/error/running/warn/critical; **unknown/нет
  данных как класса нет** — выражается `"--"`. Цвет нигде не единственный
  носитель (везде `●` + текст — сделано правильно), но пороги рисуются
  инлайн-hex-ами (monitoring ×10, modules, inventory, history).

## 6. Состояния (loading / empty / error / demo)

- **Loading**: нет единого паттерна (только `.loading` в disks, спиннер в
  base_app); чаще — текст «--»/«Загрузка…» локально.
- **Empty**: 5 разных `.empty-state`, есть словесные «Нет раздач/событий».
- **Error**: `status-error` + `alert()`; тихие `catch(()=>{})` — 8 штук.
- **Demo/недоступно**: **33 места со значением `"--"` без какого-либо
  объяснения** (base ×15, weather ×14, wifianalyzer ×4) + 3 конкурирующих
  обозначения пустоты: `--`, `—`, слово («нет данных», «недоступно»).
  Флага demo/unavailable нет → §19 промпта нарушается уже сейчас.

## 7. Проблемы (P-номера)

| # | Проблема | Где | Влияние |
|---|---|---|---|
| P-1 | Нет design system: 4 параллельных темы, 0 токенов, мёртвый `static/style.css`, 2 193 стр. инлайн-CSS | 20 шаблонов | любая правка — в 4 местах |
| P-2 | Монолит `base.html` 2 124 стр. (467 CSS + 1 572 JS) грузится на всех страницах; **два `<body>`** (`:504`, `:506`), дважды `button{}` (`:386`, `:444`) | base.html | хрупкость, вес |
| P-3 | Двойной poll `/api/status` 3 с; на 13/14 страниц — впустую | base.html:1790/2103 | ~40 req/мин впустую |
| P-4 | `/apps`: 11 iframe статически, поллеры закрытых модалок, 2 таймера bluetooth; **нет deep-link/back/refresh** (оверлеи) | apps.html | ~60–70 req/мин; UX-тупик |
| P-5 | `base_app`-страницы при прямом заходе — **без шапки/навигации/выхода** (тупиковые экраны) | base_app.html | потеря контекста |
| P-6 | **Нет `<meta viewport>` в base.html** → 14 основных страниц не адаптивны (медиазапросы не работают); `base_app`/`login` — есть | base.html:1-30 | mobile сломан |
| P-7 | Доступность ~0: `aria/role/tabindex/alt` = 0/0/0/0, `<label for>` 2/48, `<main>/<header>/<nav>` = 0/0/1, `:focus-visible` 0, `outline:none` ×8 | везде | клавиатура/скринридер |
| P-8 | 27 нативных alert/confirm/prompt; 3 модалки + 3 тоста; нет Esc/фокус-трапа/`<dialog>` | везде | UX-консистентность |
| P-9 | 33 `"--"` без объяснения; 3 обозначения пустоты; нет demo/unavailable-состояния | base/weather/wifi | §19 промпта |
| P-10 | Статусы: классы живут только в base.html; пороги — инлайн-hex на страницах; нет `unknown` | monitoring×10 и др. | §5 промпта (semantic states) |
| P-11 | Плоская навигация без групп; `/history`-сирота; «Модули» вне порядка; guest-ограничения разбросаны | base.html:527 | §8 промпта |
| P-12 | Мёртвая/утраченная UX-функциональность: `inventory_device` — заглушка без JS; кнопки файлового бэкапа/теста/emmc-restore **утеряны** (JS есть, кнопок нет), help их обещает | inventory_device, base.html:921/988/1004 | регрессия |
| P-13 | Legacy: `system_full.html` (корень) — неиспользуемый снапшот; `static/style.css` не подключён; `.app-btn` определён и мёртв; help.html:220-242 — устаревшая ручная копия API-каталога | репо | грязь |
| P-14 | 18 склеек URL в JS без `encodeURIComponent` + Jinja-интерполяция в JS-строки (`devices.html:73` — IP в onclick) | base/apps/notes/… | стиль/безопасность |
| P-15 | Дублирование device-поверхностей: `/` (таблица), `/device/<ip>`, `/inventory` (+мёртвый device), `/monitoring` (accordion по устройствам) — 4 поверхности об одном | — | навигационная путаница |
| P-16 | Нет единой status-обёртки fetch (26 async-функций, 103 fetch, 62 json-цепочки, копия CSRF-обёртки в base и base_app) | везде | поддержка |

## 8. Функции, которые нельзя потерять (Keep-list)

1. Auth/CSRF/роли (admin/editor/guest), гостевые ограничения, 404 выключенных
   модулей по префиксам, admin-only роуты.
2. Скан LAN + переименование устройств + история/события (3 уровня) +
   dismiss «новых»; инвентаризация; мониторинг Netdata.
3. **Модульная система целиком**: 33 модуля, `module.json`, установка/
   тумблеры/каталог, блочная система `system`/`currencies`, `help_sections`
   (секции справки следят за тумблерами), `disabled_prefixes`.
4. Все приложения: terminal (socket.io), filemanager (admin), notes/secrets
   (Fernet), nettools, wifi, disks/SMART, downloads (Transmission), dlna,
   upnp, bluetooth, radio/player/cameras/alarms (хаб), калькулятор/таймер и
   пр., 4 игры, iframe-Torrent.
5. Система: 9 блоков (services+samba-guest toggle, eMMC, БД backup/restore,
   network check/config, clone SD↔eMMC, IPTV, power, settings, users),
   статус-бар, шапочные виджеты (часы/погода/интернет/health), restore:8081.
6. Справка `/help` (ядро + секции модулей), «О системе», страница Модули.
7. Бэкап/восстановление/клонирование (включая диск-замену), reboot/poweroff
   с confirm.

## 9. Backend limitations (мешают UI по промпту)

| Ограничение | Что нужно для промпта |
|---|---|
| Нет сущности **alerts** (health-предупреждения + events-уровни разрознены) | агрегированный «Alerts» для dashboard (§6.3) |
| Нет **capabilities** (`core/hardware.py` — 7 функций: thermal/hdd/emmc/sd/board/platform) | новый read-only `core/capabilities.py` + `GET /api/capabilities` (§9) |
| Нет слоя **roles** («role» в коде = пользователь) | конфиг-профили поверх modules + API + UI (§11) |
| `module.json` без version/source/ports/permissions/hw-требований (13 полей, deps только у 19) | расширение схемы каталога → статусы Requires hardware/Incompatible (§10) |
| Нет topology/interfaces/services-страниц; device-detail серверный | новые страницы или честный отказ в 1.1 (§8) |
| Dashboard-агрегата нет (каждый виджет сам опрашивает) | `GET /api/dashboard`-агрегат (§6) |
| Нет флага demo/unavailable | флаг источника метрик (§19) |
| 14 API недостижимы из UI (3 — утерянные кнопки) | вернуть кнопки (бэкапы!) — регрессия |

## 10. Необходимые API changes (минимальные, аддитивные)

1. **`GET /api/dashboard`** — агрегат: health + summary сети + последние
   события/alerts + статусы сервисов (закрывает двойной `/api/status`-poll и
   §6 промпта). Существующие не удалять.
2. **`GET /api/capabilities`** (+ `core/capabilities.py`) — только
   достоверное, с reliability-флагами.
3. **Расширение `module.json`** (+version, +source, +ports, +permissions,
   +hardware, +services) и вычисляемые статусы модуля
   (Available/Installed/Active/Disabled/Requires dependency/Requires
   hardware/Incompatible/Error) — старые модули без полей → «Unknown».
4. **`GET/POST /api/roles*`** — профили (списки модулей) + проверка
   hardware-требований; без изменения module loader.
5. **Вернуть недостающие кнопки** (backup/backup-test/emmc-restore) —
   backend не менять, только UI.
6. Опционально: ETag/кеш для `/api/status` (снизить стоимость poll),
   `encodeURIComponent`-хелпер на фронте.

## 11. Сводная таблица (Existing feature | Current UI | API | Keep | Redesign | Backend change)

| Existing feature | Current UI | API | Keep | Redesign | Backend change |
|---|---|---|---|---|---|
| Скан LAN / список устройств | `devices.html` — широкая таблица, инлайн-статусы | `POST /api/scan` | ✔ данные/действия | list → 6 ключевых колонок, уровни | нет |
| Детали устройства | `device.html` (форма + история) | `POST /device/<ip>/name` | ✔ всё | drawer/страница с уровнями (MAC/services/ports/history/relationships) | нет (кандидат: `GET /api/device/<ip>` JSON) |
| События/история | `history.html` — **сирота**, серверный рендер | `GET /api/events` (не используется UI) | ✔ уровни | Monitoring→Events, навигация, живой фильтр | опц.: events-пагинация |
| Инвентаризация | `inventory.html` (+ мёртвый `inventory_device`) | `POST /inventory/scan` | ✔ | объединить с device-detail, убрать заглушку | нет |
| Мониторинг | `monitoring.html` — accordion, hex-пороги | серверный Netdata, `GET /api/monitoring/<ip>` | ✔ | semantic states, единые бары, alerts-вьюха | нет |
| Погода | `weather.html` (33 inline, серверный рендер) | через base `/api/weather-status` | ✔ контент | дизайн-система, пустые состояния | нет |
| Валюты | `currencies.html` + 5 блоков | серверный рендер | ✔ | design system | нет |
| Торрент | `torrent.html` iframe | внешний :9091 | ✔ | обвязка/статусы | нет |
| Приложения-хаб | `apps.html` 1 812 стр., оверлеи, iframe | `/api/{alarms,radio,player,cameras}` | ✔ все 23 приложения | ленивая загрузка iframe, deep-link, единые модалки/тосты, design system | нет |
| Приложения `/apps/*` (11) | `base_app`-лейаут без шапки | свои API | ✔ функции | вернуть общий shell/навигацию; единый `api()` helper; polling только видимого | нет |
| Терминал | `apps/terminal.html` + xterm CDN | socket.io | ✔ | обвязка | нет |
| Система (9 блоков) | блочная система | service/samba/backup/clone/network/settings/users | ✔ всё | design system, состояния, вернуть утерянные кнопки бэкапов | нет |
| О системе | `about.html` серверный | — | ✔ | дизайн | нет |
| Справка | `help.html` (ядро+33 модуля, TOC) | — | ✔ модульность | дизайн; убрать ручной API-каталог (ссылка на docs) | нет |
| Модули (install/toggle/каталог) | `modules.html` формы | `POST /modules/*` | ✔ | карточки со статусами §10, privileged-badge, предустановочные checks | **да**: расширение module.json + статусы |
| Навигация | плоские 11 табов | `nav_items()` | ✔ механизм | доменные группы (§8), убрать сирот | микро: порядок/группы в конфиге |
| Статус-бар/шапка | base.html, 4 фоновых poll | `/api/status` ×2, weather, health | ✔ виджеты | **один** агрегат-poller, demo-состояние | **да**: `GET /api/dashboard` |
| Capabilities | **нет** | — | — | раздел «Hardware capabilities» | **да**: `core/capabilities.py` |
| Roles | **нет** | — | — | Active/Available, профили модулей, compat-check | **да**: roles-слой |
| Recovery/backup | блоки + JS (часть кнопок утеряна) | `/system/backup*`, `/api/clone*`, disk ops | ✔ | вернуть кнопки, безопасные confirm, preview «что изменится» | нет (1.3 — транзакционность) |
| Администрирование (users/settings) | блоки sys-users/sys-settings | `/api/users*`, `/api/settings` | ✔ | design system, admin-раздел | нет |
| Login | `login.html` отдельная тема | `POST /login` | ✔ | в дизайн-систему (viewport/focus) | нет |
| Игры (4) | iframe из хаба | статика | ✔ | не трогать (кроме ленивой загрузки) | нет |
| History-уровни критичности | `history.html` (critical/warning/info) | события | ✔ | перенести в semantic states глобально | нет |

## 12. Дельта к целевой модели (промпт §8) и распределение

- **В 1.1 (STEP 1-12)**: audit (этот документ) → design system (только
  `base.html`+`style.css` как источник истины, токены, примитивы, semantic
  states, demo/unavailable) → IA-навигация → dashboard (`GET /api/dashboard`)
  → devices list/detail → system/monitoring (states) → capabilities v1 →
  modules v1 (схема+статусы) → roles-архитектура + 1-2 роли из существующих
  модулей → responsive (viewport + приоритетные страницы) → a11y → cleanup
  (удалить system_full.html, подключить/заменить style.css, мёртвый JS).
- **В 1.2**: Topology/Interfaces/Services-страницы, полный responsive всех
  28 шаблонов, network-роли (Router/Firewall/DHCP/DNS) через Network
  Configuration API, подписи каталога модулей.
- **В 1.3**: транзакционный netconf (Prepare/Apply/Verify/Commit/Rollback),
  Safe Network Mode, recovery-интерфейс.

## 13. Выводы (коротко)

1. Backend для UI-редизайна **пригоден**: 165 роутов покрывают всё
   существующее, нужны только аддитивные агрегаты (dashboard, capabilities,
   roles) и расширение схемы модулей. Переписывать нельзя — и не нужно.
2. Главная работа — **фундамент**: сейчас 4 темы, 0 токенов, 2 193 стр.
   инлайн-CSS, 4 799 стр. инлайн-JS без общих хелперов; без design system
   каждый следующий шаг будет разъезжаться.
3. Уже сейчас нарушения будущего DoD: нет viewport (mobile сломан),
   доступность ~0, `"--"` без состояний, сироты (`/history`, заглушка
   inventory), утеряны кнопки бэкапов — это чинится в ходе STEP 2/12.
4. Трафик-мусор (двойной `/api/status`, фоновые iframe-поллеры) — закрывается
   одним агрегатом и ленивой загрузкой приложений (STEP 4/12).
