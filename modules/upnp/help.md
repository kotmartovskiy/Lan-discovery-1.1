**Где это:** плитка «UPnP» на /apps (оверлей).

- Управление UPnP-рендерерами (колонки/ТВ): выбор рендера, play/pause/stop/next/prev, громкость, mute; обзор содержимого UPnP-серверов (SOAP Browse).
- API: `GET /api/upnp/renderers|servers|status|browse`, `POST /api/upnp/play|pause|stop|next|prev|volume|mute`.
- Списки пустые — если устройства не отвечают на SSDP-обнаружение в сети.
- Выключенный модуль: плитка скрыта, `/apps/upnp` и `/api/upnp` → 404.
