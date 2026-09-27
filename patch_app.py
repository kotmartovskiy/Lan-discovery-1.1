import sys
import re


def patch_app():
    with open("/opt/lan-discovery/app.py", "r") as f:
        content = f.read()

    # 1. Add imports at the top
    old_imports = 'from datetime import datetime'
    new_imports = '''from datetime import datetime
import sys
sys.path.insert(0, "/opt/lan-discovery")
from modules.currencies import update_all as update_currencies, get_latest as get_currency_latest, get_history as get_currency_history
from modules.monitor import get_system_overview, get_device_inventory, get_netdata_stats_for_host
from modules.inventory import scan_device_full as scan_device_inventory, get_inventory, init_inventory_db, scan_all_devices
from modules.recycling import update_all as update_recycling, get_latest as get_recycling_latest'''
    content = content.replace(old_imports, new_imports, 1)

    # 2. Update menu in HTML
    old_menu = '''<div class="tabs">
<a href="/" class="{{ 'active' if page == 'devices' else '' }}">
Устройства
</a>

<a href="/history" class="{{ 'active' if page == 'history' else '' }}">
История
</a>

<a href="/weather" class="{{ 'active' if page == 'weather' else '' }}">
Погода
</a>

<a href="/system" class="{{ 'active' if page == 'system' else '' }}">
Система
</a>

<a href="/about" class="{{ 'active' if page == 'about' else '' }}">
О системе
</a>
</div>'''

    new_menu = '''<div class="tabs">
<a href="/" class="{{ 'active' if page == 'devices' else '' }}">
Устройства
</a>

<a href="/inventory" class="{{ 'active' if page == 'inventory' else '' }}">
Инвентаризация
</a>

<a href="/monitoring" class="{{ 'active' if page == 'monitoring' else '' }}">
Мониторинг
</a>

<a href="/currencies" class="{{ 'active' if page == 'currencies' else '' }}">
Валюты
</a>

<a href="/weather" class="{{ 'active' if page == 'weather' else '' }}">
Погода
</a>

<a href="/system" class="{{ 'active' if page == 'system' else '' }}">
Система
</a>

<a href="/about" class="{{ 'active' if page == 'about' else '' }}">
О системе
</a>
</div>'''

    content = content.replace(old_menu, new_menu, 1)

    # 3. Add currencies page HTML before the system page
    currencies_html = '''

{% if page == 'currencies' %}

<h2>Курсы валют и металлов</h2>

{% if currency_data %}

{% for category, items in currency_data.items() %}

<h3>{{ currency_category_name(category) }}</h3>

<table>
<thead>
<tr>
<th>Название</th>
<th>Цена</th>
<th>Ед.</th>
<th>24ч</th>
<th>Источник</th>
</tr>
</thead>
<tbody>

{% for item in items %}
<tr>
<td><strong>{{ item.name }}</strong></td>
<td>{{ "%.2f"|format(item.value) if item.value else '-' }}</td>
<td>{{ item.unit }}</td>
<td>
{% if item.change_24h %}
<span class="{{ 'online' if item.change_24h > 0 else 'offline' }}">
{{ "+" if item.change_24h > 0 else "" }}{{ "%.2f"|format(item.change_24h) }}%
</span>
{% else %}-{% endif %}
</td>
<td class="small">{{ item.source }}</td>
</tr>
{% endfor %}

</tbody>
</table>

{% endfor %}

{% else %}

<div class="info">Данные загружаются... Попробуйте обновить страницу через минуту.</div>

{% endif %}

<h3>Приемные пункты (ЦФО)</h3>

{% if recycling_data %}

{% for category, items in recycling_data.items() %}

<h4>{{ recycling_category_name(category) }}</h4>

<table>
<thead>
<tr>
<th>Материал</th>
<th>Цена</th>
<th>Ед.</th>
<th>Регион</th>
<th>Источник</th>
</tr>
</thead>
<tbody>

{% for item in items %}
<tr>
<td>{{ item.material }}</td>
<td>{{ "%.2f"|format(item.price_min) if item.price_min else '-' }}</td>
<td>{{ item.unit }}</td>
<td class="small">{{ item.region }}</td>
<td class="small">{{ item.source }}</td>
</tr>
{% endfor %}

</tbody>
</table>

{% endfor %}

{% else %}

<div class="info">Данные о приемных пунктах пока недоступны.</div>

{% endif %}

<div style="margin-top:20px;">
<span class="small">Последнее обновление: {{ currency_updated or 'никогда' }}</span>
</div>

{% endif %}


{% if page == 'monitoring' %}

<h2>Мониторинг устройств</h2>

<div class="system-grid">

{% for host in monitoring_hosts %}

<div class="card">

<div class="card-title">{{ host.name or host.ip }}</div>

<div class="info-row">
<span class="info-label">IP:</span> {{ host.ip }}
</div>

<div class="info-row">
<span class="info-label">Netdata:</span>
{% if host.netdata %}
<span class="status-ok">● Активен</span>
{% else %}
<span class="status-error">● Недоступен</span>
{% endif %}
</div>

{% if host.cpu_percent is not none %}
<div class="info-row">
<span class="info-label">CPU:</span>
<span class="{{ 'status-warn' if host.cpu_percent > 80 else 'status-ok' }}">
{{ host.cpu_percent }}%
</span>
</div>
{% endif %}

{% if host.ram_percent is not none %}
<div class="info-row">
<span class="info-label">RAM:</span>
<span class="{{ 'status-warn' if host.ram_percent > 80 else 'status-ok' }}">
{{ host.ram_percent }}%
</span>
</div>
{% endif %}

{% if host.uptime %}
<div class="info-row">
<span class="info-label">Uptime:</span> {{ host.uptime }}
</div>
{% endif %}

</div>

{% endfor %}

</div>

{% if netdata_overview %}

<h3>Система Orange Pi (Netdata)</h3>

<div class="system-grid">

<div class="card">
<div class="card-title">CPU</div>
<div class="info-row">
<span class="info-label">Загрузка:</span>
{{ netdata_overview.cpu.busy_percent }}%
</div>
{% if netdata_overview.cpu.labels %}
<div class="info-row small">
{{ netdata_overview.cpu.labels|join(', ') }}
</div>
{% endif %}
</div>

<div class="card">
<div class="card-title">RAM</div>
{% for label, value in netdata_overview.ram.labels|zip(netdata_overview.ram.values) %}
<div class="info-row">
<span class="info-label">{{ label }}:</span> {{ value }} MiB
</div>
{% endfor %}
</div>

<div class="card">
<div class="card-title">Сеть</div>
{% for label, value in netdata_overview.network.labels|zip(netdata_overview.network.values) %}
<div class="info-row">
<span class="info-label">{{ label }}:</span> {{ value }} bytes/s
</div>
{% endfor %}
</div>

</div>

{% endif %}

{% endif %}


{% if page == 'inventory' %}

<h2>Инвентаризация устройств</h2>

{% if inventories %}

{% for inv in inventories %}

<div class="card" style="margin-bottom: 20px;">

<div class="card-title">
{{ inv.model or inv.hostname or inv.ip }}
{% if inv.device_type %}
<span class="badge">{{ inv.device_type }}</span>
{% endif %}
{% if inv.netdata_host %}
<span class="badge" style="background:#65d46e;color:#000;">NETDATA</span>
{% endif %}
</div>

<div class="info-row">
<span class="info-label">IP:</span> {{ inv.ip }}
</div>

{% if inv.hostname %}
<div class="info-row">
<span class="info-label">Hostname:</span> {{ inv.hostname }}
</div>
{% endif %}

{% if inv.mac %}
<div class="info-row">
<span class="info-label">MAC:</span> {{ inv.mac }}
</div>
{% endif %}

{% if inv.manufacturer %}
<div class="info-row">
<span class="info-label">Производитель:</span> {{ inv.manufacturer }}
</div>
{% endif %}

{% if inv.model %}
<div class="info-row">
<span class="info-label">Модель:</span> {{ inv.model }}
</div>
{% endif %}

{% if inv.serial_number %}
<div class="info-row">
<span class="info-label">Серийный номер:</span> {{ inv.serial_number }}
</div>
{% endif %}

{% if inv.firmware %}
<div class="info-row">
<span class="info-label">Прошивка/ОС:</span> {{ inv.firmware }}
</div>
{% endif %}

{% if inv.os_info %}
<div class="info-row">
<span class="info-label">ОС:</span> {{ inv.os_info }}
</div>
{% endif %}

{% if inv.cpu_model %}
<div class="info-row">
<span class="info-label">CPU:</span> {{ inv.cpu_model }}
</div>
{% endif %}

{% if inv.open_ports is iterable and inv.open_ports is not string and inv.open_ports|length > 0 %}

<div class="subsection-title">Открытые порты</div>

<table>
<thead>
<tr>
<th>Порт</th>
<th>Протокол</th>
<th>Состояние</th>
<th>Сервис</th>
</tr>
</thead>
<tbody>
{% for port in inv.open_ports %}
<tr>
<td>{{ port.port }}</td>
<td>{{ port.proto }}</td>
<td>{{ port.state }}</td>
<td>{{ port.service }}</td>
</tr>
{% endfor %}
</tbody>
</table>

{% endif %}

{% if inv.last_scan %}
<div class="info-row small" style="margin-top:10px;">
<span class="info-label">Последнее сканирование:</span> {{ inv.last_scan }}
</div>
{% endif %}

</div>

{% endfor %}

{% else %}

<div class="info">Инвентаризация пока не выполнялась. Нажмите кнопку для запуска.</div>

{% endif %}

<div style="margin-top:20px;">
<form method="post" action="/inventory/scan">
<button type="submit">Запустить сканирование всех устройств</button>
</form>
</div>

{% endif %}'''

    # Insert before the system page
    old_system_marker = "{% if page == 'system' %}"
    content = content.replace(old_system_marker, currencies_html + "\n" + old_system_marker, 1)

    # 4. Add helper functions before page_data()
    helper_functions = '''

def currency_category_name(cat):
    names = {
        "fiat": "Fiat валюты",
        "crypto": "Криптовалюта",
        "precious": "Драгоценные металлы",
        "industrial": "Промышленные металлы",
    }
    return names.get(cat, cat)


def recycling_category_name(cat):
    names = {
        "paper": "Бумага / макулатура",
        "metal": "Металлы",
        "electronics": "Электроника",
    }
    return names.get(cat, cat)


app.jinja_env.globals["currency_category_name"] = currency_category_name
app.jinja_env.globals["recycling_category_name"] = recycling_category_name


def update_currencies_background():
    try:
        update_currencies()
    except Exception as e:
        print(f"CURRENCIES BG ERROR: {e}", flush=True)


def update_recycling_background():
    try:
        update_recycling()
    except Exception as e:
        print(f"RECYCLING BG ERROR: {e}", flush=True)'''

    content = content.replace("def page_data():", helper_functions + "\n\ndef page_data():", 1)

    # 5. Add routes before the if __name__ block
    new_routes = '''

@app.route("/currencies")
def currencies():
    data = page_data()

    try:
        currency_data = get_currency_latest()
    except Exception:
        currency_data = {}

    try:
        recycling_data = get_recycling_latest()
    except Exception:
        recycling_data = {}

    currency_updated = ""
    if currency_data:
        for cat_items in currency_data.values():
            if cat_items:
                currency_updated = cat_items[0].get("fetched_at", "")
                break

    data["currency_data"] = currency_data
    data["recycling_data"] = recycling_data
    data["currency_updated"] = currency_updated

    return render_template_string(
        HTML,
        page="currencies",
        **data
    )


@app.route("/monitoring")
def monitoring():
    data = page_data()

    hosts = [
        {"ip": "192.168.3.234", "name": "Orange Pi", "netdata": True},
        {"ip": "192.168.3.7", "name": "Комп рабочий LAN", "netdata": False},
        {"ip": "192.168.3.236", "name": "Thinkpad T480 WiFi", "netdata": False},
        {"ip": "192.168.3.239", "name": "Thinkpad T480 LAN", "netdata": False},
    ]

    monitoring_hosts = []
    for host in hosts:
        info = {"ip": host["ip"], "name": host["name"], "netdata": False,
                "cpu_percent": None, "ram_percent": None, "uptime": ""}

        if host["netdata"]:
            try:
                stats = get_netdata_stats_for_host(host["ip"])
                info["netdata"] = True
                info["cpu_percent"] = stats.get("cpu_percent", 0)
                info["ram_percent"] = stats.get("ram_percent", 0)
            except Exception:
                pass

        monitoring_hosts.append(info)

    try:
        netdata_overview = get_system_overview()
    except Exception:
        netdata_overview = None

    data["monitoring_hosts"] = monitoring_hosts
    data["netdata_overview"] = netdata_overview

    return render_template_string(
        HTML,
        page="monitoring",
        **data
    )


@app.route("/inventory")
def inventory():
    data = page_data()

    try:
        inventories = get_inventory()
    except Exception:
        inventories = []

    data["inventories"] = inventories

    return render_template_string(
        HTML,
        page="inventory",
        **data
    )


@app.route("/inventory/scan", methods=["POST"])
def inventory_scan():
    import threading
    threading.Thread(
        target=scan_all_devices,
        daemon=True
    ).start()
    return redirect(url_for("inventory"))


@app.route("/inventory/device/<ip>")
def inventory_device(ip):
    data = page_data()

    try:
        inv = get_inventory(ip)
    except Exception:
        inv = None

    data["inventory"] = inv

    return render_template_string(
        HTML,
        page="inventory_device",
        **data
    )


@app.route("/api/currencies")
def api_currencies():
    try:
        data = get_currency_latest()
        return {"ok": True, "data": data}
    except Exception as e:
        return {"ok": False, "error": str(e)}, 500


@app.route("/api/monitoring/<ip>")
def api_monitoring(ip):
    try:
        stats = get_netdata_stats_for_host(ip)
        return {"ok": True, "data": stats}
    except Exception as e:
        return {"ok": False, "error": str(e)}, 500


@app.route("/api/inventory/<ip>")
def api_inventory(ip):
    try:
        inv = get_inventory(ip)
        if inv:
            return {"ok": True, "data": inv}
        return {"ok": False, "error": "Device not found"}, 404
    except Exception as e:
        return {"ok": False, "error": str(e)}, 500'''

    content = content.replace(
        'if __name__ == "__main__":',
        new_routes + '\n\n\nif __name__ == "__main__":',
        1
    )

    # 6. Add schedule thread at startup
    startup_code = '''    threading.Thread(
        target=scan_loop,
        daemon=True
    ).start()

    threading.Thread(
        target=update_currencies_background,
        daemon=True
    ).start()

    threading.Thread(
        target=update_recycling_background,
        daemon=True
    ).start()

    import schedule as sched
    sched.every(6).hours.do(update_currencies_background)
    sched.every(24).hours.do(update_recycling_background)

    def run_schedule():
        while True:
            sched.run_pending()
            time.sleep(60)

    threading.Thread(
        target=run_schedule,
        daemon=True
    ).start()'''

    content = content.replace(
        '''    threading.Thread(
        target=scan_loop,
        daemon=True
    ).start()''',
        startup_code,
        1
    )

    # Write the patched file
    with open("/opt/lan-discovery/app.py", "w") as f:
        f.write(content)

    print("APP.PY PATCHED SUCCESSFULLY")


if __name__ == "__main__":
    patch_app()
