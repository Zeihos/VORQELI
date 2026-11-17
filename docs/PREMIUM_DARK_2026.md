# VORQELI · Premium Dark 2026

This is a **real Tkinter Canvas** UI refresh on top of v0.41.0, not screenshot-backed buttons.

## Principles

- Neutral graphite background and subtle layered surfaces; violet is reserved for primary actions and selection
- Real module state is distinct from remote-site availability; no invented IP, country, latency or VPN claims
- Pointer clicks do not leave a keyboard focus ring; keyboard focus remains visible through Tab
- Consistent typography, compact sidebar, sufficient click targets, and readable text at 80% minimum scale
- Preserve the existing app/controller callbacks for WinWS, Telegram and GeoHide DNS/HOSTS
- Diagnostics retain strict response semantics: HTTP 403/429 are not treated as success

## Verification

Run `python -m pytest -q`, `python scripts/check_repo_layout.py`,
`python scripts/verify_build_manifest.py`, and inspect the six real Tkinter screens
at Windows DPI 100%, 125%, 150% and at 1280×720, 1920×1080.

This update does not establish real-world efficacy of any network bypass.
