# Зависимости третьих сторон

VORQELI не является официальным продуктом Flowseal или GeoHide.

- **Flowseal / zapret-discord-youtube 1.10.3**: https://github.com/Flowseal/zapret-discord-youtube . Исходный архив не содержит бинарный движок. При первом подключении приложение скачивает официальный pinned ZIP-релиз и проверяет SHA-256. Комплект содержит лицензии Flowseal, bol-van и зависимости WinDivert.
- **Flowseal / tg-ws-proxy v1.11.2**: https://github.com/Flowseal/tg-ws-proxy . Код не включён в исходный ZIP VORQELI, но **встраивается в собранный EXE** из коммита `307a384ab7f522e34bb1a045884d0bd90f40bee5`. Copyright © 2026 Flowseal, MIT License. Для корректной поставки нужно сохранить MIT-уведомление и уведомления о зависимостях.
- **GeoHide DNS**: https://geohide.ru/ — отдельный провайдер. VORQELI не владеет сервисом и не распространяет его код.
- **Pillow / pystray** — GUI assets и Windows system tray, со своими независимыми лицензиями.

VORQELI Connect код лицензирован по MIT. Подробная фиксация внешних источников содержится в корневом `NOTICE.md`.
