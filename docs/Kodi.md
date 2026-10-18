# Kodi на X96 Max (автозапуск, Wi-Fi, SDR-радио)

Приставка X96 Max при загрузке сразу открывает Kodi; в Kodi из главного
меню доступны настройки Wi-Fi (выбор сети, ввод пароля) и эфирное
радио через RTL-SDR свисток. Всё содержится в `tools/kodi/` репозитория
и разворачивается **одной командой** на аналогичном устройстве Armbian/
Debian (arm64):

```bash
scp -r tools/kodi root@<ip>:/root/kodi-kit
ssh root@<ip> 'sh /root/kodi-kit/install.sh'
```

Установщик идемпотентен, ставит только недостающее (kodi, ffmpeg,
rtl-sdr, python3) и полностью воспроизводим.

## Что ставит install.sh

| Компонент | Файл | Назначение |
|---|---|---|
| systemd-сервис | `kodi.service` | автозапуск `kodi-standalone` (GBM, без X) от юзера `kot` на `graphical.target` |
| стример | `/usr/local/bin/sdr_radio.py` | `rtl_fm → ffmpeg (aac/adts) → http://:8344/stream` |
| udev | `90-rtlsdr.rules` | доступ к свистку `0666` (номер 90 перебивает `60-librtlsdr0.rules` пакета) |
| группа | `plugdev` | юзер Kodi получает доступ к USB-свистку (страховка) |
| sudo | `sudoers-lan-bridge` | `kot` может вызывать `nmcli` без пароля |
| аддон Wi-Fi | `addon-wifi/plugin.program.wifi-settings` | список сетей NM, ввод пароля, подключение/отключение |
| аддон SDR | `addon-sdr/plugin.program.sdr-radio` | меню частот/модуляций, запуск стрима, воспроизведение в Kodi |
| ярлыки | `favorites.xml` | 📶 Wi-Fi и 📻 SDR Радио в «Избранном» главного меню |

Ключ: `--user <юзер>` (по умолчанию `kot`), `--no-enable` — без автозапуска.

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
