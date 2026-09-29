**Где это:** плитка «Bluetooth» на /apps (оверлей).

- Статус адаптера (MAC, имя, вкл/выкл), видимость, поиск и подключение устройств (колонки, гарнитуры), управление парами.
- API: `GET /api/bluetooth/status|devices|paired|discovered`, `POST /api/bluetooth/scan|power|connect|disconnect|pair|remove|discoverable|trust`.
- Статус читается из `/sys/class/bluetooth`, управление — через `bluetoothctl`.
- Зависимости модуля: пакет `bluez` (apt), сервис `bluetooth`.
- Выключенный модуль: плитка скрыта, `/apps/bluetooth` и `/api/bluetooth` → 404.
