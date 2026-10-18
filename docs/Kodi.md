# Kodi на X96 Max (автозапуск, Wi-Fi, SDR, ретроигры, ТВ)

Приставка X96 Max при загрузке сразу открывает Kodi; в Kodi из главного
меню (раздел «Избранное») доступны настройки Wi-Fi, эфирное радио через
RTL-SDR свисток, ретроигры (RetroArch) и телевизионный интерфейс PVR
(tvheadend). Всё содержится в `tools/kodi/` репозитория
и разворачивается **одной командой** на аналогичном устройстве Armbian/
Debian (arm64):

```bash
scp -r tools/kodi root@<ip>:/root/kodi-kit
ssh root@<ip> 'sh /root/kodi-kit/install.sh'
```

Установщик идемпотентен, ставит только недостающее (kodi, ffmpeg,
rtl-sdr, python3, retroarch + libretro-ядра) и полностью воспроизводим.

## Что ставит install.sh

| Компонент | Файл | Назначение |
|---|---|---|
| systemd-сервис | `kodi.service` | автозапуск `kodi-standalone` (GBM, без X) от юзера `kot` на `graphical.target` |
| hdmi-watch | `hdmi-watch.service` | при появлении HDMI-дисплея (HPD edge) сам перезапускает kodi |
| стример | `/usr/local/bin/sdr_radio.py` | `rtl_fm → ffmpeg (aac/adts) → http://:8344/stream` |
| udev | `90-rtlsdr.rules` | доступ к свистку `0666` (номер 90 перебивает `60-librtlsdr0.rules` пакета) |
| группа | `plugdev` | юзер Kodi получает доступ к USB-свистку (страховка) |
| sudo | `sudoers-lan-bridge` | `kot` может вызывать `nmcli` без пароля |
| аддон Wi-Fi | `addon-wifi/plugin.program.wifi-settings` | список сетей NM, ввод пароля, подключение/отключение |
| аддон SDR | `addon-sdr/plugin.program.sdr-radio` | меню частот/модуляций, запуск стрима, воспроизведение в Kodi |
| аддон ретро | `addon-retro/plugin.program.retro-games` | выбор системы (NES/SNES/GB/GBA/Genesis/PSX) → RetroArch |
| стример ретро | `retro-games.sh` | kodi stop → `retroarch -L core` → kodi start (GBM не конфликтует) |
| PVR-клиент | `pvr-hts-settings.xml` | instance tvheadend.htsp: 127.0.0.1:9981, user/pass kodi/kodi |
| PVR включение | `enable-pvr.sh` | `UPDATE installed SET enabled=1` в Addons*.db (после 1-го старта kodi) |
| tvheadend-доступ | `tvh-access.sh` | юзер kodi в tvheadend: `accesscontrol/` + `passwd/` (пароль kodi) |
| web-управление | `advancedsettings.xml`, `settings-webserver.xml` | JSON-RPC TCP 9090 / HTTP 8085 (8080 занят панелью) |
| ярлыки | `favorites.xml` | 📶 Wi-Fi, 📻 SDR/FM, 🎮 Ретроигры, 📺 ТВ в «Избранном» |

Ключ: `--user <юзер>` (по умолчанию `kot`), `--no-enable` — без автозапуска.

## Где всё искать в Kodi

В главном меню Estuary открой **«Избранное»** — там четыре ярлыка:
📶 Wi-Fi, 📻 SDR Радио (FM/AM), 🎮 Ретроигры, 📺 ТВ (tvheadend).
Те же аддоны видны в разделе «Программы» → «Установленные дополнения».

## Ретроигры

`Избранное → 🎮 Ретроигры`: список систем (NES Nestopia, SNES Snes9x,
Game Boy Gambatte, GBA mGBA, Genesis Plus GX, PlayStation Beetle PSX) +
«RetroArch: главное меню». Выбор → `retro-games.sh` останавливает kodi,
запускает RetroArch fullscreen с ядром, после выхода возвращает kodi
(оба — GBM, DRM-конкуренция исключена). ROM'ы складывать в
`/home/kot/roms` (в самом RetroArch — Load Content). Ядра ставит
install.sh (libretro-*).

## ТВ (tvheadend)

`Избранное → 📺 ТВ` открывает PVR-интерфейс tvheadend (pvr.hts
подключается к `127.0.0.1:9981` под пользователем kodi/kodi — доступ
создаёт `tvh-access.sh`: ACL в `accesscontrol/`, пароль в `passwd/`).
Каналов нет, пока к tvheadend не подключён DVB-тюнер или IPTV-источник —
интерфейс ТВ (guide/каналы/записи) при этом уже работает. Сам tvheadend
на X96 собран из исходников (`/usr/local/bin/tvheadend -c
/usr/local/share/tvheadend`), kodi-kit его не ставит, а только
настраивает доступ и клиент.

Если kodi запускался впервые (install только что): pvr.hts включается
`enable-pvr.sh` (и install.sh делает это сам, если БД аддонов уже есть).

## Монитор был выключен при загрузке?

На Amlogic/GBM при старте с отключённым дисплее HDMI «залечивает» HPD и
kodi не подхватывает его появление — картинки нет до reboot. Поэтому
в набор входит `hdmi-watch.service` (каждые 3 с читает
`/sys/class/drm/card0-HDMI-A-1/status`): при переходе
`disconnected → connected` автоматически делает `systemctl restart kodi`.
Включаешь монитор/ТВ → через 1–5 с картинка появляется сама, приставку
перезагружать не нужно.

## Wi-Fi из Kodi

`Избранное → 📶 Wi-Fi` (или Программы → Wi-Fi Settings):

- список сетей `nmcli dev wifi list` (активная, сигнал, 🔒),
- выбор сети → ввод пароля (клавиатура Kodi) → `nmcli dev wifi connect`,
- отключение текущего подключения, обновление списка.

Пароль хранит NetworkManager (системный), в аддоне не хранится.

## SDR-радио из Kodi

`Избранное → 📻 SDR Радио`: пресеты FM 88-108 (WBFM), авиа 118-137 AM,
ДВМ 136-174, УКВ 400-470, ручной ввод частоты и модуляции (WBFM/AM/NFM/
USB/LSB), остановка, просмотр лога.

Как работает: `sdr_radio.py` запускает `rtl_fm` (свисток, 48 кГц PCM) →
`ffmpeg` кодирует в AAC (ADTS, 128k) → раздаёт по `http://<box>:8344/stream`
→ Kodi проигрывает поток обычным плеером. Один процесс на частоту;
остановка — SIGTERM (pid: `/tmp/sdr_radio.pid`, лог: `/tmp/sdr_radio.log`).

Важно: свисток физически один — если им занят OpenWebRX (открытая вкладка
приёмника) или ADS-B, `rtl_fm` получит «device busy». Освободить: закрыть
приёмник OpenWebRX (он отпускает свисток после отключения клиентов) или
`systemctl stop dump1090-mutability rtl_tcp` (по необходимости).

## Проверка на устройстве

```bash
systemctl status kodi                      # активен, kodi.bin под kot
sudo -u kot sudo -n nmcli dev wifi list    # Wi-Fi без пароля sudo
sudo -u kot /usr/local/bin/sdr_radio.py --freq 98000000 --mod wfm &
curl -s --max-time 4 http://127.0.0.1:8344/stream -o /tmp/t.aac
file /tmp/t.aac                            # MPEG ADTS, AAC
kill $(cat /tmp/sdr_radio.pid)
```
