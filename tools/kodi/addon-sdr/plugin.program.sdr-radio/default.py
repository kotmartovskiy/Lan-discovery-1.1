#!/usr/bin/env python3
# SDR Радио: эфирное радио через RTL-SDR свисток (sdr_radio.py, http://127.0.0.1:8344/stream).
import os
import signal
import subprocess
import time
import urllib.request
import xbmc
import xbmcgui

STREAMER = "/usr/local/bin/sdr_radio.py"
PIDFILE = "/tmp/sdr_radio.pid"
URL = "http://127.0.0.1:8344/stream"
LOGFILE = "/tmp/sdr_radio.log"

PRESETS = [
    ("FM 88-108 МГц (широкий)", 98000000, "wfm"),
    ("Авиа 118-137 МГц (AM)", 121500000, "am"),
    ("ДВМ 136-174 МГц (узкий FM)", 145000000, "nfm"),
    ("УКВ 400-470 МГц (узкий FM)", 433920000, "nfm"),
    ("Частота вручную...", None, None),
]

MOD_LABELS = ["WBFM (FM 88-108)", "AM (авиа)", "Узкий FM (12.5k)", "USB", "LSB"]
MOD_KEYS = ["wfm", "am", "nfm", "usb", "lsb"]


def read_pid():
    try:
        with open(PIDFILE) as f:
            return int(f.read().strip())
    except Exception:
        return None


def is_running():
    pid = read_pid()
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def stop_stream():
    pid = read_pid()
    if pid:
        try:
            os.kill(pid, signal.SIGTERM)
            for _ in range(10):
                time.sleep(0.3)
                try:
                    os.kill(pid, 0)
                except Exception:
                    break
            try:
                os.kill(pid, signal.SIGKILL)
            except Exception:
                pass
        except Exception:
            pass
    try:
        os.remove(PIDFILE)
    except Exception:
        pass


def log_tail(n=8):
    try:
        with open(LOGFILE) as f:
            return "".join(f.readlines()[-n:])
    except Exception:
        return "(лог пуст)"


def start_stream(freq, mod, gain=29):
    stop_stream()
    subprocess.Popen([STREAMER, "--freq", str(freq), "--mod", mod, "--gain", str(gain)],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True)
    for _ in range(20):
        time.sleep(0.4)
        try:
            with urllib.request.urlopen(URL, timeout=2) as r:
                if r.status == 200:
                    return True
        except Exception:
            pass
    return is_running()


def main():
    running = is_running()
    entries = []
    if running:
        entries.append(("stop", "⏹ Остановить радио", None, None))
    for name, freq, mod in PRESETS:
        entries.append(("preset", "▶ " + name, freq, mod))
    entries.append(("log", "ℹ Лог стримера", None, None))

    idx = xbmcgui.Dialog().select(
        "📻 SDR Радио (RTL-SDR)" + (" — играет" if running else ""),
        [e[1] for e in entries])
    if idx < 0:
        return

    kind, label, freq, mod = entries[idx]

    if kind == "stop":
        stop_stream()
        xbmc.Player().stop()
        xbmcgui.Dialog().notification("SDR Радио", "Остановлено", xbmcgui.NOTIFICATION_INFO, 2500)
        return
    if kind == "log":
        xbmcgui.Dialog().textviewer("SDR Радио — лог", log_tail())
        return

    if freq is None:
        kb = xbmc.Keyboard("98.0", "Частота, МГц (например 100.5)")
        kb.doModal()
        if not kb.isConfirmed():
            return
        try:
            mhz = float(kb.getText().replace(",", "."))
        except ValueError:
            xbmcgui.Dialog().notification("SDR Радио", "Неверная частота",
                                          xbmcgui.NOTIFICATION_ERROR, 4000)
            return
        m = xbmcgui.Dialog().select("Модуляция", MOD_LABELS)
        if m < 0:
            return
        mod = MOD_KEYS[m]
        freq = int(mhz * 1000000)
        name = "%.3f МГц %s" % (mhz, mod.upper())
    else:
        name = label.replace("▶ ", "")

    dlg = xbmcgui.DialogProgress()
    dlg.create("SDR Радио", "Запуск: %s..." % name)
    try:
        ok = start_stream(freq, mod)
    finally:
        dlg.close()
    if ok:
        xbmc.executebuiltin("PlayMedia(%s)" % URL)
        xbmcgui.Dialog().notification("SDR Радио", name, xbmcgui.NOTIFICATION_INFO, 4000)
    else:
        xbmcgui.Dialog().ok(
            "SDR Радио",
            "Не удалось запустить приём.\n\n"
            "Часто свисток занят (OpenWebRX/ADS-B) или не подключён.\n"
            "См. лог:\n%s" % log_tail(6))


if __name__ == "__main__":
    main()
