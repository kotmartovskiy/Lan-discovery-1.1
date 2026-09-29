**Где это:** плитка «Файлы» на /apps (оверлей).

- Двухпанельный файловый менеджер: список, чтение файла, копирование/перемещение, переименование, удаление, создание каталогов.
- Пути абсолютные (с `/`); права — от пользователя, под которым работает сервис панели.
- API: `GET /api/filemanager/list?path=`, `GET /api/filemanager/read?path=`, `POST /api/filemanager/rename|delete|copy|move|mkdir` (JSON).
- Выключенный модуль: плитка скрыта, `/apps/filemanager` и `/api/filemanager` → 404.
