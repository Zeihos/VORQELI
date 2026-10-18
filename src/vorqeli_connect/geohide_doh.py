"""Opt-in Windows system DNS-over-HTTPS for the GeoHide IPv4 profile.

The native Windows DnsClient mapping is global, not per adapter. Its changes
must be journalled *before* each addition. Existing mappings are never replaced.
No implicit downgrade to plaintext DNS is performed on unsupported Windows.

This module uses only the fixed GeoHide IPs and template, never user-controlled
PowerShell input. DoH implementation requires real Windows 11 acceptance tests.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from . import geohide

DOH_STATE_FILE = geohide.APP_DIR / 'doh-restore.json'

_CAPABILITY_SCRIPT = r'''
$ErrorActionPreference='Stop'
$required=@('Get-DnsClientDohServerAddress','Add-DnsClientDohServerAddress','Remove-DnsClientDohServerAddress')
foreach($cmd in $required) { if(-not (Get-Command $cmd -ErrorAction SilentlyContinue)) { throw 'Системный DoH не поддерживается этой версией Windows' } }
'available'
'''

_READ_SCRIPT = r'''
$ErrorActionPreference='Stop'
$items=@(Get-DnsClientDohServerAddress | Select-Object ServerAddress,DohTemplate,AutoUpgrade,AllowFallbackToUdp)
@($items) | ConvertTo-Json -Depth 5 -Compress
'''


def _journal_path(path: Path) -> Path:
    return DOH_STATE_FILE if path == geohide.STATE_FILE else path.with_name(path.stem + '-doh.json')


def _read_mappings() -> dict[str, dict]:
    """Return only GeoHide-IP mappings, including policy flags."""
    raw = json.loads(geohide._ps(_READ_SCRIPT) or '[]')
    entries = [] if raw is None else ([raw] if isinstance(raw, dict) else raw)
    if not isinstance(entries, list) or len(entries) > 1024:
        raise RuntimeError('Windows вернула некорректные данные DoH')
    mappings = {}
    for row in entries:
        if not isinstance(row, dict):
            raise RuntimeError('Windows вернула некорректную запись DoH')
        ip = row.get('ServerAddress')
        if ip not in geohide.GEOHIDE_IPV4:
            continue
        if ip in mappings or type(row.get('AutoUpgrade')) is not bool or type(row.get('AllowFallbackToUdp')) is not bool:
            raise RuntimeError('Windows вернула неоднозначную запись GeoHide DoH')
        template = row.get('DohTemplate')
        if not isinstance(template, str):
            raise RuntimeError('Windows вернула некорректный шаблон GeoHide DoH')
        mappings[ip] = {'template': template, 'upgrade': row['AutoUpgrade'],
                        'fallback': row['AllowFallbackToUdp']}
    return mappings


def _expected(entry: dict) -> bool:
    return (entry.get('template') == geohide.DOH_TEMPLATE and
            entry.get('upgrade') is True and entry.get('fallback') is False)


def _load_journal(path: Path) -> list[str]:
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data, dict) or data.get('provider') != 'geohide_doh' or data.get('version') != 1:
        raise ValueError('Некорректная резервная копия GeoHide DoH')
    addresses = data.get('created')
    if (not isinstance(addresses, list) or len(addresses) > len(geohide.GEOHIDE_IPV4) or
            len(set(str(x) for x in addresses)) != len(addresses) or
            any(type(x) is not str or x not in geohide.GEOHIDE_IPV4 for x in addresses)):
        raise ValueError('Некорректный список настроек GeoHide DoH')
    return addresses


def _save_journal(addresses: list[str], path: Path) -> None:
    if len(set(addresses)) != len(addresses) or any(x not in geohide.GEOHIDE_IPV4 for x in addresses):
        raise ValueError('Недопустимые адреса DoH')
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    with tmp.open('w', encoding='utf-8') as f:
        json.dump({'provider': 'geohide_doh', 'version': 1, 'created': addresses}, f)
        f.flush()
        os.fsync(f.fileno())
    tmp.replace(path)


def _add_mapping(ip: str) -> None:
    if ip not in geohide.GEOHIDE_IPV4:
        raise ValueError('Недопустимый адрес GeoHide DoH')
    geohide._ps('Add-DnsClientDohServerAddress -ServerAddress ' + "'" + ip + "'" +
                ' -DohTemplate ' + "'" + geohide.DOH_TEMPLATE + "'" +
                ' -AutoUpgrade $True -AllowFallbackToUdp $False -ErrorAction Stop')


def _remove_mapping(ip: str) -> None:
    if ip not in geohide.GEOHIDE_IPV4:
        raise ValueError('Недопустимый адрес GeoHide DoH')
    geohide._ps("Remove-DnsClientDohServerAddress -ServerAddress '" + ip +
                "' -Confirm:$False -ErrorAction Stop")


def restore_doh(path: Path = DOH_STATE_FILE) -> bool:
    """Remove only VORQELI-created mapping(s) still matching our exact profile.

    Externally changed mappings are NEVER overwritten/deleted; the journal
    stays on disk for user-assisted recovery. Missing mappings are fine.
    """
    if not path.is_file():
        return False
    owned = _load_journal(path)
    if not owned:
        path.unlink()
        return True
    current = _read_mappings()
    remaining = []
    failures = []
    for ip in owned:
        existing = current.get(ip)
        if existing is None:
            continue
        if not _expected(existing):
            remaining.append(ip)
            failures.append('DoH GeoHide изменён другой программой')
            continue
        try:
            _remove_mapping(ip)
        except Exception as exc:
            remaining.append(ip)
            failures.append('Не удалось удалить настройку DoH: ' + type(exc).__name__)
    try:
        after = _read_mappings()
    except Exception as exc:
        # Preserve full journal: Windows may have ignored a delete request.
        raise RuntimeError('Не удалось проверить удаление GeoHide DoH') from exc
    for ip in owned:
        if ip in after and ip not in remaining:
            remaining.append(ip)
            failures.append('Windows не подтвердила удаление GeoHide DoH')
    if remaining:
        if len(remaining) < len(owned):
            _save_journal(remaining, path)
        raise RuntimeError('DoH восстановлен не полностью: ' + '; '.join(failures))
    path.unlink()
    return True


def enable_secure_dns(path: Path = geohide.STATE_FILE, *, probe: bool = True) -> int:
    """Enable native encrypted DNS, failing closed when system support is absent.

    A write-ahead journal tracks exactly the DoH mappings this application
    intends to create. All external pre-existing mappings are left intact.
    """
    journal = _journal_path(path)
    if journal.exists():
        owned = _load_journal(journal)
        if not path.exists():
            raise RuntimeError('Остался журнал DoH после сбоя. Сначала восстановите DNS.')
        current = _read_mappings()
        if not all(_expected(current.get(ip, {})) for ip in geohide.GEOHIDE_IPV4):
            raise RuntimeError('Настройки GeoHide DoH изменились. Сначала восстановите DNS.')
        return geohide.enable_dns(path, probe=False)
    if path.exists():
        raise RuntimeError('Найдена резервная копия обычного DNS. Сначала восстановите DNS.')
    if probe:
        geohide._dns_probe()
    geohide._ps(_CAPABILITY_SCRIPT)
    # Validate before writing any registry or adapter configuration.
    before = _read_mappings()
    for ip in geohide.GEOHIDE_IPV4:
        if ip in before and not _expected(before[ip]):
            raise RuntimeError('В Windows уже настроен другой DoH для адреса GeoHide. Ничего не изменено.')
    to_create = [ip for ip in geohide.GEOHIDE_IPV4 if ip not in before]
    _save_journal(to_create, journal)
    try:
        for ip in to_create:
            _add_mapping(ip)
        after = _read_mappings()
        if not all(_expected(after.get(ip, {})) for ip in geohide.GEOHIDE_IPV4):
            raise RuntimeError('Windows не подтвердила настройку зашифрованного GeoHide DoH')
        return geohide.enable_dns(path, probe=False)
    except Exception as original:
        problems = []
        if path.exists():
            try:
                geohide.restore_dns(path)
            except Exception:
                problems.append('Не удалось восстановить DNS-адаптеры')
        # Do not remove an encrypted resolver while rollback is unresolved.
        if not path.exists():
            try:
                restore_doh(journal)
            except Exception:
                problems.append('Не удалось убрать системный DoH')
        if problems:
            raise RuntimeError('GeoHide DoH не подключён; требуется восстановление: ' + ', '.join(problems)) from original
        raise


def enable_geo_dns(*, mode: str = 'plain', path: Path = geohide.STATE_FILE, probe: bool = True) -> int:
    if mode == 'doh':
        return enable_secure_dns(path, probe=probe)
    if mode != 'plain':
        raise ValueError('Неизвестный режим GeoHide DNS')
    if _journal_path(path).exists():
        raise RuntimeError('Остались настройки DoH. Сначала восстановите GeoHide DNS.')
    return geohide.enable_dns(path, probe=probe)


def restore_geo_dns(path: Path = geohide.STATE_FILE) -> bool:
    journal = _journal_path(path)
    had_dns = path.is_file()
    had_doh = journal.is_file()
    # First restore adapter DNS; until successful, leave encrypted mappings.
    if had_dns:
        result = geohide.restore_dns(path)
        if result is not True or path.exists():
            raise RuntimeError('Windows не подтвердил восстановление DNS адаптеров')
    if had_doh:
        restore_doh(journal)
    return had_dns or had_doh
