#!/usr/bin/env python3
# Ретроигры: запуск RetroArch с libretro-ядром (kodi останавливается, возвращается после выхода).
import os
import subprocess
import xbmcgui

LAUNCHER = "/usr/local/bin/retro-games.sh"
CORES = "/usr/lib/aarch64-linux-gnu/libretro"
ROMS = os.path.expanduser("~/roms")

PRESETS = [
    ("NES (Nestopia)", "nestopia_libretro.so", [".nes"]),
    ("Super NES (Snes9x)", "snes9x_libretro.so", [".sfc", ".smc"]),
    ("Game Boy / GBC (Gambatte)", "gambatte_libretro.so", [".gb", ".gbc"]),
    ("Game Boy Advance (mGBA)", "mgba_libretro.so", [".gba"]),
    ("Genesis / Mega Drive", "genesis_plus_gx_libretro.so", [".md", ".gen", ".bin", ".zip"]),
    ("PlayStation (Beetle PSX)", "mednafen_psx_libretro.so", [".bin", ".cue", ".chd", ".pbp", ".img"]),
]


def find_rom(exts):
    if not os.path.isdir(ROMS):
        return None
    for name in sorted(os.listdir(ROMS)):
        if os.path.splitext(name)[1].lower() in exts:
            return os.path.join(ROMS, name)
    return None


def main():
    labels = ["🎮 " + name for name, _, _ in PRESETS]
    labels.append("🕹 RetroArch: главное меню / Load Content")
    idx = xbmcgui.Dialog().select("Ретроигры (RetroArch)", labels)
    if idx < 0:
        return

    if idx >= len(PRESETS):
        subprocess.Popen(["/bin/sh", LAUNCHER, ""],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
        xbmcgui.Dialog().notification(
            "Ретроигры", "Меню RetroArch — kodi вернётся после выхода",
            xbmcgui.NOTIFICATION_INFO, 5000)
        return

    name, core_name, exts = PRESETS[idx]
    core = os.path.join(CORES, core_name)
    if not os.path.isfile(core):
        xbmcgui.Dialog().ok("Ретроигры", "Ядро не найдено:\n%s" % core)
        return

    rom = find_rom(exts)
    if rom:
        subprocess.Popen(["/bin/sh", LAUNCHER, core, rom],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
        xbmcgui.Dialog().notification(
            "Ретроигры", "Запуск: %s — kodi вернётся после выхода" % os.path.basename(rom),
            xbmcgui.NOTIFICATION_INFO, 5000)
    else:
        subprocess.Popen(["/bin/sh", LAUNCHER, ""],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
        xbmcgui.Dialog().ok(
            "Ретроигры",
            "В папке %s нет файлов %s (ROM для %s).\n\n"
            "Скопируй ROM-файлы в эту папку и запусти снова.\n"
            "Сейчас откроется меню RetroArch — там можно Load Content вручную."
            % (ROMS, "/".join(exts), name))


if __name__ == "__main__":
    main()
