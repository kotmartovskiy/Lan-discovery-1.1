# -*- coding: utf-8 -*-
"""Unit: sync_check (PHASE 16 №61) — дрейф-контроль repo ↔ сервер."""
import hashlib
import pathlib
import subprocess
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "tools"))

import sync_check as sc  # noqa: E402


def _m(b):
    return hashlib.md5(b).hexdigest()


def test_parse_filelist_three_columns():
    text = "%s  %s  modules/app.py\n\n%s  %s  app.py\n" % (
        _m(b"x"), _m(b"x"), _m(b"y"), _m(b"y"))
    fl, errs = sc.parse_filelist(text)
    assert errs == []
    assert fl["modules/app.py"] == (_m(b"x"), _m(b"x"))
    assert "app.py" in fl


def test_parse_filelist_legacy_two_columns():
    fl, errs = sc.parse_filelist("%s  app.py\n" % _m(b"x"))
    assert fl["app.py"] == (_m(b"x"), None)
    assert errs == []


def test_parse_filelist_errors_collected():
    fl, errs = sc.parse_filelist("ERR-no such file  -  modules/x.py\n")
    # ошибка читается в отчёт, но файл не пропадает из сверки
    assert len(errs) == 1
    assert fl["modules/x.py"][0].startswith("ERR-")
    assert fl["modules/x.py"][1] is None
    # ERR в старом формате (2 колонки) не попадает в filelist
    fl2, errs2 = sc.parse_filelist("ERR-no such file  modules/x.py\n")
    assert fl2 == {} and len(errs2) == 1


def test_skipped_rules():
    assert sc.skipped("docs/API.md")
    assert sc.skipped("AGENTS.md")
    assert sc.skipped(".github/workflows/ci.yml")
    assert sc.skipped("ROADMAP.md")
    assert sc.skipped("deploy/backup-db.timer")
    assert sc.skipped("deploy.py")
    assert sc.skipped("remote_edit.py")
    assert sc.skipped("tools/demo_lint.py")
    assert not sc.skipped("modules/app.py")
    assert not sc.skipped("templates/base.html")
    assert not sc.skipped("tools/make_demo.py")
    # --include-docs снимает только docs/
    assert not sc.skipped("docs/API.md", include_docs=True)
    assert sc.skipped("AGENTS.md", include_docs=True)
    assert sc.skipped("deploy.py", include_docs=True)


def test_compare_exact_eol_content():
    srv = {
        "same.py": (_m(b"same"), _m(b"same")),
        "eol.py": (_m(b"a\nb\n"), _m(b"a\nb\n")),
        "diff.py": (_m(b"old"), _m(b"old")),
    }
    local = {
        "same.py": b"same",
        "eol.py": b"a\r\nb\r\n",      # локально CRLF, на сервере LF
        "diff.py": b"new",
        "only_git.py": b"x",
    }
    rep = sc.compare(srv, local)
    assert rep["exact"] == ["same.py"]
    assert rep["eol"] == ["eol.py"]
    assert rep["content"] == ["diff.py"]
    assert rep["only_local"] == ["only_git.py"]
    assert rep["only_remote"] == []


def test_compare_only_remote_and_legacy_no_eol_claim():
    srv = {"srv_only.py": (_m(b"z"), None)}
    local = {"l.py": b"a\r\nb"}
    rep = sc.compare(srv, local)
    assert rep["only_remote"] == ["srv_only.py"]
    # legacy (norm=None): CRLF-разница не может быть доказана → content
    assert rep["content"] == ["l.py"] or rep["only_local"] == ["l.py"]
    assert rep["only_local"] == ["l.py"]


def test_compare_skips_docs_unless_asked():
    srv = {"docs/API.md": (_m(b"old"), _m(b"old"))}
    local = {"docs/API.md": b"new", "app.py": b"ok"}
    rep = sc.compare(srv, local)
    assert "docs/API.md" not in rep["content"]   # skipped → просто отсутствует
    rep2 = sc.compare(srv, local, include_docs=True)
    assert rep2["content"] == ["docs/API.md"]


def test_local_snapshot_git(tmp_path):
    subprocess.check_call(["git", "init", "-q"], cwd=str(tmp_path))
    (tmp_path / "app.py").write_bytes(b"print(1)\n")
    (tmp_path / "README.md").write_text("skip", encoding="utf-8")
    subprocess.check_call(["git", "add", "app.py", "README.md"], cwd=str(tmp_path))
    snap = sc.local_snapshot(tmp_path)
    assert set(snap) == {"app.py"}
    snap2 = sc.local_snapshot(tmp_path, include_docs=True)
    assert "README.md" in snap2


def test_main_filelist_ok_and_drift(tmp_path, capsys):
    repo = tmp_path / "r"
    repo.mkdir()
    subprocess.check_call(["git", "init", "-q"], cwd=str(repo))
    (repo / "app.py").write_bytes(b"hello\n")
    subprocess.check_call(["git", "add", "app.py"], cwd=str(repo))
    # сервер: тот же файл → exit 0
    fl = tmp_path / "fl.txt"
    fl.write_text("%s  %s  app.py\n" % (_m(b"hello\n"), _m(b"hello\n")),
                  encoding="utf-8")
    rc = sc.main(["--filelist", str(fl), "--repo", str(repo)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "exact=1" in out and "content_diff=0" in out
    # сервер: другой контент → exit 1
    fl.write_text("%s  %s  app.py\n" % (_m(b"other\n"), _m(b"other\n")),
                  encoding="utf-8")
    rc = sc.main(["--filelist", str(fl), "--repo", str(repo)])
    assert rc == 1
    assert "CONTENT DIFF" in capsys.readouterr().out


def test_main_missing_filelist(tmp_path):
    rc = sc.main(["--filelist", str(tmp_path / "nope.txt"),
                  "--repo", str(tmp_path)])
    assert rc == 2
