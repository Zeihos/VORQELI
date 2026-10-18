## 0.35.0 — Flowseal ALT 1–13 и HOSTS

- Приоритетный последовательный выбор ALT2, ALT6, ALT11… и ручное меню ALT1–ALT13.
- Безопасный разбор параметров официальных ALT BAT без их исполнения.
- HOSTS: 241 дополнительных доменов с явным подтверждением и удаляемым блоком.
- Проверка целостности ALT-шаблонов, новые офлайн-тесты и улучшенные статусы.

## v0.34.0 — Network adapter identity protection (2026-10-18)

- Persist stable `InterfaceGuid` in every new GeoHide IPv4 DNS backup.
- Verify GUID before enabling, restoring or resuming DNS settings, protecting
  against Windows reusing an interface index for a different adapter.
- Add a second GUID verification inside the same PowerShell invocation as
  `Set-DnsClientServerAddress`, reducing the index-reassignment race.
- Preserve unresolved backups on changed/renamed/replaced adapters; a rename
  is safe when GUID is unchanged. Historic GUID-less backups use a conservative
  adapter-alias compatibility check and never gain a fake GUID during rewrites.
- Strengthen DHCP rollback verification: manual DNS must be empty and the
  effective server list must not still match GeoHide (including first-server-only).
- New unit regressions and a read-only Windows CI snapshot smoke test.
- Networking still requires real Windows acceptance; this is not proof of
  encrypted DoH, successful DPI bypass, or correct driver behavior.

## v0.33.0 — Fail-safe OFF persistence (2026-10-18)

- Added an independent, durable `settings.json.off-intent` marker. It is created and fsynced **before** an OFF-settings write and kept while OFF is intended. A stale or partially written `settings.json` can no longer silently re-enable the application after a reboot if the marker was committed.
- Intentional ON: persist settings first, then remove the OFF marker. Interrupted ON writes therefore also remain OFF after restart (safe conservative recovery).
- `--doctor` includes `explicit_off_guard` (boolean only; never secrets or paths).
- New offline failure-injection tests simulate interrupted ON/OFF writes, corrupted settings, backup recovery, a read-only marker path and broken symlinks. Windows CI also runs an isolated temporary-directory intent smoke test without touching networking or real user preferences.
- This is a defence against interrupted settings writes, **not** a promise of OS-level durability after storage hardware failure or a replacement privileged account. Full Windows reboot acceptance is still required.

## v0.32.0 — Windows installer lifecycle & build inventory hardening (2026-10-18)

- Removed an uninstall false-positive: `--uninstall-cleanup` independently
  checks that Windows has no remaining HKCU Run / scheduled-task registration
  after asking for autostart removal. An unknown/conflicting registration fails
  closed rather than allowing Inno Setup to delete the executable.
- Extended Windows CI with an in-place reinstallation, executable SHA-256
  comparison, refusal to uninstall while the named GUI mutex is held, and
  a final successful removal after releasing the mutex.
- Strengthened source manifest verification: detects extra unmanifested source
  files, Windows case-insensitive filename collisions, path/symlink redirects,
  invalid digest metadata, and changed/missing original files. CI uses this
  check BEFORE dependency installation and PyInstaller packaging.
- Added offline regression tests for the above safety checks and release gate
  documentation in `docs/RELEASE_CANDIDATE_GATE_V32.md`.
- No claim of verified Windows networking, code signing, or public v1.0 release.

## v0.31.0 — Installer integrity and GitHub recovery (2026-10-18)

- Reject download directories containing symlinks at **any parent level**, not only at the last directory; reject regular files in parent directory positions. This prevents redirecting verified installers outside the intended local folder.
- New offline regression tests cover nested symlinks, non-directory path components and reuse of validated downloads.
- Added a standard-library `scripts/verify_build_manifest.py` source-integrity check in GitHub Actions. This detects incomplete or changed uploads before expensive Windows packaging. The manifest is **not a digital signature** and cannot authenticate an untrusted repository.
- Version consistency updated in package, app, Inno Setup, and Windows build artifact.
- **Release blocked** pending restored GitHub repository, successful Windows CI run, real DPI + Telegram + GeoHide connectivity, reboot, installer, and signed binaries.

## v0.30.0 — Release Candidate Hardening (2026-10-18)

- Hardened GitHub release handling: API redirects forbidden; installer redirects restricted to trusted GitHub CDN over HTTPS, max 3 hops.
- Installer publication is now atomic without overwriting an existing file: hard link to verified temporary download rather than `os.replace`.
- Symlinked update folders and pre-existing symlinked installers are rejected, fail-closed behavior on unsupported file systems.
- Added `scripts/windows_release_gate.ps1`: manual **read-only** SHA-256 and pinned Authenticode signer verification; intentionally blocks unsigned releases.
- Added offline regression tests covering redirect hijack, URL confusion, race-to-replace attacks and symlinks.
- Added `docs/RELEASE_CANDIDATE_GATE_V30.md` for signing and Windows P0 acceptance criteria.
- **Not yet stable:** Windows EXE, installer, signing, DPI+Telegram+GeoHide, DoH traffic, reboot recovery have not been validated end-to-end.

# VORQELI Connect — изменения

## v0.29.0 — проверка обновлений (Development Preview)

- Кнопка проверки только официального GitHub Release, без фонового сетевого опроса.
- Подтверждаемая загрузка установщика с обязательной проверкой метаданных SHA-256, размера, URL и номера версии.
- Частичные и изменённые загрузки удаляются; никаких автоматических запусков, UAC или DNS-операций.
- Операции в фоновых потоках Tk; чёткие сообщения об отсутствии релиза или проверочной суммы.
- Более 45 новых offline-тестов безопасности, включая отклонение поддельных URL и разницу SHA-256.
- Известное ограничение: контрольная сумма из GitHub не обеспечивает подлинность издателя; обязательны цифровая подпись и реальные Windows-тесты перед 1.0.

## v0.28.0 — Final UI: keyboard and compact screens (development preview)

- Tab / Shift+Tab, Enter / Space, стрелки Left/Right для Canvas-кнопок с видимой рамкой фокуса; недоступные кнопки пропускаются.
- Автоматическая прокрутка к фокусу, вертикальная и горизонтальная полосы прокрутки для маленьких/высоко масштабированных окон Windows.
- На экране «Настройки» убрано перекрытие нижней подписи и управления GeoHide DoH.
- Best-effort поддержка темной системной рамки и Mica главного окна через DWM Windows 11; внутренняя стеклянная сцена остаётся Pillow, не нативный Acrylic.
- Добавлено 29 регрессионных тестов и отдельный Tk GUI smoke-тест компактного окна.
- Совместная работа компонентов на Windows 10/11 и качество DWM-эффектов ещё не проверены на реальном устройстве.

## 0.27.0 — GeoHide DoH: добровольный системный шифрованный DNS (Development Preview)

- Добавлен отдельный режим `dns_mode=plain|doh` с безопасной проверкой значений; прежний IPv4-профиль остаётся значением по умолчанию.
- Новый модуль `geohide_doh.py`: системный Windows DoH через PowerShell DnsClient с фиксированным официальным HTTPS-шаблоном GeoHide. DoH не включается на неподдерживаемой системе и **не откатывается автоматически на UDP**.
- Проверяются существующие DoH-записи: чужие/отличающиеся конфигурации не изменяются. Новые глобальные записи журналируются **до создания**, а при отключении удаляются только при точном совпадении профиля.
- Двухэтапное восстановление: сначала DNS сетевых адаптеров, затем созданные VORQELI глобальные DoH-сопоставления. При ошибках журналы сохраняются.
- Добавлена кнопка выбора транспорта GeoHide в тёмных глянцевых настройках; переключать транспорт во время активного соединения нельзя.
- `--doctor` и отчёт поддержки показывают только безопасное имя транспорта `plain|doh` и наличие журнала восстановления, но не адреса и пользовательские параметры.
- CI выполняет только *чтение* поддержки нативных Windows DoH-команд — без изменения сети. Добавлены регрессионные тесты и руководство `docs/GEOHIDE_DOH_V27.md`.
- **Локально 271 тест прошёл**, проверены пять разделов интерфейса и read-only диагностика. **Требуется реальное тестирование Windows 11**: настройка глобальных DoH-сопоставлений сама по себе ещё не доказывает шифрование DNS-трафика.


## 0.26.0 — Smart DPI: ограниченный автоматический подбор (Development Preview)

- Добавлен добровольный режим **АВТО** в настройках DPI; прежний выбор FAKE остался стандартным.
- Автоматическая последовательность FAKE → MULTISPLIT с ограниченными по времени прямыми HTTPS-проверками Discord и YouTube; при полном ответе первой стратегии второй запуск пропускается.
- Выбирается профиль с наибольшим числом HTTPS-ответов; при равенстве сохраняется FAKE. Не более двух проверок на профиль. Стратегия меняется только у собственного дочернего процесса WinWS.
- Проверка реагирует на явное отключение пользователя, не создаёт сторонние процессы и не меняет системные настройки DNS или прокси.
- При неполной доступности интерфейс сообщает «Работа обхода не подтверждена». Сам факт ответа HTTPS **не подтверждает** обход DPI.
- Добавлены модуль `smart_dpi.py`, регрессионные тесты, документация `docs/SMART_DPI_V26.md` и индикация фактически выбранного профиля на главной.
- **241 локальный автоматический тест пройден** в окружении без WinDivert. Запуск WinWS, DNS и Telegram на Windows остаётся на этапе приёмочных испытаний.


## 0.25.0 — Проверка автозапуска Windows (Development Preview)

- HKCU Run: проверка реальной команды запуска и типа REG_SZ. Посторонняя или изменённая запись «VORQELI Connect» больше не перезаписывается и не удаляется автоматически.
- Диагностика `--doctor`: значение `startup_registration: untrusted` для неподтверждённой записи реестра, без раскрытия текста команды.
- Повторная регистрация доверенной записи идемпотентна; доверенная задача Планировщика не перезаписывается без необходимости.
- Переход с HKCU Run на повышенную задачу: при сбое удаления старой записи выполняется попытка отката только что созданной задачи (уже существовавшую задачу не удаляем).
- Новые регрессионные тесты: подмена EXE, дополнительные аргументы, бинарный ключ, ошибки прав, откат после ошибки. **223 теста пройдены** локально (без реальных сетевых драйверов).
- В Windows GitHub Actions добавлена проверка реального цикла HKCU Run «создание → проверка → удаление» на чистом раннере.
- Новый документ `docs/WINDOWS_STARTUP_AUDIT_V25.md`.

**Не подтверждено:** CI после публикации исходников, WinDivert, GeoHide и Telegram вместе, автозапуск через перезагрузку, сам Windows-установщик.


## 0.24.0

- Автозапуск: чтение Task Scheduler XML с проверкой команды, аргументов, единственности действия, LogonTrigger и HighestAvailable.
- Запрещена модификация посторонней/повреждённой/недоступной задачи с совпадающим названием.
- Команда `--doctor` обозначает `untrusted`, не раскрывая команду из XML.
- Новые тесты безопасности и руководство `docs/WINDOWS_STARTUP_AUDIT_V24.md`.

## 0.24.0 — Autostart safety & upgrade guards (development preview)

- Не создавать второй автозапуск через HKCU Run, если уже присутствует повышенная задача Windows, но нет прав безопасно изменить её.
- Явно сообщать об ошибке создания задачи вместо тихого перехода на другой способ запуска.
- Диагностика `--doctor` показывает `startup_registration: conflict` при одновременной регистрации задачи и HKCU Run.
- Inno Setup `AppMutex` блокирует попытку обновления, если приложение всё ещё запущено в трее.
- Windows CI проверяет отказ установщика при работающем экземпляре; дополнительные Python-тесты проверяют переключение механизмов запуска.
- Упрощены главная README и документация Windows-приёмки.

**Не проверено в этой среде:** реальный процесс установки Windows, UAC, DPI/WinDivert, сетевые изменения GeoHide и восстановление после перезагрузки.

## 0.22.0 — Safe uninstallation & repository recovery (development preview)

- Before uninstall, check application mutex, remove Windows autorun and restore GeoHide DNS. Fail closed when cleanup is incomplete; do not remove the EXE prematurely.
- Inno Setup `InitializeUninstall` blocks removal on nonzero preflight exit code.
- Repository preflight detects accidentally deleted files, broken assets and mismatched versions before pip install.
- Add `--version`, Windows mutex safety smoke test and 12 new unit tests.
- Document safe recovery of an emptied GitHub repository.
- Requires successful Windows Actions and live networking acceptance.

## 0.21.0 — Verified DNS and safer recovery (development preview)

- Fail-closed settings recovery: if `settings.json` is missing/corrupt and only `settings.bak` is usable, never auto-connect from the older backup's ON value. Other preferences and decryptable Telegram secret remain available.
- GeoHide enable: re-query Windows DNS after PowerShell changes and require all adapters to reflect configured GeoHide addresses before declaring success.
- GeoHide restore: verify actual DNS configuration after each successful reset. Preserve unresolved backups if Windows silently ignores the change.
- GeoHide failed-enable rollback: verify the final state before deleting the recovery snapshot. No false success if a Windows command returned success without changing the adapter.
- Expanded regression tests (161 passing locally on Linux/mocks). The tests simulate Windows behavior; they are not live Windows driver/network tests.
- Added Windows installer install/uninstall smoke script, invoked by GitHub Actions after Inno Setup packaging. Requires validation by an actual CI run.
- Added `docs/WINDOWS_ACCEPTANCE_V21.md` for mandatory live checks.

# v0.20.0 — Integrity and release checks

- Manifest SHA-256 для файлов `.exe`, `.dll`, `.sys` кеша Flowseal; повторная проверка перед использованием.
- Отказ от неподтверждённого старого кеша с повторной загрузкой закреплённого релиза.
- Сохранение прежнего кеша при неудачной загрузке и проверке; атомарная замена в удачном случае.
- Статус локального кеша в `--doctor` без путей и секретов.
- SHA256SUMS.txt в GitHub Actions для EXE и установщика.
- Новые regression-тесты, ручной Windows test plan.

**Не проверено:** реальный WinDivert, автозапуск и сетевой маршрут после перезагрузки Windows.

# Изменения

## v0.19.0 — восстановление и стабильность

- Восстановление Telegram: если принадлежащий VORQELI процесс существует, но не слушает локальный порт, собственный процесс перезапускается без вмешательства в чужие процессы.
- Безопасный откат GeoHide: после частичного сбоя восстановить только затронутые адаптеры; сохранять резервную копию только для проблемных адаптеров.
- Сохранение окна: ошибка записи на диск не мешает сворачиванию в трей или штатному выходу и остановке сетевых модулей.
- Проверка готовности трея до скрытия стартового окна и возврат окна, если трей завершился.
- Новые автоматические тесты отказоустойчивости, сценарии проверки Windows `docs/WINDOWS_ACCEPTANCE_V19.md`.

Обход DPI, DNS, Windows-установщик и запуск после перезагрузки требуют реальных испытаний на Windows, а не только тестов в изолированной среде.
