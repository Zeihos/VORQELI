# VORQELI Connect

**Version 0.1.0 — desktop foundation, not a working DPI bypass or Telegram proxy.**

Independent Windows-oriented network utility. This first increment includes a themed Tkinter GUI, non-invasive connectivity checks for Discord, YouTube, Telegram and GitHub, persistent user settings and unit tests. The DPI processing engine, Telegram MTProto backend, update mechanism, startup integration and signed installer **are not implemented**.

## Run

Requires Python 3.10+ and Windows 10/11 (other desktop platforms may run, but are not supported).

```powershell
py -m pip install -e .
py -m vorqeli_connect
```

## Tests

```powershell
py -m pip install -e '.[dev]'
py -m pytest
```

## Optional EXE packaging (on Windows)

```powershell
py -m PyInstaller --noconfirm --clean --windowed --onefile --name VorqeliConnect --paths src src/vorqeli_connect/app.py
```

Note: use `py -m vorqeli_connect` for supported launching; the PyInstaller single-file invocation may need package context adjustments. Prefer a module-aware .spec for production builds.

## Principles

- Never implicitly modify system DNS, routing, firewall or Windows services.
- No hidden background traffic, no telemetry by default.
- All future external binaries must come from an authenticated, reviewed, license-compatible source with pinned versions and SHA-256 validation.
- Clearly distinguish actual reachability from generic HTTP responses or proxy success.

## Reference projects

- https://github.com/Flowseal/zapret-discord-youtube (check LICENSE.txt and embedded dependencies separately)
- https://github.com/Flowseal/tg-ws-proxy (MIT; retain required attribution when reusing any source)

This repository currently contains new original code and does not embed either upstream project.


## Status
VORQELI Connect v0.2.0 is a rebranded desktop prototype. No DPI/proxy engine is included. The connectivity checks do not establish whether a service is fully usable.

## Attribution
Inspired by https://github.com/Flowseal/zapret-discord-youtube and https://github.com/Flowseal/tg-ws-proxy. Their code is not bundled in this prototype. Integrating third-party code later requires retaining its applicable license notices.
