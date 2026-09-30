# -*- coding: utf-8 -*-
"""Unit: hardware abstraction (PHASE 3) — переносимо across платформы.

На Windows/CI (нет /sys) функции возвращают None — это валидный кейс;
на X96/Orange Pi проверяются фактические значения.
"""
import platform as pyplatform

from core import hardware as hw


def test_thermal_zone_path_type():
    p = hw.thermal_zone_path()
    assert p is None or (isinstance(p, str)
                         and p.startswith("/sys/class/thermal/"))


def test_thermal_temp_type():
    t = hw.thermal_temp()
    assert t is None or isinstance(t, float)
    if t is not None:
        assert -50 < t < 200


def test_storage_devices():
    for name in (hw.hdd_device(), hw.emmc_device(), hw.sd_device()):
        if name is not None:
            assert isinstance(name, str) and name
            assert name.startswith(("sd", "mmcblk"))
            assert "boot" not in name


def test_board_model_nonempty():
    m = hw.board_model()
    assert isinstance(m, str) and m.strip()


def test_detect_platform_shape():
    data = hw.detect_platform()
    assert set(data) == {"board", "arch", "system", "emmc", "sd", "hdd",
                         "thermal_zone"}
    assert data["arch"] in ("aarch64", "armv7l", "x86_64", "AMD64") \
        or data["arch"] == pyplatform.machine()
    assert data["system"] in ("Linux", "Windows")


def test_detect_platform_cached():
    assert hw.detect_platform() is hw.detect_platform()
