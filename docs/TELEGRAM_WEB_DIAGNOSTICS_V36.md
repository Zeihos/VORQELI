# VORQELI v0.36 — Telegram Web diagnostics

## Motivation

Telegram MTProto (`tg-ws-proxy`) works independently of Telegram Web, which uses
browser TLS/HTTPS, JavaScript and additional domains. A running WinWS process or
an HTTP 200 response cannot confirm browser functionality. A fixed HOSTS record
may conflict with the domain's currently returned DNS answer.

## Read-only in-app verification

1. Open **Диагностика → TELEGRAM WEB**.
2. The window independently requests `https://web.telegram.org/k/` and `/a/`
   via direct HTTPS (no inherited HTTP proxy), and checks known K/A gateway
   hostnames. The TLS peer certificate is verified via the normal OS trust store.
3. The system HOSTS file is read without modification. Only known Telegram Web
   hostnames are displayed; arbitrary custom domains are not exported.
4. Windows `Resolve-DnsName -NoHostsFile -DnsOnly` compares the current DNS
   answers for `web.telegram.org` with pinned HOSTS overrides, if present.
5. The UI shows DNS/TLS/timeout/HTTP failures separately; checks are bound to
   a small fixed host allowlist and can be repeated on demand.

## Interpretation

* **HTTPS OK**: an HTTP response arrived, not proof that the Telegram Web SPA
  loaded or that login/messaging works.
* **HTTP error**: server replied; the browser path may still be unavailable.
* **TLS error**: certificate / handshake failure; a stale fixed HOSTS IP is one
  potential cause, but not the only one.
* **DNS error**: no address was resolved; check DNS and manual HOSTS records.
* **Different HOSTS/DNS IPs**: investigate; multi-CDN and regional responses can
  legitimately differ, so do not automatically overwrite the user's HOSTS.

Browsers can use DoH, QUIC/HTTP3 or proxy settings, causing different results.
No user IP mappings are sent to any telemetry endpoint; data stays in the UI.

## Release acceptance

* Windows CI: tests, PyInstaller, executable self-test, silent installer lifecycle.
* On Windows: test Web K/A directly with and without system HOSTS, without
  changing working ALT profiles or Telegram MTProto.
* GeoHide should be evaluated separately against a clean DNS/hosts baseline.
