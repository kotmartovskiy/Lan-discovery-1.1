**Где это:** плитка «Сеть» на /apps (оверлей).

- Утилиты сети: ping, DNS-резолвер, сканер портов, traceroute — по кнопкам интерфейса.
- API: `POST /api/nettools/ping|dns|ports|trace` (JSON: `host`; для ports — ещё `ports`, например `"22,80,443"`).
- Выключенный модуль: плитка скрыта, `/apps/nettools` и `/api/nettools` → 404.
