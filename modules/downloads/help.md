**Где это:** плитка «Загрузки» на /apps (оверлей).

- Веб-обёртка над Transmission: список торрентов, добавление по URL/файл-маршруту, старт/стоп/удаление, очередь.
- Файлы качаются в `/srv/downloads` (демон `transmission-daemon`).
- API: `GET /api/transmission/torrents`, `POST /api/transmission/add|action|queue` (JSON).
- Выключенный модуль: плитка скрыта, `/apps/downloads` и `/api/transmission` → 404.
