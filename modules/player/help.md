**Где это:** плитка «Плеер» на /apps (оверлей).

- Плеер медиафайлов сервера: обзор каталогов, плейлисты (сохранение/удаление), play/stop/next/prev, случайный порядок. Воспроизведение — через `mpv`.
- API: `GET /api/player/browse`, `GET /api/player/playlists`, `GET /api/player/status`, `POST /api/player/play|stop|next|prev|random|playlist`.
- Выключенный модуль: плитка скрыта, `/api/player/*` → 404.
