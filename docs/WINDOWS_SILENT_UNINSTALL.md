# Silent uninstallation regression (Windows CI)

The installed VORQELI cleanup helper already fails closed (exit code 8)
when a running GUI mutex is detected. In the Inno Setup script, this
was followed by an unconditional Pascal Script `MsgBox` in
`InitializeUninstall`. Unlike `SuppressibleMsgBox`, `MsgBox`
is not suppressed by `/SUPPRESSMSGBOXES`. Consequently, the
`blocked-uninstall` CI subprocess could wait for a hidden modal dialog
until its 60-second timeout.

This change keeps all original cleanup conditions and exit codes:

- A failed or nonzero `--uninstall-cleanup` call still returns
  `Result := False`, so no installed files are deleted.
- Interactive uninstallations still receive the Russian error dialog.
- Silent uninstallations (`UninstallSilent()`) write an Inno log
  message instead of opening a modal dialog.
- The Windows smoke check records a dedicated uninstall log and still
  requires a nonzero exit code with the installed EXE intact.
- The later uninstall after releasing the mutex remains mandatory.

Neither GUI asset resolution nor DPI, GeoHide DNS, HOSTS, proxies,
network processes, or Telegram settings are modified by this change.

## Validation

Run `python -m pytest -q` and `python scripts/verify_build_manifest.py`
locally. The definitive Inno Setup runtime check is the Windows CI
installer smoke step, including the blocked-uninstall and upgrade cases.
