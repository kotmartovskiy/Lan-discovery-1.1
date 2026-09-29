**Где это:** плитка «Камеры» на /apps (оверлей).

- IP-камеры: добавление/удаление (RTSP-URL), запуск/остановка трансляций, просмотр потока в браузере.
- API: `GET/POST /api/cameras`, `PUT/DELETE /api/cameras/<id>`, `POST /api/cameras/<id>/start|stop`, `POST /api/cameras/start_all|stop_all`, `GET /api/cameras/stream/<id>`.
- Трансляции тянет `ffmpeg` — камеры должны быть доступны с сети сервера.
- Выключенный модуль: плитка скрыта, `/api/cameras` → 404.
