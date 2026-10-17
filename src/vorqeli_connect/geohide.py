"""GeoHide IPv4 DNS profile with backed-up adapter settings and safe restoration.

No hosts-file edits. Windows PowerShell commands are fixed templates, never built
from user-controlled shell fragments. DNS address mappings can change upstream.
"""
from __future__ import annotations
import json
import os
import re
import socket
import subprocess
import urllib.request
from pathlib import Path
from .config import APP_DIR

INFO_PAGE = 'https://dns.geohide.ru:8443/'
DOH_TEMPLATE = 'https://geohide.ru/dns-query'
# Published addresses, revalidate with GeoHide before future releases.
GEOHIDE_IPV4 = ('159.194.200.33', '37.230.192.51')
STATE_FILE = APP_DIR / 'dns-restore.json'
POWERSHELL = ['powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-Command']


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
  $before=@((Get-DnsClientServerAddress -InterfaceIndex $a.ifIndex -AddressFamily IPv4).ServerAddresses)
  [pscustomobject]@{ index=[int]$a.ifIndex; alias=[string]$a.Name; manual=[string]$manual; before=@($before) }
}
@($result) | ConvertTo-Json -Depth 5 -Compress
'''


def _validate_state(items: object) -> list[dict]:
    if not isinstance(items, list):
        raise ValueError('Неверный формат резервной копии DNS')
    checked = []
    for item in items:
        if (not isinstance(item, dict) or type(item.get('index')) is not int or
                item['index'] < 1 or not isinstance(item.get('manual'), str) or
                not isinstance(item.get('before'), list)):
            raise ValueError('Некорректные данные сетевого адаптера')
        checked.append({'index': item['index'], 'manual': item['manual'], 'before': item['before'],
                        'alias': str(item.get('alias', ''))})
    return checked


def query_dns_state() -> list[dict]:
    raw = json.loads(_ps(_SNAPSHOT) or '[]')
    return _validate_state(raw if isinstance(raw, list) else [raw])


def _apply_one(index: int, ip_addresses: list[str] | None = None) -> None:
    idx = int(index)
    if ip_addresses is None:
        _ps(f'Set-DnsClientServerAddress -InterfaceIndex {idx} -ResetServerAddresses -ErrorAction Stop')
    else:
        addresses = ','.join("'" + str(x).replace("'", "") + "'" for x in ip_addresses)
        _ps(f'Set-DnsClientServerAddress -InterfaceIndex {idx} -ServerAddresses @({addresses}) -ErrorAction Stop')


def _dns_probe(timeout: float = 5.0) -> None:
    """Verify DoH endpoint returns a DNS message before changing OS networking."""
    # RFC 1035 example.com A query, fixed ID 0xAC01.
    query = b'\xac\x01\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00' + b'\x07example\x03com\x00\x00\x01\x00\x01'
    req = urllib.request.Request(DOH_TEMPLATE, data=query,
                                 headers={'Content-Type':'application/dns-message',
                                          'Accept':'application/dns-message',
                                          'User-Agent':'VORQELI-Connect/0.12.0'})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        data = response.read(4096)
    if len(data) < 12 or data[:2] != query[:2] or data[2] & 0x80 == 0:
        raise RuntimeError('Сервис GeoHide не вернул корректный DNS-ответ')


def _save_state(items: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps({'provider': 'geohide', 'interfaces': items}, ensure_ascii=False,
                              indent=2), encoding='utf-8')
    tmp.replace(path)


def restore_dns(path: Path = STATE_FILE) -> bool:
    if not path.is_file():
        return False
    saved = json.loads(path.read_text(encoding='utf-8'))
    entries = _validate_state(saved['interfaces'])
    errors = []
    current = {a['index']: a for a in query_dns_state()}
    for item in entries:
        # Respect changes made by users/other applications while VORQELI ran.
        now = current.get(item['index'])
        if now is None or tuple(now['before']) not in (GEOHIDE_IPV4, GEOHIDE_IPV4[:1]):
            continue
        try:
            manual = [s.strip() for s in re.split(r'[,;\s]+', item['manual']) if s.strip()]
            _apply_one(item['index'], manual or None)
        except Exception as exc:
            errors.append(f"{item['alias']}: {exc}")
    if errors:
        raise RuntimeError('Не удалось вернуть DNS: ' + '; '.join(errors))
    path.unlink(missing_ok=True)
    return True


def enable_dns(path: Path = STATE_FILE, *, probe=True) -> int:
    if path.exists():
        # Never overwrite the original snapshot on reboot. Verify current DNS
        # instead of claiming an unchanged machine has GeoHide active.
        saved = _validate_state(json.loads(path.read_text(encoding='utf-8'))['interfaces'])
        current = {a['index']: a for a in query_dns_state()}
        if not saved or not all(
            e['index'] in current and tuple(current[e['index']]['before']) in
            (GEOHIDE_IPV4, GEOHIDE_IPV4[:1]) for e in saved
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
    changed = []
    try:
        for entry in current:
            _apply_one(entry['index'], list(GEOHIDE_IPV4))
            changed.append(entry['index'])
    except Exception:
        # Best effort rollback from snapshot, retaining backup if restoration fails.
        restore_dns(path)
        raise
    return len(changed)
