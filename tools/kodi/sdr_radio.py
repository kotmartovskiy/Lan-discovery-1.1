#!/usr/bin/env python3
"""SDR-радио: rtl_fm -> ffmpeg (aac128k) -> http://<host>:8344/stream

Запуск: sdr_radio.py --freq 98000000 --mod wfm [--gain 29] [--port 8344] [--ppm 0]
Моды: wfm (WBFM 200k), nfm (12.5k), am, usb, lsb.
Стоп: kill $(cat /run/sdr_radio.pid) или SIGTERM/kill на процесс.
Лог: /tmp/sdr_radio.log. Порт занят → выход с кодом 1.
"""
import argparse
import os
import signal
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PIDFILE = "/tmp/sdr_radio.pid"
LOGFILE = "/tmp/sdr_radio.log"

MODS = {
    "wfm": ("-M", "wbfm", "-s", "200000"),
    "nfm": ("-M", "fm", "-s", "12500"),
    "am": ("-M", "am", "-s", "10000"),
    "usb": ("-M", "usb", "-s", "3000"),
    "lsb": ("-M", "lsb", "-s", "3000"),
}


def log(msg):
    line = time.strftime("[%Y-%m-%d %H:%M:%S] ") + msg + "\n"
    sys.stderr.write(line)
    sys.stderr.flush()
    try:
        with open(LOGFILE, "a") as f:
            f.write(line)
    except Exception:
        pass


class Broadcaster:
    def __init__(self):
        self.clients = []
        self.lock = threading.Lock()

    def add(self, sock):
        with self.lock:
            self.clients.append(sock)

    def remove(self, sock):
        with self.lock:
            if sock in self.clients:
                self.clients.remove(sock)
        try:
            sock.close()
        except Exception:
            pass

    def send(self, data):
        with self.lock:
            dead = []
            for s in self.clients:
                try:
                    s.sendall(data)
                except Exception:
                    dead.append(s)
            for s in dead:
                self.clients.remove(s)
                try:
                    s.close()
                except Exception:
                    pass

    def count(self):
        with self.lock:
            return len(self.clients)


class StreamHandler(BaseHTTPRequestHandler):
    bcast = None

    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path.rstrip("/") not in ("", "/stream"):
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "audio/aac")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        sock = self.connection
        self.bcast.add(sock)
        log("client connected (%d total)" % self.bcast.count())
        try:
            while True:
                time.sleep(1)
                if sock not in self.bcast.clients:
                    break
        except Exception:
            pass
        finally:
            self.bcast.remove(sock)
            log("client gone (%d total)" % self.bcast.count())


def read_pid():
    try:
        with open(PIDFILE) as f:
            return int(f.read().strip())
    except Exception:
        return None


def kill_old():
    pid = read_pid()
    if pid:
        try:
            os.kill(pid, signal.SIGTERM)
            time.sleep(0.5)
            os.kill(pid, signal.SIGKILL)
        except Exception:
            pass
    try:
        os.remove(PIDFILE)
    except Exception:
        pass


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--freq", type=int, required=True)
    p.add_argument("--mod", default="wfm", choices=sorted(MODS.keys()))
    p.add_argument("--gain", type=int, default=29)
    p.add_argument("--port", type=int, default=8344)
    p.add_argument("--ppm", type=int, default=0)
    args = p.parse_args()

    kill_old()

    rtl_cmd = ["rtl_fm", "-f", str(args.freq), "-g", str(args.gain)]
    if args.ppm:
        rtl_cmd += ["-p", str(args.ppm)]
    rtl_cmd += list(MODS[args.mod]) + ["-"]

    ff_cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-f", "s16le", "-ar", "48000", "-ac", "1", "-i", "pipe:0",
        "-codec:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "1",
        "-f", "adts", "pipe:1",
    ]

    log("start freq=%d mod=%s gain=%d port=%d" % (args.freq, args.mod, args.gain, args.port))
    log("rtl_fm: %s" % " ".join(rtl_cmd))

    rtl = subprocess.Popen(rtl_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    ff = subprocess.Popen(ff_cmd, stdin=rtl.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    rtl.stdout.close()

    with open(PIDFILE, "w") as f:
        f.write(str(os.getpid()))

    bcast = Broadcaster()
    StreamHandler.bcast = bcast

    def pump():
        while True:
            data = ff.stdout.read1(8192)
            if not data:
                log("ffmpeg stdout EOF")
                break
            bcast.send(data)
        os.kill(os.getpid(), signal.SIGTERM)

    threading.Thread(target=pump, daemon=True).start()

    def reap(*_):
        for proc in (rtl, ff):
            try:
                proc.terminate()
                proc.wait(timeout=2)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        try:
            os.remove(PIDFILE)
        except Exception:
            pass
        log("stopped")
        os._exit(0)

    signal.signal(signal.SIGTERM, reap)
    signal.signal(signal.SIGINT, reap)

    try:
        srv = ThreadingHTTPServer(("0.0.0.0", args.port), StreamHandler)
    except OSError as e:
        log("port %d busy: %s" % (args.port, e))
        reap()
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    log("http ready on %d" % args.port)

    while True:
        time.sleep(1)
        if rtl.poll() is not None:
            err = rtl.stderr.read().decode("utf-8", "replace").strip()
            log("rtl_fm exited rc=%s err=%s" % (rtl.returncode, err))
            if err and "error" in err.lower():
                sys.stderr.write(err + "\n")
            reap()


if __name__ == "__main__":
    main()
