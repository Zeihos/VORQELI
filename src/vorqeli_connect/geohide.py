"""GeoHide IPv4 DNS profile with backed-up adapter settings and safe restoration.

No hosts-file edits. Windows PowerShell commands are fixed templates, never built
from user-controlled shell fragments. DNS address mappings can change upstream.
"""
from __future__ import annotations
import json
import ipaddress
import os
import re
import socket
import subprocess
import urllib.request
from pathlib import Path
from .config import APP_DIR

INFO_PAGE = 'https://geohide.ru/'
DOH_TEMPLATE = 'https://geohide.ru/dns-query'
# Published addresses, revalidate with GeoHide before future releases.
GEOHIDE_IPV4 = ('159.194.200.33', '37.230.192.51')
STATE_FILE = APP_DIR / 'dns-restore.json'
POWERSHELL = ['powershell.exe', '-NoProfile', '-NonInteractive', '-Command']


def _ps(script: str, *, timeout: int = 25) -> str:
    if os.name != 'nt':
        raise RuntimeError('Настройка DNS поддерживается только на Windows')
    p = subprocess.run([*POWERSHELL, script], capture_output=True, text=True,
                       timeout=timeout, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if p.returncode:
        raise RuntimeError((p.stderr or p.stdout or 'PowerShell завершился с ошибкой')[-2000:])
    return p.stdout.strip()


_SNAPSHOT = r'''
$ErrorActionPreference='Stop'
$items = @(Get-NetAdapter | Where-Object { $_.Status -eq 'Up' -and $_.HardwareInterface -eq $true })
$result = foreach ($a in $items) {
  $guid='{' + ([string]$a.InterfaceGuid).Trim('{}') + '}'
  $key='HKLM:\SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces\' + $guid
  $manual=''
  if (Test-Path $key) { $manual=[string](Get-ItemProperty -Path $key -Name NameServer -ErrorAction SilentlyContinue).NameServer }
  # Some hosted Windows NICs have no matching DNS Client CIM instance.
  # Skip only this exact missing-object error, never mask other CIM failures.
  try {
    $dns = Get-DnsClientServerAddress -InterfaceIndex $a.ifIndex -AddressFamily IPv4 -ErrorAction Stop
  } catch {
    if ($_.FullyQualifiedErrorId -like 'CmdletizationQuery_NotFound*') { continue }
    throw
  }
  $before=@($dns.ServerAddresses)
  [pscustomobject]@{ index=[int]$a.ifIndex; guid=[string]$a.InterfaceGuid; alias=[string]$a.Name; manual=[string]$manual; before=@($before) }
}
@($result) | ConvertTo-Json -Depth 5 -Compress
'''


_GUID = re.compile(r'^(?:[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}|\{[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}\})$')


def _clean_guid(value: str) -> str:
    # Interface GUIDs are stable across adapter renames and ifIndex reuse.
    if type(value) is not str or not _GUID.fullmatch(value):
        raise ValueError('Некорректный идентификатор сетевого адаптера')
    return value.strip('{}').lower()


def adapter_matches(saved: dict, observed: dict | None) -> bool:
    """Conservatively validate that an interface index still identifies ours.

    Legacy backups predate GUID persistence; use the recorded alias as a
    weak compatibility check rather than modifying a differently named NIC.
    A new backup always stores a GUID and rejects missing identity data.
    """
    if observed is None or saved['index'] != observed.get('index'):
        return False
    if saved.get('guid'):
        try:
            return _clean_guid(saved['guid']) == _clean_guid(observed.get('guid'))
        except ValueError:
            return False
    alias = str(saved.get('alias', '')).strip()
    return not alias or alias.casefold() == str(observed.get('alias', '')).strip().casefold()


def _apply_for_record(record: dict, addresses: list[str] | None) -> None:
    """Check adapter identity inside the PowerShell invocation when available."""
    if record.get('guid'):
        _apply_one(record['index'], addresses, record['guid'])
    else:
        # Historic journals did not have GUIDs. Their identity is checked
        # against the latest snapshot immediately before this call.
        _apply_one(record['index'], addresses)


def _clean_ipv4(address: object) -> str:
    """Strict input validation: never interpolate arbitrary backup text in PS."""
    if not isinstance(address, str):
        raise ValueError('DNS-адрес должен быть строкой')
    try:
        return str(ipaddress.IPv4Address(address.strip()))
    except ipaddress.AddressValueError as exc:
        raise ValueError(f'Недопустимый IPv4 DNS-адрес: {address[:64]}') from exc


def _manual_addresses(manual: str) -> list[str]:
    if not manual.strip():
        return []
    return [_clean_ipv4(value) for value in re.split(r'[,;\s]+', manual) if value.strip()]


def _validate_state(items: object) -> list[dict]:
    if not isinstance(items, list) or len(items) > 128:
        raise ValueError('Неверный формат резервной копии DNS')
    checked = []
    seen = set()
    seen_guids = set()
    for item in items:
        if (not isinstance(item, dict) or type(item.get('index')) is not int or
                not 1 <= item['index'] <= 2147483647 or
                not isinstance(item.get('manual'), str) or
                not isinstance(item.get('before'), list)):
            raise ValueError('Некорректные данные сетевого адаптера')
        if item['index'] in seen:
            raise ValueError('Повторяющийся индекс сетевого адаптера')
        seen.add(item['index'])
        original = [_clean_ipv4(x) for x in item['before']]
        _manual_addresses(item['manual'])
        guid = _clean_guid(item['guid']) if 'guid' in item else ''
        if guid:
            if guid in seen_guids:
                raise ValueError('Повторяющийся GUID сетевого адаптера')
            seen_guids.add(guid)
        checked_item = {'index': item['index'], 'manual': item['manual'], 'before': original,
                        'alias': str(item.get('alias', ''))[:128]}
        if guid:
            checked_item['guid'] = guid
        checked.append(checked_item)
    return checked


def query_dns_state() -> list[dict]:
    raw = json.loads(_ps(_SNAPSHOT) or '[]')
    return _validate_state(raw if isinstance(raw, list) else [raw])


def _apply_one(index: int, ip_addresses: list[str] | None = None,
               guid: str | None = None) -> None:
    idx = int(index)
    if not 1 <= idx <= 2147483647:
        raise ValueError('Некорректный индекс сетевого адаптера')
    guard = ''
    if guid:
        expected = _clean_guid(guid)
        # Do not trust the adapter index across reconnects. Check stable GUID
        # in the very same PowerShell script that changes the DNS servers.
        guard = (f"$nic=Get-NetAdapter -InterfaceIndex {idx} -ErrorAction Stop; "
                 f"if (([string]$nic.InterfaceGuid).Trim('{{}}').ToLowerInvariant() -ne '{expected}') "
                 "{ throw 'Сетевой адаптер заменён' }; " )
    if ip_addresses is None:
        _ps(guard + f'Set-DnsClientServerAddress -InterfaceIndex {idx} -ResetServerAddresses -ErrorAction Stop')
    else:
        addresses = ','.join("'" + _clean_ipv4(x) + "'" for x in ip_addresses)
        _ps(guard + f'Set-DnsClientServerAddress -InterfaceIndex {idx} -ServerAddresses @({addresses}) -ErrorAction Stop')


def _dns_probe(timeout: float = 5.0) -> None:
    """Verify DoH endpoint returns a DNS message before changing OS networking."""
    # RFC 1035 example.com A query, fixed ID 0xAC01.
    query = b'\xac\x01\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00' + b'\x07example\x03com\x00\x00\x01\x00\x01'
    req = urllib.request.Request(DOH_TEMPLATE, data=query,
                                 headers={'Content-Type':'application/dns-message',
                                          'Accept':'application/dns-message',
                                          'User-Agent':'VORQELI-Connect/0.27.0'})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        data = response.read(4096)
    if len(data) < 12 or data[:2] != query[:2] or data[2] & 0x80 == 0:
        raise RuntimeError('Сервис GeoHide не вернул корректный DNS-ответ')


def _save_state(items: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    with tmp.open('w', encoding='utf-8') as handle:
        json.dump({'provider': 'geohide', 'interfaces': items}, handle,
                  ensure_ascii=False, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    tmp.replace(path)


def restore_dns(path: Path = STATE_FILE) -> bool:
    """Restore only adapters still managed by VORQELI.

    Never discard unresolved adapter backups: the adapter may be unplugged,
    changed by a VPN, or unavailable due to a Windows API failure. Successful
    adapters are removed from the backup to prevent a later retry from
    reverting new manual changes on already-restored adapters.

    Return True only when all saved adapters have been restored. False means
    a backup remains and operator attention is required; it is *not* success.
    """
    if not path.is_file():
        return False
    saved = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(saved, dict) or saved.get('provider') != 'geohide':
        raise ValueError('Неверный формат резервной копии GeoHide')
    entries = _validate_state(saved['interfaces'])
    errors = []
    remaining = []
    verify_restored = []
    current = {a['index']: a for a in query_dns_state()}
    for item in entries:
        now = current.get(item['index'])
        if now is None:
            remaining.append(item)
            errors.append(f"{item['alias']}: адаптер отсутствует — резервная копия сохранена")
            continue
        if not adapter_matches(item, now):
            remaining.append(item)
            errors.append(f"{item['alias']}: сетевой адаптер изменился — резервная копия сохранена")
            continue
        if tuple(now['before']) == tuple(item['before']):
            # Common after a crash midway through enabling GeoHide: this
            # adapter was never changed, or was already restored successfully.
            # Do not leave an unnecessary recovery record indefinitely.
            continue
        if tuple(now['before']) not in (GEOHIDE_IPV4, GEOHIDE_IPV4[:1]):
            # Respect DNS changes made outside VORQELI; do not lose the snapshot.
            remaining.append(item)
            errors.append(f"{item['alias']}: DNS изменён другой программой — резервная копия сохранена")
            continue
        try:
            manual = _manual_addresses(item['manual'])
            _apply_for_record(item, manual or None)
            verify_restored.append((item, manual))
        except Exception as exc:
            remaining.append(item)
            errors.append(f"{item['alias']}: {exc}")
    if verify_restored:
        try:
            after = {a['index']: a for a in query_dns_state()}
        except Exception as exc:
            remaining.extend(item for item, _ in verify_restored)
            errors.append('Не удалось проверить DNS после восстановления: ' + str(exc))
        else:
            for item, manual in verify_restored:
                actual = after.get(item['index'])
                current_ips = tuple(actual['before']) if adapter_matches(item, actual) else None
                # With DHCP the resolver can legitimately change after a reset.
                # We can only verify it is no longer the GeoHide pair; with
                # manual DNS the exact addresses must be restored.
                valid = ((current_ips == tuple(manual)) if manual else
                         (current_ips is not None and
                          current_ips not in (GEOHIDE_IPV4, GEOHIDE_IPV4[:1]) and
                          str(actual.get('manual', '')).strip() == ''))
                if not valid:
                    remaining.append(item)
                    errors.append(f"{item['alias']}: Windows не подтвердил восстановление DNS")
    if remaining:
        # Keep only unresolved records. The original file is left untouched if
        # this atomic write fails, which also avoids losing recovery evidence.
        if len(remaining) < len(entries):
            _save_state(remaining, path)
        raise RuntimeError('DNS восстановлен не полностью: ' + '; '.join(errors))
    path.unlink()
    return True


def enable_dns(path: Path = STATE_FILE, *, probe=True) -> int:
    if path.exists():
        # Never overwrite the original snapshot on reboot. Verify current DNS
        # instead of claiming an unchanged machine has GeoHide active.
        saved = _validate_state(json.loads(path.read_text(encoding='utf-8'))['interfaces'])
        current = {a['index']: a for a in query_dns_state()}
        if not saved or not all(
            adapter_matches(e, current.get(e['index'])) and
            tuple(current[e['index']]['before']) in (GEOHIDE_IPV4, GEOHIDE_IPV4[:1])
            for e in saved
        ):
            raise RuntimeError('Существует резервная копия DNS, но настройки изменились. '
                               'Сначала восстановите DNS в настройках VORQELI.')
        return len(saved)
    if probe:
        _dns_probe()
    current = query_dns_state()
    if not current:
        raise RuntimeError('Не найдены активные физические сетевые адаптеры')
    _save_state(current, path)
    attempted = []
    try:
        for entry in current:
            # Include the failing adapter: a failed Windows API call may still
            # have changed its configuration before returning an error.
            attempted.append(entry['index'])
            _apply_for_record(entry, list(GEOHIDE_IPV4))
        # PowerShell command success is not proof that Windows accepted the DNS
        # settings. Verify every adapter before reporting connection success.
        after = {item['index']: item for item in query_dns_state()}
        for entry in current:
            found = after.get(entry['index'])
            if not adapter_matches(entry, found) or tuple(found['before']) != GEOHIDE_IPV4:
                raise RuntimeError('Windows не подтвердил применение GeoHide DNS '
                                   f'для адаптера {entry["index"]}')
    except Exception as original:
        # Roll back only adapters touched by our attempt. Keep a recovery file
        # only for adapters whose state we could not establish or restore.
        pending = []
        recovery_errors = []
        try:
            now = {a['index']: a for a in query_dns_state()}
            for item in current:
                if item['index'] not in attempted:
                    continue
                actual = now.get(item['index'])
                if actual is None:
                    pending.append(item)
                    recovery_errors.append(f"{item['alias']}: адаптер недоступен")
                elif not adapter_matches(item, actual):
                    pending.append(item)
                    recovery_errors.append(f"{item['alias']}: сетевой адаптер заменён")
                elif tuple(actual['before']) == tuple(item['before']):
                    continue  # Original DNS was not changed.
                elif tuple(actual['before']) in (GEOHIDE_IPV4, GEOHIDE_IPV4[:1]):
                    try:
                        _apply_for_record(item, _manual_addresses(item['manual']) or None)
                    except Exception as rollback_error:
                        pending.append(item)
                        recovery_errors.append(f"{item['alias']}: {rollback_error}")
                else:
                    # Another program may have changed DNS; never overwrite it.
                    pending.append(item)
                    recovery_errors.append(f"{item['alias']}: обнаружены сторонние изменения DNS")
        except Exception as inspection_error:
            pending = [item for item in current if item['index'] in attempted]
            recovery_errors.append(f'Не удалось проверить откат: {inspection_error}')
        # A successful rollback command may still be ignored by Windows.
        # Verify the effective adapter state before deleting recovery evidence.
        if not pending:
            try:
                after_rollback = {a['index']: a for a in query_dns_state()}
                for item in current:
                    if item['index'] not in attempted:
                        continue
                    actual = after_rollback.get(item['index'])
                    ips = tuple(actual['before']) if adapter_matches(item, actual) else None
                    manual = _manual_addresses(item['manual'])
                    if manual:
                        ok = ips == tuple(manual)
                    else:
                        ok = (ips is not None and
                              ips not in (GEOHIDE_IPV4, GEOHIDE_IPV4[:1]) and
                              str(actual.get('manual', '')).strip() == '')
                    if not ok:
                        pending.append(item)
                        recovery_errors.append(
                            f"{item['alias']}: откат DNS не подтверждён")
            except Exception as verification_error:
                pending = [item for item in current if item['index'] in attempted]
                recovery_errors.append('Не удалось проверить откат DNS: ' + str(verification_error))
        if pending:
            # Preserve evidence for operator-assisted restoration, even when
            # some interfaces recovered and others did not.
            _save_state(pending, path)
            raise RuntimeError(
                f'GeoHide не применён: {original}. Восстановление не завершено: '
                + '; '.join(recovery_errors)
            ) from original
        path.unlink(missing_ok=True)
        raise
    return len(attempted)
