"""Загрузчик модульной системы: манифесты, состояние, nav/help реестры.

Модуль = каталог modules/<id>/ с файлом module.json (манифест):
    id          — уникальный ключ (латиницей)
    name        — название для справки/админки
    description — строка для карточки в /modules
    builtin     — true: код уже в панели (навигация доступна без install)
    url         — главный адрес страницы модуля
    prefixes    — URL-префиксы, которые гасятся when модуль выключен
    tab         — {"title": ..., "order": ...} вкладка в верхнем меню
    page        — ключ активной вкладки (дефолт = id)
    help        — true: рендерить modules/<id>/help.md в конце «Справки»
    deps        — {"apt": [...], "pip": [...], "services": [...], "dirs": [...],
                   "ports": [...]} — ставится кнопкой «Установить зависимости»
Состояние (installed/enabled/last_install) хранится в /etc/lan-discovery/modules.json.
"""
import glob
import json
import os
import time

_CORE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODULES_DIR = os.path.join(_CORE_DIR, "modules")
STATE_PATH = "/etc/lan-discovery/modules.json"

# Ядро: всегда в навигации, не выключается. group — доменная группа (STEP 3).
CORE_NAV = [
    {"page": "devices", "title": "Устройства", "url": "/", "order": 10, "group": "Устройства"},
    {"page": "history", "title": "История", "url": "/history", "order": 35, "group": "Мониторинг"},
    {"page": "apps", "title": "Приложения", "url": "/apps", "order": 70, "group": "Приложения"},
    {"page": "system", "title": "Система", "url": "/system", "order": 80, "group": "Система"},
    {"page": "modules", "title": "Модули", "url": "/modules", "order": 85, "group": "Система", "admin": True},
    {"page": "about", "title": "О системе", "url": "/about", "order": 90, "group": "Система"},
    {"page": "help", "title": "Справка", "url": "/help", "order": 100, "group": "Помощь"},
]

# Порядок доменных групп в шапке (пункты без known-группы уходят в «Прочее» в конец).
NAV_GROUP_ORDER = ["Устройства", "Мониторинг", "Приложения", "Система", "Помощь"]

# Категории рабочего стола /apps (порядок разделов) и ядровые плитки (без манифестов).
APP_CATEGORY_ORDER = ["Утилиты", "Медиа", "Игры", "Система и сеть"]

CORE_APPS = [
    # (category, key, title, icon, order)
    ("Утилиты", "calc", "Калькулятор", "🔢", 10),
    ("Утилиты", "calendar", "Календарь", "📅", 20),
    ("Утилиты", "timer", "Таймер", "⏳", 30),
    ("Утилиты", "stopwatch", "Секундомер", "⏱", 40),
    ("Утилиты", "alarm", "Будильник", "⏰", 50),
    ("Игры", "snake", "Змейка", "🐍", 10),
    ("Игры", "tetris", "Тетрис", "🟦", 20),
    ("Игры", "g2048", "2048", "🟩", 30),
    ("Игры", "arkanoid", "Арканоид", "🟪", 40),
]

_manifest_cache = {"ts": 0.0, "data": None}
_state_cache = {"mtime": -1, "data": None}


def _read_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_state(state):
    try:
        os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
        with open(STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        _state_cache["mtime"] = -1
        return True
    except Exception:
        return False


def load_state():
    try:
        mtime = os.path.getmtime(STATE_PATH)
    except Exception:
        mtime = -1
    if _state_cache["data"] is not None and _state_cache["mtime"] == mtime:
        return _state_cache["data"]
    data = _read_json(STATE_PATH, {})
    _state_cache["data"] = data
    _state_cache["mtime"] = mtime
    return data


def discover_modules(force=False):
    now = time.time()
    if not force and _manifest_cache["data"] is not None and now - _manifest_cache["ts"] < 5:
        return _manifest_cache["data"]
    mods = []
    for path in sorted(glob.glob(os.path.join(MODULES_DIR, "*", "module.json"))):
        m = _read_json(path, None)
        if not isinstance(m, dict) or not m.get("id"):
            continue
        m["_dir"] = os.path.dirname(path)
        mods.append(m)
    _manifest_cache["data"] = mods
    _manifest_cache["ts"] = now
    return mods


def get_module(mid):
    for m in discover_modules():
        if m["id"] == mid:
            return m
    return None


def module_status(mid):
    """(installed, enabled). Дефолт для builtin-модулей — True/True."""
    m = get_module(mid)
    builtin = bool(m and m.get("builtin"))
    entry = load_state().get(mid) or {}
    installed = entry.get("installed", builtin)
    enabled = entry.get("enabled", builtin)
    return bool(installed), bool(enabled)


def set_module_status(mid, installed=None, enabled=None):
    state = load_state()
    entry = state.get(mid) or {}
    if installed is not None:
        entry["installed"] = bool(installed)
    if enabled is not None:
        entry["enabled"] = bool(enabled)
    if not entry:
        return False
    state[mid] = entry
    return save_state(state)


def record_install_result(mid, result):
    state = load_state()
    entry = state.get(mid) or {}
    entry["installed"] = True
    entry["last"] = result
    state[mid] = entry
    save_state(state)


def nav_items():
    items = list(CORE_NAV)
    for m in discover_modules():
        installed, enabled = module_status(m["id"])
        tab = m.get("tab")
        if installed and enabled and isinstance(tab, dict) and tab.get("title"):
            items.append({
                "page": m.get("page") or m["id"],
                "title": tab["title"],
                "url": m.get("url", "/"),
                "order": int(tab.get("order", 500)),
                "group": tab.get("group") or "Прочее",
                "module": m["id"],
            })
    return sorted(items, key=lambda x: x["order"])


def nav_groups(admin=False):
    """Доменные группы навигации: [{name, entries}] (порядок — NAV_GROUP_ORDER).

    admin=False скрывает пункты с флагом admin (например, «Модули»).
    Ключ entries, а не items: в Jinja словарь с ключом "items" конфликтует
    с методом dict.items (attempts lookup атрибута первым).
    """
    buckets = {}
    for it in nav_items():
        if it.get("admin") and not admin:
            continue
        buckets.setdefault(it.get("group") or "Прочее", []).append(it)
    out = [{"name": name, "entries": buckets.pop(name)}
           for name in NAV_GROUP_ORDER if buckets.get(name)]
    out += [{"name": name, "entries": entries} for name, entries in sorted(buckets.items())]
    return out


def active_page(path):
    """Ключ активной вкладки по пути запроса ('' — ничего)."""
    if path == "/modules":
        return "modules"
    for it in nav_items():
        url = it["url"]
        if url == "/":
            if path == "/":
                return it["page"]
        elif path == url or path.startswith(url + "/"):
            return it["page"]
    return ""


def disabled_prefixes():
    """URL-префиксы выключенных (но установленных) модулей — для before_request."""
    out = []
    for m in discover_modules():
        installed, enabled = module_status(m["id"])
        if installed and not enabled:
            prefixes = m.get("prefixes")
            if not prefixes:
                u = m.get("url")
                prefixes = [u] if u else []
            for p in prefixes:
                if p and p not in out:
                    out.append(p)
    return out


def app_items():
    """Плитки приложений из включённых модулей (поле app в манифесте)."""
    out = []
    for m in discover_modules():
        installed, enabled = module_status(m["id"])
        app = m.get("app")
        if installed and enabled and isinstance(app, dict) and app.get("title"):
            out.append({
                "key": app.get("key") or m["id"],
                "title": app["title"],
                "icon": app.get("icon", "📦"),
                "category": app.get("category", "Прочее"),
                "order": int(app.get("order", 500)),
                "description": m.get("description", ""),
                "module": m["id"],
            })
    return out


def block_items(slot=None):
    """Блоки включённых модулей для слота во вкладке (поле block в манифесте).

    Манифест блока:
        "type": "block",
        "block": {"slot": "currencies", "order": 10, "title": "Fiat валюты",
                  "template": "<id>/block.html"}   # template опционален
    Возвращает [{id, title, order, slot, module, template}] отсортированное по order.
    """
    out = []
    for m in discover_modules():
        installed, enabled = module_status(m["id"])
        blk = m.get("block")
        if not (installed and enabled and isinstance(blk, dict)):
            continue
        s = blk.get("slot")
        if slot is not None and s != slot:
            continue
        out.append({
            "id": m["id"],
            "title": blk.get("title") or m.get("name") or m["id"],
            "order": int(blk.get("order", 500)),
            "slot": s,
            "module": m["id"],
            "template": blk.get("template") or (m["id"] + "/block.html"),
        })
    return sorted(out, key=lambda x: x["order"])


def desktop_categories():
    """Разделы рабочего стола /apps: ядровые плитки + плитки включённых модулей."""
    cats = {name: [] for name in APP_CATEGORY_ORDER}
    for cat, key, title, icon, order in CORE_APPS:
        cats.setdefault(cat, []).append(
            {"key": key, "title": title, "icon": icon, "order": order,
             "description": "", "module": None})
    for it in app_items():
        cats.setdefault(it["category"], []).append(it)
    out = []
    for name, items in cats.items():
        if items:
            out.append({"name": name, "tiles": sorted(items, key=lambda x: x["order"])})
    return out


def help_sections():
    """Секции справки включённых модулей: [{id, title, html}]. help.md → markdown."""
    try:
        import markdown as _markdown
    except Exception:
        _markdown = None
    out = []
    for m in discover_modules():
        installed, enabled = module_status(m["id"])
        if not (installed and enabled and m.get("help")):
            continue
        path = os.path.join(m["_dir"], "help.md")
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
        except Exception:
            continue
        if _markdown:
            html = _markdown.markdown(text, extensions=["extra"])
        else:
            esc = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            html = "<pre>" + esc + "</pre>"
        out.append({"id": m["id"], "title": m.get("name") or m["id"], "html": html})
    return out
