"""Санитайзинг docs/ для публичного репозитория Lan-discovery-docs.

Читает <repo>/docs/*.md, вычищает чувствительные данные (рабочие IP,
пароли, системные пользователи), ссылки на wiki приватного репозитория
меняет на относительные, пишет результат в temp-каталог docs-public
(плюс README.md = Home.md). Затем: git init + push в публичный репо.

Проверка: regex по 192.168.3.*, 1234, kot:kot, /wiki/ — должно быть 0.
"""
import pathlib
import re
import shutil

REPO = pathlib.Path(__file__).resolve().parents[1]
SRC = REPO / "docs"
DST = pathlib.Path(r"C:\Users\Lenovo\AppData\Local\Temp\opencode\docs-public")

DST.mkdir(parents=True, exist_ok=True)
for p in DST.iterdir():
    if p.name == ".git":          # remote/ветка сохраняются для push
        continue
    if p.is_dir():
        shutil.rmtree(p)
    else:
        p.unlink()

REPL = [
    ("192.168.3.234", "192.168.1.10"),
    ("192.168.3.235", "192.168.1.11"),
    ("192.168.3.1", "192.168.1.1"),
    ("`192.168.3.7`", "`192.168.1.20`"),
    ("`192.168.3.236`", "`192.168.1.21`"),
    ("`192.168.3.239`", "`192.168.1.22`"),
    ("`192.168.3.51`", "`192.168.1.30`"),
    ("работать по `.235`", "работать по IP WiFi-точки доступа"),
    ("(пароль: 1234)", "(пароль — свой, заданный при установке)"),
    ("пароль `1234`", "пароль — свой"),
    ("(пароль 1234)", "(пароль — свой)"),
    ("kot:kot", "<пользователь>:<группа>"),
]

WIKI = "https://github.com/kotmartovskiy/Lan-discovery-ARM/wiki/"
PAGES = [
    "Полезные-команды", "SD-клонирование", "Архитектура", "Установка",
    "Модули", "Погода", "IPTV", "Home",
]


def sanitize(text: str) -> str:
    for old, new in REPL:
        text = text.replace(old, new)
    for page in PAGES:
        text = text.replace(WIKI + page, page + ".md")
    text = text.replace(
        "- **Репозиторий:** https://github.com/kotmartovskiy/Lan-discovery-ARM\n",
        "- **Исходный код:** в закрытом репозитории проекта\n",
    )
    return text.replace("wiki: `/wiki`.", "документация: этот репозиторий.")


for f in sorted(SRC.glob("*.md")):
    text = sanitize(f.read_text(encoding="utf-8"))
    name = "Оглавление.md" if f.name == "_Sidebar.md" else f.name
    (DST / name).write_text(text, encoding="utf-8", newline="\n")

(DST / "README.md").write_text(
    (DST / "Home.md").read_text(encoding="utf-8"), encoding="utf-8", newline="\n"
)

leaks = []
for f in DST.glob("*.md"):
    t = f.read_text(encoding="utf-8")
    for pat in (r"192\.168\.3\.", r"\b1234\b", r"kot:kot", r"/wiki/"):
        for m in re.finditer(pat, t):
            line = t[: m.start()].count("\n") + 1
            leaks.append(f"{f.name}:{line}: {t.splitlines()[line - 1].strip()[:100]}")

print(f"files: {len(list(DST.glob('*.md')))} -> {DST}")
print(f"leaks: {len(leaks)}")
for l in leaks:
    print("  ", l)
raise SystemExit(1 if leaks else 0)
