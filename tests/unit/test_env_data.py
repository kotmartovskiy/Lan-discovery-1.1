# -*- coding: utf-8 -*-
"""Unit: чистые функции fetcher'а env_data (ЕГАСМРО: ближайшие пункты, уровни)."""
import importlib.util
import json
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
# в репозитории скрипт в deploy/, на сервере — копия в корне приложения
_SCRIPT = next((p for p in (_ROOT / "deploy" / "env_data.py",
                            _ROOT / "env_data.py") if p.exists()), None)
if _SCRIPT is None:
    pytest.skip("env_data.py not found", allow_module_level=True)
_spec = importlib.util.spec_from_file_location("deploy_env_data", _SCRIPT)
env_data = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(env_data)


def test_haversine_one_degree_lon():
    # экватор: 1° долготы ≈ 111.19 км
    assert abs(env_data.haversine_km(0, 0, 0, 1) - 111.19) < 0.5


def test_haversine_ivanovo_moscow_range():
    d = env_data.haversine_km(57.0, 41.0, 55.7558, 37.6173)
    assert 240 < d < 300  # Иваново–Москва по прямой ≈ 250 км


def test_direction_names():
    assert env_data.direction_name(0) == "С"
    assert env_data.direction_name(90) == "В"
    assert env_data.direction_name(180) == "Ю"
    assert env_data.direction_name(270) == "З"
    assert env_data.direction_name(359) == "С"
    assert env_data.direction_name(135) == "ЮВ"


def test_radiation_level_thresholds():
    assert env_data.radiation_level(None) == "Н/Д"
    assert env_data.radiation_level(0.12) == "Норма"
    assert env_data.radiation_level(0.2) == "Норма"
    assert env_data.radiation_level(0.3) == "Повышенный"
    assert env_data.radiation_level(0.55) == "Высокий"
    assert env_data.radiation_level(1.5) == "Опасный"


def test_nearest_points_sorted_limited_filtered():
    rows = [
        {"name": "Дальний", "value": "0.10", "lat": "60.0", "lng": "45.0",
         "date": "03.10.2026", "tind": 0},
        {"name": "Ближний", "value": "0,13", "lat": "57.1", "lng": "41.1",
         "date": "03.10.2026", "tind": 0},
        {"name": "Средний", "value": "0.12", "lat": "56.5", "lng": "40.5",
         "date": "03.10.2026", "tind": 0},
        {"name": "Не-МЭД", "value": "9.9", "lat": "57.0", "lng": "41.01",
         "date": "03.10.2026", "tind": 1},
        {"name": "Битый", "value": "abc", "lat": "57.0", "lng": "41.02",
         "date": "03.10.2026", "tind": 0},
    ]
    pts = env_data.nearest_points(rows, 57.0, 41.0, 2)

    assert [p["name"] for p in pts] == ["Ближний", "Средний"]
    assert pts[0]["value"] == 0.13  # запятая → точка
    assert pts[0]["dist"] < 30
    assert pts[0]["dir"] in env_data.DIRS
    assert pts[0]["date"] == "03.10.2026"
    assert "lat" in pts[0] and "lng" in pts[0]


def test_nearest_points_empty_input():
    assert env_data.nearest_points([], 57.0, 41.0, 3) == []


def test_load_site_reads_settings(tmp_path, monkeypatch):
    cfg = tmp_path / "settings.json"
    cfg.write_text(json.dumps({"weather": {
        "latitude": 56.0, "longitude": 40.0,
        "region_name": "Шуя", "radiation_points": 5}}),
        encoding="utf-8")
    monkeypatch.setattr(env_data, "SETTINGS", str(cfg))

    lat, lon, name, count = env_data.load_site()
    assert (lat, lon, name, count) == (56.0, 40.0, "Шуя", 5)


def test_load_site_defaults_and_clamp(tmp_path, monkeypatch):
    monkeypatch.setattr(env_data, "SETTINGS",
                        str(tmp_path / "missing.json"))
    assert env_data.load_site() == (57.0, 41.0, "Иваново", 3)

    cfg = tmp_path / "settings.json"
    cfg.write_text(json.dumps({"weather": {
        "latitude": "57.5", "longitude": 41.0,
        "region_name": "Кохма", "radiation_points": 99}}),
        encoding="utf-8")
    monkeypatch.setattr(env_data, "SETTINGS", str(cfg))
    lat, lon, name, count = env_data.load_site()
    assert (lat, lon, name, count) == (57.5, 41.0, "Кохма", 10)
