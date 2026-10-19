# VORQELI Connect v0.38.0 — Production UI pass

## Actual application changes

* Entire six-page Python/Tk Canvas renderer replaced: not a screenshot, external website, or independent mock app.
* Consistent dark navy+blue color tokens, gradient/glass backgrounds, layered cards, in-app vector service glyphs, hero glow/waves, on/off/partial/error states, custom pill controls and switch thumbs.
* Sidebar navigation and keyboard tab registry preserved. Layout works from logical 1060×710 upwards; existing Tk scrollbars cover physically smaller work areas.
* Main page shows actual statuses reported by `UnifiedController`; it does not equate active DPI or DNS with unblocked websites.
* Diagnostics lists exactly 5 categories. Microsoft is **one** category; individual HTTPS checks still use existing backend. `HTTP 403` is an HTTP rejection, not marked as working.
* History filters `Все события`, `Подключение`, `Настройки`, `Ошибки` change the displayed local event list. Export JSON retains existing behavior.
* Settings include working persisted switches for startup, reconnect, tray, UAC and the three modules; advanced screen implements 13 real ALT choices, automated ALT selection, GeoHide IPv4/DoH choice and real HOSTS/DNS actions.
* No new unsupported IPSet or protocol switches. Those are controlled by Flowseal selected strategy; exposing pretend controls would be misleading.
* Network/WinDivert/DNS/MTProto code and system HOSTS are not modified by this update.
* Tray startup and UAC improvements from v0.37.0 are retained. This patch does not revert them.

## Safety and release verification

* Save the current checkout and verify the manifest first. The patch targets **v0.37.0** and aborts when source hashes diverge or a partial patch exists.
* Apply patch, run `py -3.12 -m pip install -e ".[dev]"`, `py -3.12 -m pytest -q`, `py -3.12 scripts/check_repo_layout.py`, `py -3.12 scripts/verify_build_manifest.py`, `git diff --check`.
* Compile Windows EXE and installer via GitHub Actions before a release. Manually inspect all six screens at 1060×710, 1180×780 and different Windows display scaling, tabs, disabled controls, scrollbars and modal windows.
* Confirm tray registration/menu/Explorer restart, Windows UAC accepted/declined, DPI startup, Telegram, DNS backup+restore and full uninstall on real Windows. A Linux virtual-display UI smoke and offline unit tests do not prove Windows deployment behavior.

Version 0.38.0 is a UI-quality release; it is not a claim that GeoHide can guarantee access to Claude or that external services have no regional restrictions.
