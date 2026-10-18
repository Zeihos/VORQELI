# VORQELI Connect v0.32.0 — Windows Release Candidate validation

**Status:** Development Preview, not v1.0. Code tests and GitHub Actions smoke
checks are not evidence that DPI bypass, Telegram access or encrypted DNS works
on end-user Windows networks.

## A. Restore all project files to GitHub

1. Extract the ZIP **contents** into the root of `Zeihos/VORQELI` (including
   `.github/`, `src/`, `installer/`, `scripts/`, `tests/`, `assets/`).
2. Run `python scripts/check_repo_layout.py`.
3. Run `python scripts/verify_build_manifest.py`. This fails if mandatory
   files are missing, tracked files differ from the manifest, unlisted code
   files appear, or a manifest path resolves through a symlink.
4. Run `python -m pytest -q` and check the entire suite. Do not regenerate
   `BUILD_MANIFEST.json` automatically in CI; source integrity is distinct
   from publisher authenticity.

## B. Windows GitHub Actions smoke test

Workflow `.github/workflows/windows-build.yml` must complete ALL of:

- PyInstaller EXE and `--version`, `--self-test`, read-only `--doctor`;
- Windows DPAPI secret roundtrip;
- HKCU Run registration creation/verification/removal, with no DPI/DNS calls;
- Inno Setup build;
- silent install, bundled resources, `--self-test`, read-only doctor;
- block upgrade AND uninstall when the named app mutex is held;
- allow an in-place upgrade when the mutex is released, verify installed
  executable SHA-256 and run `--self-test` again;
- silent uninstall and verify installed EXE was removed;
- two release-file SHA-256 sums.

Never mark the release stable if a Windows runner failed or its logs are missing.

## C. Real Windows 10/11 acceptance (manual, clean VM recommended)

- Install without Python. Check UAC and Windows SmartScreen behavior.
- With network disconnected, activate and cancel; check status/error honesty.
- Check DPI and Telegram separately and together, including remote reachability
  independently of `winws.exe` process existence or the local Telegram socket.
- Check GeoHide plain DNS, enable optional DoH only on a supported Windows
  image. Confirm real DNS traffic protection; PowerShell mappings alone are
  insufficient proof of HTTPS-only DNS.
- On a multi-adapter Windows installation, verify original DNS returns after
  Disconnect and abnormal termination. Reboot and repeat. Check wired/Wi-Fi
  switches, VPN adapters, sleep/wake, and changes by third-party DNS tools.
- Check remembered OFF across reboot (must stay off) and ON across reboot
  (must restore only if previously explicitly ON). Check no duplicate launches.
- Repeat uninstall when DNS recovery is incomplete and verify it refuses
  to delete the only available cleanup executable.
- Test Windows accessibility at 100/150/200% scaling, keyboard-only Tab focus,
  visible controls, and tray failure.

## D. Security publication gate

The project SHA-256 manifest is for completeness only; it is not a signature.
Sign **both** `VORQELI-Connect.exe` and `VORQELI-Connect-Setup.exe` using an
approved Authenticode publisher certificate and run
`scripts/windows_release_gate.ps1 -TrustedSignerThumbprint <sha1-thumbprint>`
after regenerating `dist/SHA256SUMS.txt` for the *signed* files.

VORQELI does not automatically execute downloaded installers. Publishing v1.0
requires a separate security review and successful full Windows acceptance.
