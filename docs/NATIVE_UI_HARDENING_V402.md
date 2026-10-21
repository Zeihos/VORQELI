# VORQELI Connect 0.40.2 RC — Native UI reliability

Native Tk Canvas v0.40.1 remains the sole active renderer. No whole-screen PNGs or baked demo statistics are used. Existing VORQELI-logo.png, ICO and wordmark are not edited.

## Corrections

1. Real, focusable history rows open full event detail on both mouse and keyboard. Row actions use captured event data from the selected page; pagination and filtered history cannot open the wrong row.
2. While an asynchronous diagnostic is running, all five individual HTTPS buttons and the collective action are visually disabled, preserving the network worker's serialization contract. Current application detail is shown as-is, without fabricated progress.
3. Small service pictograms and original logo are decoded and resized only once for each pixel size, using an 80-entry in-process bounded cache. Each file handle closes immediately. Tk image references remain alive for the current Canvas frame and are released on the next draw.
4. The app still uses the original `app.py` callbacks, with no change to WinWS, Telegram, DNS, HOSTS, privileges, install/uninstall or autostart logic.
5. Added independent tests for page-specific history actions, busy/idle diagnostics, icon caching and ensuring native Canvas surfaces rather than screenshot backgrounds.

## Verification completed in test environment

- Syntax compilation and 27 native UI tests (v0.40.1 + new v0.40.2 assertions) passed on Python 3.
- Tkinter actual rendering under Xvfb: six screens and mouse-click on a settings toggle passed.
- Combined patch is designed to accept clean source v0.40.0 or integrity-checked v0.40.1 and fails closed on unknown versions or changed native renderer files.

## Release blockers

Full Windows pytest after patch, Windows GitHub Actions build, GUI pixel/layout inspection at 100/150/200% scaling, installed EXE smoke, real DPI/MTProto/GeoHide network acceptance, DNS/HOSTS recovery, and installer code signing. This is a candidate, not stable 1.0.0.
