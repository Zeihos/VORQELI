# VORQELI v0.31.0 — Windows release gate

1. Restore the **full** source archive to the GitHub repository root, preserving `.github/` and `src/`.
2. Run `python scripts/check_repo_layout.py` and `python scripts/verify_build_manifest.py`. These checks detect missing files and unexpected changes; they do not authenticate the publisher.
3. Run Windows GitHub Actions and capture logs for Python tests, DPAPI, registry startup, read-only DoH probe, EXE, Inno Setup, install/uninstall smoke.
4. On a genuine Windows 10 and Windows 11 machine: connect DPI, Telegram and GeoHide; verify actual service behavior, error and partial-status indications, DNS restore (including DHCP/multiple adapters), exit-to-tray, auto-start ON/OFF after reboot, sleep/wake and changing networks.
5. Sign **both** Windows binaries with a trusted publisher certificate. Generate new SHA256SUMS after signing, pin independently verified certificate thumbprint, and run `scripts/windows_release_gate.ps1`.
6. Publish v1.0 only when every P0 scenario has a recorded PASS, with signed build provenance. Avoid claiming that passing 380 simulated Python tests proves actual bypass or encrypted DNS on Windows.

Current status: **not ready for public stable release**.
