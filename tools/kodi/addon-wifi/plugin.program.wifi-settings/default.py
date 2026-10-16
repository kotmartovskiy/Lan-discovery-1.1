#!/usr/bin/env python3
# Wi-Fi Settings: выбор Wi-Fi сети и ввод пароля через nmcli (NetworkManager).
import re
import subprocess
import xbmc
import xbmcgui


def nmcli(args, timeout=45):
    try:
        r = subprocess.run(["sudo", "-n", "nmcli"] + list(args),
                           capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout or "").strip(), (r.stderr or "").strip()
    except Exception as e:
        return 1, "", str(e)


def split_unescaped(line):
    parts = re.split(r"(?<!\\):", line)
    return [p.replace("\\:", ":").replace("\\\\", "\\") for p in parts]


def current_connection():
    rc, out, _ = nmcli(["-t", "-f", "NAME,TYPE,DEVICE", "con", "show", "--active"])
    if rc != 0:
        return None
    for line in out.splitlines():
        f = split_unescaped(line)
        if len(f) >= 3 and f[1] == "802-11-wireless":
            return f[0], f[2]
    return None


def wifi_list():
    rc, out, err = nmcli(["-t", "-f", "ACTIVE,SSID,SIGNAL,SECURITY", "dev", "wifi", "list", "--rescan", "yes"])
    if rc != 0:
        raise RuntimeError(err or "nmcli dev wifi list failed")
    nets = []
    seen = set()
    for line in out.splitlines():
        f = split_unescaped(line)
        if len(f) < 4:
            continue
        active, ssid, signal, sec = f[0], f[1], f[2], f[3]
        if not ssid or ssid in seen:
            continue
        seen.add(ssid)
        nets.append({
            "ssid": ssid,
            "active": active == "yes",
            "signal": int(signal) if signal.isdigit() else 0,
            "secure": bool(sec) and sec != "--",
            "security": sec or "",
        })
    nets.sort(key=lambda n: (not n["active"], -n["signal"]))
    return nets


def connect(ssid, password=None):
    if password:
        rc, out, err = nmcli(["dev", "wifi", "connect", ssid, "password", password])
    else:
        rc, out, err = nmcli(["dev", "wifi", "connect", ssid])
    return rc, (out or err)


def main():
    cur = current_connection()
    cur_txt = ("Подключено: %s (%s)" % (cur[0], cur[1])) if cur else "Нет Wi-Fi подключения"

    while True:
        try:
            nets = wifi_list()
        except Exception as e:
            xbmcgui.Dialog().ok("Wi-Fi", "Ошибка nmcli:\n%s" % e)
            return

        labels = []
        for n in nets:
            lock = " 🔒" if n["secure"] else ""
            act = " ●" if n["active"] else ""
            labels.append("%s%s  %d%%%s" % (act, n["ssid"], n["signal"], lock))
        labels.append("── Обновить список ──")
        labels.append("── Отключить Wi-Fi ──" if cur else "── Выход ──")

        idx = xbmcgui.Dialog().select("Wi-Fi — %s" % cur_txt, labels)
        if idx < 0:
            return
        if idx >= len(nets):
            if labels[idx].startswith("── Обновить"):
                xbmc.executebuiltin("BusyDialog")
                continue
            if cur:
                nmcli(["con", "down", "id", cur[0]])
                xbmcgui.Dialog().notification("Wi-Fi", "Отключено", xbmcgui.NOTIFICATION_INFO, 3000)
                return
            return

        net = nets[idx]
        if net["active"]:
            xbmcgui.Dialog().notification("Wi-Fi", "%s уже подключена" % net["ssid"],
                                          xbmcgui.NOTIFICATION_INFO, 3000)
            return

        password = None
        if net["secure"]:
            kb = xbmc.Keyboard("", "Пароль: %s" % net["ssid"], True)
            kb.doModal()
            if not kb.isConfirmed():
                return
            password = kb.getText()
            if not password:
                return

        dlg = xbmcgui.DialogProgress()
        dlg.create("Wi-Fi", "Подключение к %s..." % net["ssid"])
        dlg.update(50)
        try:
            rc, msg = connect(net["ssid"], password)
        finally:
            dlg.close()
        if rc == 0:
            xbmcgui.Dialog().ok("Wi-Fi", "Подключено к %s" % net["ssid"])
            return
        retry = xbmcgui.Dialog().yesno("Wi-Fi", "Не удалось подключиться:\n%s\n\nПовторить?" % msg)
        if not retry:
            return


if __name__ == "__main__":
    main()
