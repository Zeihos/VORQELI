# VORQELI Connect 0.21.0 — Windows acceptance

## What CI now verifies automatically

- Windows Python tests and DPAPI smoke test.
- PyInstaller EXE starts with `--self-test`.
- EXE writes a local `--doctor` report without exposing Telegram secrets.
- Installer builds, installs into an isolated Windows CI directory, and the installed EXE passes the same read-only checks.
- Inno Setup uninstalls the isolated application; EXE must be removed.
- Checksums of the distributed EXE and installer are generated.

The new installer check **does not** connect to DPI, change DNS, attempt censorship bypass, schedule Windows logon tasks or require a user reboot. Windows CI success does **not** prove this application works with WinDivert or a particular ISP.

## Mandatory physical Windows checks before 1.0

1. Windows 10 and 11: install under `%ProgramFiles%` as admin, close and reopen; no system Python required. Confirm Defender behavior without disabling protection.
2. Start with all three modules selected. Press **Подключиться** once; verify WinWS process ownership, Telegram local listener at `127.0.0.1:1443`, Telegram Desktop `tg://proxy` registration and reachability to the desired applications.
3. Confirm GeoHide settings were actually applied to each targeted IPv4 adapter. Test normal manual/static DNS and DHCP; test failure when adapter refuses changes. Confirm recovery backup remains for unverified rollback.
4. Press **Отключиться**; verify WinWS/TG processes exit and previous DNS configuration is restored. Third-party DNS modifications made while VORQELI runs must never be overwritten automatically.
5. Connect -> close window -> tray stays present and network modules remain active. Reopen via icon. Explicitly exit -> own components stop and DNS restoration runs.
6. Connect -> reboot -> app starts minimized, recreates selected modules, and reconnects only if settings primary is valid and desired state is ON. Disconnect -> reboot -> remains OFF.
7. Corrupt `settings.json` with a known-good backup containing `desired_enabled:true` and restart. The app must fail closed, retain other preferences and **not** reconnect until clicked.
8. Disconnect Wi-Fi during enabled GeoHide and attempt restore; backup should remain available for later retry. Reconnect adapter and restore; inspect DNS on Windows.
9. Try to uninstall while connected and with another copy running. Confirm DNS restoration, task removal, and no network driver left behind. **Do not publish a stable release until uninstallation safety is verified.**
10. Test `--doctor` before and after connection, check it contains no secrets/IP addresses/local paths. Verify downloads against `SHA256SUMS.txt` from the same trusted release page.

If a Windows network test fails, stop and collect only redacted logs; restore DNS manually through Network Settings if VORQELI cannot restore it automatically. Upstream binaries must be obtained only from the official Flowseal projects.
