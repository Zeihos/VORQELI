# Зависимости третьих сторон

VORQELI не является официальным продуктом Flowseal или GeoHide.

- **Flowseal / zapret-discord-youtube 1.10.4**: https://github.com/Flowseal/zapret-discord-youtube . Исходный архив не содержит бинарный движок. При первом подключении приложение скачивает официальный pinned ZIP-релиз и проверяет SHA-256 `291af673bd0238506f9548e0e94ca0abf244000f4c9a06960544fb01c5f97b34` по официальному GitHub Release API. Комплект содержит лицензии Flowseal, bol-van и зависимости WinDivert.
- **Flowseal / tg-ws-proxy v1.11.4**: https://github.com/Flowseal/tg-ws-proxy . Код не включён в исходный ZIP VORQELI, но **встраивается в собранный EXE** из коммита `9f71904e1a4a282fd9e5044bbb71d59f4d30576b`. Copyright © 2026 Flowseal, MIT License. Для корректной поставки нужно сохранить MIT-уведомление и уведомления о зависимостях.
- **GeoHide DNS**: https://geohide.ru/ — отдельный провайдер. VORQELI не владеет сервисом и не распространяет его код.
- **Pillow / pystray** — GUI assets и Windows system tray, со своими независимыми лицензиями.

VORQELI Connect код лицензирован по MIT. Подробная фиксация внешних источников содержится в корневом `NOTICE.md`.
