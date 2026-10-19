# GeoHide / AI read-only diagnostics (v0.36.2 candidate)

Field observations: Discord, YouTube, Telegram MTProto and Telegram Web HOSTS
work on a friend's Windows PC, but ChatGPT and Claude fail. This does NOT by
itself establish that GeoHide was not configured.

## Source audit

- Windows DNS is set via `Set-DnsClientServerAddress` to the pinned pair
  159.194.200.33 and 37.230.192.51. The program verifies configured IPv4
  addresses on detected active **physical** adapters.
- Default configuration uses `dns_mode=plain` (unencrypted IPv4 DNS).
  `dns_mode=doh` is opt-in and depends on compatible Windows commands.
- The v0.36.1 resource `assets/VORQELI-hosts-optional.txt` contains no ChatGPT
  or Claude domain rules. A larger GeoHide HOSTS list pasted by a tester is
  **not** installed automatically by VORQELI. This patch does not ingest it.
- Runtime DNS status is still backed by the existence of an internal recovery
  journal. A journal is not a live proof of active browser DNS resolution.

## What this patch changes

Only the user-triggered **Diagnostics > DNS / HOSTS** window now additionally
reads candidate Windows IPv4 default-route adapters, compares their configured
DNS with the GeoHide pair, reads DoH template flags if DoH was explicitly
selected, and makes bounded A-record queries for `chatgpt.com` and `claude.ai`
against **each** pinned GeoHide resolver, excluding the HOSTS file.

These are read-only probes, not HTTPS access/login/censorship tests. They
cannot prove that a browser uses Windows DNS; browser Secure DNS (DoH), VPN,
IPv6, service-side geolocation and network filtering may differ.

The route list contains **candidates**, not a promise about exact Windows
routing decisions. The audit considers a missing VPN adapter `unknown`, never
silently reports success because any unrelated NIC has GeoHide DNS.

There is no change to settings, system DNS application, GeoHide rollback,
HOSTS, Flowseal ALT strategies, proxies, driver startup or automatic switching.

## After application

Run `py -3.12 -m pytest -q` and `py -3.12 scripts/verify_build_manifest.py`,
then push the changes and wait for Windows CI. The friend should open the
new version, connect, navigate to Diagnostics > DNS / HOSTS, and compare the
reports from ChatGPT and Claude with `plain` vs manual opt-in `DoH`. Avoid
changing DNS or hosts manually during the comparison.
