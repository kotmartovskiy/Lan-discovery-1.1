#!/usr/bin/env python3
"""demo_lint.py — проверка демо-слепка перед публикацией.

Проверяет папку demo/:
  1) все ссылки href/src/action ведут на существующие файлы (или заглушку);
  2) нет абсолютных путей («/...») и внешних URL в атрибутах;
  3) в JS нет fetch("...") с абсолютными путями;
  4) секреты вычищены (notes/secrets пусты, в settings нет token/password);
  5) каркасные файлы на месте (index, restore, stub, 404, demo.js, static).

Запуск: python tools/demo_lint.py <папка-demo>
Код 0 = чисто, 1 = найдены ошибки.
"""
import json
import os
import re
import sys

ROOT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "demo")

ATTR_RE = re.compile(
    r'(?:href|src|action)\s*=\s*["\']([^"\']*)["\']', re.I)
FETCH_ABS_RE = re.compile(r"""fetch\(\s*["']/""")
XHR_ABS_RE = re.compile(r"""\.open\(\s*["'][A-Z]+["']\s*,\s*["']/""")
EXT_ATTR_RE = re.compile(r'^https?://', re.I)

errors = []
warns = []


def err(msg):
    errors.append(msg)


def warn(msg):
    warns.append(msg)


def check_files():
    for f in ("index.html", "restore.html", "stub.html", "404.html",
              "demo.js", os.path.join("static", "style.css")):
        if not os.path.exists(os.path.join(ROOT, f)):
            err("нет каркасного файла: " + f)


def check_secrets():
    for rel, expect_empty in (("api/notes.json", True),
                              ("api/secrets.json", True),
                              ("api/settings.json", False)):
        p = os.path.join(ROOT, rel)
        if not os.path.exists(p):
            err("нет " + rel)
            continue
        try:
            data = json.load(open(p, encoding="utf-8"))
        except Exception as e:
            err("%s: не JSON (%s)" % (rel, e))
            continue
        if expect_empty and data != []:
            err("%s: должен быть пустым []" % rel)
        if isinstance(data, dict):
            blob = json.dumps(data).lower()
            for k in ("token", "password_hash", "secret_key", "api_key",
                      "access_token", "bssid"):
                if '"%s"' % k in blob:
                    err("%s: остался ключ %s" % (rel, k))
    # нигде в api не должно быть хешей паролей
    api_dir = os.path.join(ROOT, "api")
    for dirpath, _, files in os.walk(api_dir):
        for fn in files:
            p = os.path.join(dirpath, fn)
            try:
                text = open(p, encoding="utf-8").read()
            except Exception:
                continue
            if "password_hash" in text or "$2b$" in text:
                err("утечка hash в " + os.path.relpath(p, ROOT))


def check_html():
    n_html = 0
    for dirpath, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d != "api"]
        for fn in files:
            if not fn.endswith(".html"):
                continue
            n_html += 1
            rel = os.path.relpath(os.path.join(dirpath, fn), ROOT)
            html = open(os.path.join(dirpath, fn), encoding="utf-8").read()
            for m in ATTR_RE.finditer(html):
                url = m.group(1).strip()
                if not url or url.startswith(("#", "javascript:", "mailto:",
                                              "data:")):
                    continue
                if EXT_ATTR_RE.match(url):
                    err("%s: внешняя ссылка в атрибуте: %s" % (rel, url[:90]))
                    continue
                if url.startswith("/"):
                    err("%s: абсолютный путь: %s" % (rel, url[:90]))
                    continue
                if url.startswith("//"):
                    err("%s: протокол-относительная: %s" % (rel, url[:90]))
                    continue
                pure = url.split("#")[0].split("?")[0]
                if not pure:
                    continue
                if pure.endswith(".html") or "/" not in pure or pure.split(
                        "/")[0] in ("static", "api", "stub.html"):
                    target = os.path.join(ROOT, pure)
                    if pure.endswith(".html") and not os.path.exists(target):
                        err("%s: битая ссылка → %s" % (rel, pure))
            for m in FETCH_ABS_RE.finditer(html):
                err("%s: fetch с абсолютным путём: %s" % (rel, m.group(0)))
            for m in XHR_ABS_RE.finditer(html):
                err("%s: XHR с абсолютным путём: %s" % (rel, m.group(0)))
            if 'src="http' in html or "src='http" in html:
                err("%s: внешний скрипт/картинка" % rel)
            # навигационные ссылки-обязанности
            if fn == "index.html":
                if 'href="restore.html"' not in html:
                    err("index.html: нет ссылки на restore.html")
                if "Демо-режим" not in html:
                    err("index.html: нет плашки «Демо-режим»")
    print("html checked:", n_html)


def main():
    if not os.path.isdir(ROOT):
        print("нет папки", ROOT)
        return 1
    check_files()
    check_secrets()
    check_html()
    n = sum(len(f) for _, _, f in os.walk(ROOT))
    for w in warns:
        print("WARN:", w)
    if errors:
        print("ERRORS: %d" % len(errors))
        for e in errors[:60]:
            print(" -", e)
        if len(errors) > 60:
            print(" ... и ещё", len(errors) - 60)
        return 1
    print("LINT OK: %d files in %s" % (n, ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
