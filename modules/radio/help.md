**Где это:** плитка «Радио» на /apps (оверлей).

- Интернет-радио: список станций и плейлистов; play/stop/next/prev. Звук воспроизводится **на сервере** через `mpv` (без видео).
- Прослушивание прямо из браузера; станции можно добавлять вручную (URL потока + название).
- API: `GET /api/radio/stations`, `GET /api/radio/playlists`, `GET /api/radio/status`, `POST /api/radio/play|stop|next|prev`.
- Выключенный модуль: плитка скрыта, `/api/radio/*` → 404.
