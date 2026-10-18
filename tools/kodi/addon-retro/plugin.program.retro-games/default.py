#!/usr/bin/env python3
# Ретроигры: запуск RetroArch с libretro-ядром (kodi останавливается, возвращается после выхода).
import os
import subprocess
import xbmcgui

LAUNCHER = "/usr/local/bin/retro-games.sh"
CORES = "/usr/lib/aarch64-linux-gnu/libretro"
ROMS = os.path.expanduser("~/roms")

PRESETS = [
    ("NES (Nestopia)", "nestopia_libretro.so"),
    ("Super NES (Snes9x)", "snes9x_libretro.so"),
    ("Game Boy / GBC (Gambatte)", "gambatte_libretro.so"),
    ("Game Boy Advance (mGBA)", "mgba_libretro.so"),
    ("Genesis / Mega Drive (Genesis Plus GX)", "genesisplusgx_libretro.so"),
    ("PlayStation (Beetle PSX)", "mednafen_psx_libretro.so"),
]


def main():
    labels = ["🎮 " + name for name, _ in PRESETS]
    labels.append("🕹 RetroArch: главное меню / файлы")
    idx = xbmcgui.Dialog().select("Ретроигры (RetroArch)", labels)
    if idx < 0:
        return

    if idx >= len(PRESETS):
        core = ""
    else:
        core = os.path.join(CORES, PRESETS[idx][1])
        if not os.path.isfile(core):
            xbmcgui.Dialog().ok("Ретроигры", "Ядро не найдено:\n%s" % core)
            return

    subprocess.Popen(["/bin/sh", LAUNCHER, core],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True)
    xbmcgui.Dialog().notification(
        "Ретроигры",
        "RetroArch запускается — Kodi вернётся после выхода",
        xbmcgui.NOTIFICATION_INFO, 6000)


if __name__ == "__main__":
    main()
