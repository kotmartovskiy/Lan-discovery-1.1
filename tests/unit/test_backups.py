# -*- coding: utf-8 -*-
"""Unit: бэкапы (PHASE 11): фильтр UI-списка не подхватывает config-тары."""
import os

import modules.system_routes as sr


def test_db_backup_list_only_db_files(tmp_path, monkeypatch):
    monkeypatch.setattr(sr, "DB_BACKUP_DIR", str(tmp_path))
    (tmp_path / "devices_20260101-000000.db").write_bytes(b"db1" * 10)
    (tmp_path / "devices_20260102-000000.db").write_bytes(b"db2" * 10)
    (tmp_path / "config_20260101-000000.tar.gz").write_bytes(b"tar" * 10)
    (tmp_path / "unrelated.txt").write_text("x", encoding="utf-8")

    names = [b["name"] for b in sr.db_backup_list()]
    assert names == ["devices_20260102-000000.db",
                     "devices_20260101-000000.db"]
    assert all(n.startswith("devices_") for n in names)


def test_db_backup_list_empty_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(sr, "DB_BACKUP_DIR", str(tmp_path))
    assert sr.db_backup_list() == []


def test_db_backup_list_missing_dir(monkeypatch):
    import tempfile
    monkeypatch.setattr(sr, "DB_BACKUP_DIR",
                        os.path.join(tempfile.gettempdir(),
                                     "no-such-dir-xyz"))
    assert sr.db_backup_list() == []


def test_db_backup_list_fields(tmp_path, monkeypatch):
    monkeypatch.setattr(sr, "DB_BACKUP_DIR", str(tmp_path))
    (tmp_path / "devices_20260101-000000.db").write_bytes(b"z" * 2048)
    b = sr.db_backup_list()[0]
    assert set(b) == {"name", "size", "mtime"}
    assert b["size"] == 2048
    assert sr.db_backup_size_human(b["size"]).endswith("KiB")
