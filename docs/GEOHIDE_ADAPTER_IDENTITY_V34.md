# VORQELI v0.34.0 — GeoHide network adapter identity safety

## Why this exists

Windows `InterfaceIndex` is not a permanent identifier. Ethernet/Wi-Fi
reconnects, virtual adapters and driver changes can reassign it to another NIC.
Blindly restoring a DNS backup by index could change the **wrong adapter**.

## New behavior

- A new read-only PowerShell adapter snapshot records `InterfaceGuid` alongside
  `InterfaceIndex`, alias, original DNS addresses and whether DNS was manually set.
- Backups validate GUID syntax and duplicate identities. For each modification,
  VORQELI checks that the current index belongs to the same GUID.
- The PowerShell `Get-NetAdapter -InterfaceIndex` GUID guard executes in the
  **same PowerShell process as** `Set-DnsClientServerAddress`.
- When the index no longer belongs to the same adapter, no changes are made to
  that adapter; the original backup is retained for manual recovery.
- Renaming the adapter is fine because GUID, not display name, is authoritative.
- Old pre-v0.34.0 backups lack GUIDs. They remain readable; for these, the
  saved alias must match (if present). This is a compatibility fallback, not a
  proof of stable identity. Never delete older backups merely to migrate them.
- A DHCP reset is successful only if the system reports no manually configured
  DNS and the effective addresses are not still the GeoHide DNS profile.

## Windows acceptance tests (manual)

1. On a throwaway Windows 10/11 VM with two network adapters, note original DNS.
2. Connect GeoHide; confirm `dns-restore.json` contains a GUID for each adapter.
3. Disconnect and verify both original DNS profiles are restored.
4. With GeoHide active, disable/enable a NIC or switch networks; disconnect.
   If Windows reuses an index for another adapter, VORQELI must retain the
   backup and explicitly report incomplete restore without changing that NIC.
5. Rename a NIC without changing GUID; restoration should still work.
6. Repeat in DoH mode on supported Windows. Independently verify encrypted DNS
   traffic; a command reporting success does not prove HTTPS traffic.
7. Test old GUID-less backup compatibility before any production migration.

This release was tested offline and in a virtual Tk GUI; the Windows adapter
changes above require testing on a real or virtual Windows installation.
