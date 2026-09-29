# IPTV-плейлисты

Подсистема скачивает внешние M3U-плейлисты (по расписанию — systemd-таймером либо
вручную из панели) и кладёт их туда, откуда их читает плеер/стример.

> ⚠️ **Статус на X96 Max (с 28.09.2026):** скрипты `update-iptv*.sh` и юниты
> `update-iptv.service`/`update-iptv.timer` остались на прежнем хосте (Orange Pi)
> и на новый хост **не перенесены** — `/usr/local/sbin/` содержит только
> `backup-db.sh`. До их установки кнопки «Обновить» в панели отвечают
> «unit not found», статусы в `iptv-update-status.json` — исторические (сентябрьские).
> Файлы плейлистов в `/srv/media/IPTV/` и конфиг при этом на месте.

## Где что лежит

| Элемент | Путь |
|---|---|
| Список плейлистов | `/etc/lan-discovery/iptv-playlists.json` |
| Каталог с файлами | `/srv/media/IPTV/<file>` (владелец `kot:kot`, права `664`) |
| Статус каждого плейлиста | `/etc/lan-discovery/iptv-update-status.json` (по индексу: `status`, `time`, `exit_code`) |
| Полное обновление | `/usr/local/sbin/update-iptv.sh` *(на X96 не установлен)* |
| Обновление одного | `/usr/local/sbin/update-iptv-one.sh` + `update-iptv-one-worker.sh` *(на X96 не установлены)* |
| systemd | `update-iptv.service` (oneshot) + `update-iptv.timer` (ежедневно в **04:15**, `Persistent=true`) *(на X96 не установлены)* |

## Формат конфига

```json
[
  {
    "name": "Название",
    "url": "http://example.com/playlist.m3u",
    "file": "playlist.m3u",
    "enabled": true
  }
]
```

`name/url/file` читаются скриптом как TSV (табуляция), поэтому табуляции в значениях заменяются на пробелы; `enabled: false` — плейлист пропускается.

## Логика `update-iptv.sh`

1. Читает конфиг через встроенный `python3` (JSON → `name\turl\tfile\tenabled`).
2. Для каждого включённого плейлиста: `curl -fL --connect-timeout 15 --max-time 120` во временный файл `.tmp`.
3. Проверки перед подменой:
   - файл не пустой;
   - **не HTML** — `head -c 512 | grep -qiE '<(!doctype|html)'` (ловит страницы-заглушки и редиректы на главную).
4. Успешный файл перемещается на место, `chown kot:kot`, `chmod 664`, `sync`.
5. Итог: `=== IPTV UPDATE OK ===` (exit 0) либо `=== IPTV UPDATE WITH ERRORS ===`.

## Как статус виден в панели

`modules/system_routes.py → iptv_update_status()`:

- `service_state("update-iptv.service") == "active"` → **«выполняется»**;
- иначе разбирает последние 50 строк `journalctl -u update-iptv.service` и берёт последнюю строку `=== IPTV UPDATE OK: <дата>` → **«● OK, 27.09.2026 17:47:49»**;
- если не найдено — **«ОШИБКА»**.

Состояние «ОШИБКА» на главной почти всегда означает, что **ночной запуск в 04:15 упал** (нет сети / источник недоступен), а не то, что панель сломана. На X96 Max юнита нет вовсе — статус не «выполняется» и панель покажет ошибку до переустановки скриптов.

## Как обновить вручную

```bash
# все плейлисты (требует установленного update-iptv.service)
systemctl start update-iptv.service
journalctl -u update-iptv.service -n 60 --no-pager

# один плейлист (так делает кнопка в панели; требует update-iptv-one-worker.sh)
/usr/local/sbin/update-iptv-one.sh <index>
```

Из интерфейса: раздел «Система» → IPTV — кнопки «Добавить», «Обновить», «Вкл/выкл», «Удалить» (роуты `/system/iptv/*`, см. [Модули](https://github.com/kotmartovskiy/Lan-discovery-ARM/wiki/Модули)).

## Известные проблемы источников

| Симптом | Причина | Решение |
|---|---|---|
| `curl: (7) Failed to connect to ... port 80` | Источник лежал в момент ночного запуска (например, `radio.pervii.com`) | Запустить обновление вручную, когда источник ожил |
| Скачалась HTML-страница вместо M3U | Домен отдаёт главную/редирект (например, `dmi3y-tv6.ru` → `dmi3y-tv.online`) | Исправить URL в конфиге; скрипт теперь отбрасывает HTML и не портит файл |
| Плейлист пустой (`ERROR: downloaded playlist is empty`) | Источник вернул 200 и ноль байт | Проверить URL руками: `curl -sIL <url>` |

Пример исправленной записи (регион Иваново):

```json
{ "name": "ivanovo", "url": "http://dmi3y-tv.online/iptv/region/ZABAVA_IVAN.m3u", "file": "ivanovo.m3u", "enabled": true }
```

## Проверка результата

```bash
head -3 /srv/media/IPTV/*.m3u        # везде должен быть #EXTM3U
ls -l /srv/media/IPTV
python3 -c "import json;print(json.load(open('/etc/lan-discovery/iptv-update-status.json')))"
```
