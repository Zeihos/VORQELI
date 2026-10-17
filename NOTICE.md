# Third-party attributions and build manifest

**VORQELI Connect is NOT an official Flowseal / GeoHide application.**

* `Flowseal/zapret-discord-youtube` — MIT licensed, release `1.10.3`:
  https://github.com/Flowseal/zapret-discord-youtube/releases/tag/1.10.3
  bundled archive SHA-256:
  `244314ae1c24538a0d751601da8e0c925c843371eec4456eb15f14c4fd6b7058`.
  The upstream release includes `LICENSE.txt`, which remains next to the downloaded binaries.
  Underlying components may include WinDivert and other third-party licenses; refer to upstream binary bundle notices.

* `Flowseal/tg-ws-proxy` — MIT licensed, pinned commit
  `307a384ab7f522e34bb1a045884d0bd90f40bee5` (release v1.11.2):
  https://github.com/Flowseal/tg-ws-proxy
  Licensing details: https://github.com/Flowseal/tg-ws-proxy/blob/main/LICENSE
  This software is included during the Windows build. Copyright (c) 2026 Flowseal.

* **GeoHide DNS** — operated by independent third party:
  https://geohide.ru/ . Not included as software; VORQELI only changes Windows
  DNS settings to addresses published for the service.

* `Pillow` — Python Imaging Library fork, HPND license.
* `pystray` — tray integration, LGPLv3 or compatible terms depending on bundled version.
* `PyInstaller` — used only to build the executable; see its license and exception.

All third-party components retain their own copyright and license obligations.
For public redistribution of packaged applications, verify and include the exact
license notices from the selected dependency versions and their transitive packages.
