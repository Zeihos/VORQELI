"""Read-only Windows DNS / hosts audit for VORQELI.

Checks configured resolver addresses, local hosts overrides, and direct queries
against GeoHide servers. Results do NOT certify DPI bypass or browser routing.
This module never changes DNS, hosts, routing, firewall, or registry.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
from typing import Any

from .geohide import GEOHIDE_IPV4

TARGET_DOMAINS = ('youtube.com', 'googlevideo.com', 'discord.com', 'discordapp.com', 'telegram.org')
DNS_TEST_DOMAIN = 'youtube.com'


def affected_hosts(text: str, domains: tuple[str, ...] = TARGET_DOMAINS) -> list[str]:
    """Return matched hostnames, never expose the user's custom host IPs."""
    found: set[str] = set()
    for raw in text.splitlines():
        line = raw.split('#', 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        for label in parts[1:]:
            label = label.lower().rstrip('.')
            if any(label == domain or label.endswith('.' + domain) for domain in domains):
                found.add(label)
    return sorted(found)


def parse_dns_snapshot(output: str) -> list[dict[str, Any]]:
    """Accept ConvertTo-Json empty, singleton, and multi-item representations."""
    content = json.loads(output or '[]')
    if isinstance(content, dict):
        content = [content]
    if not isinstance(content, list):
        raise ValueError('Некорректный ответ DNS Windows')
    entries = []
    for item in content:
        if not isinstance(item, dict):
            continue
        raw = item.get('ServerAddresses') or []
        if isinstance(raw, str):
            raw = [raw]
        if not isinstance(raw, list):
            continue
        servers = [x for x in raw if isinstance(x, str)]
        entries.append({'alias': str(item.get('InterfaceAlias') or 'Адаптер')[:80],
                        'servers': servers[:8]})
    return entries[:32]


def geohide_configured(adapters: list[dict[str, Any]]) -> bool:
    expected = set(GEOHIDE_IPV4)
    return any(expected.issubset(set(a.get('servers', []))) for a in adapters)


def _powershell(script: str, timeout: int = 12) -> str:
    flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script],
                            capture_output=True, text=True, timeout=timeout, creationflags=flags)
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout or 'PowerShell error').strip()[-320:])
    return result.stdout.strip()


def _windows_hosts_path() -> Path:
    return Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32' / 'drivers' / 'etc' / 'hosts'


def _hosts_matches() -> list[str]:
    path = _windows_hosts_path()
    if not path.is_file():
        return []
    if path.stat().st_size > 1024 * 1024:
        raise ValueError('Файл hosts больше 1 МБ; автоматический анализ пропущен')
    return affected_hosts(path.read_text(encoding='utf-8-sig', errors='replace'))


def _system_dns() -> list[dict[str, Any]]:
    script = ("$ErrorActionPreference='Stop'; "
              "$a=@(Get-DnsClientServerAddress -AddressFamily IPv4 | "
              "Where-Object { $_.ServerAddresses.Count -gt 0 } | "
              "Select-Object InterfaceAlias,ServerAddresses); "
              "ConvertTo-Json -InputObject $a -Depth 4 -Compress")
    return parse_dns_snapshot(_powershell(script))


def _direct_dns(server: str) -> str:
    # Only constant, known addresses from GEOHIDE_IPV4 can reach this function.
    if server not in GEOHIDE_IPV4:
        raise ValueError('DNS-сервер не разрешён')
    script = ("$ErrorActionPreference='Stop'; "
              f"$a=@(Resolve-DnsName -Name '{DNS_TEST_DOMAIN}' -Type A "
              f"-Server '{server}' -NoHostsFile -DnsOnly -ErrorAction Stop | "
              "Where-Object { $_.Type -eq 'A' -and $_.IPAddress }); "
              "if ($a.Count -eq 0) { throw 'Нет DNS A-ответа' }; "
              "'DNS A-ответ получен'")
    _powershell(script, timeout=10)
    return 'Ответ получен'


def run_dns_audit() -> dict[str, Any]:
    """Best-effort read-only audit, each failure isolated and visible to user."""
    report: dict[str, Any] = {'platform': os.name, 'adapters': [],
                              'dns_configured': None, 'hosts': [], 'direct': {}, 'errors': []}
    if os.name != 'nt':
        report['errors'].append('Проверка доступна только на Windows')
        return report
    try:
        report['hosts'] = _hosts_matches()
    except (OSError, ValueError) as exc:
        report['errors'].append('hosts: ' + str(exc)[:160])
    try:
        report['adapters'] = _system_dns()
        report['dns_configured'] = geohide_configured(report['adapters'])
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        report['errors'].append('Системный DNS: ' + str(exc)[:160])
    for server in GEOHIDE_IPV4:
        try:
            report['direct'][server] = _direct_dns(server)
        except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
            report['direct'][server] = 'Нет ответа (' + type(exc).__name__ + ')'
    return report


def format_dns_audit(data: dict[str, Any]) -> str:
    """Readable dashboard; explicitly separates configured state and function."""
    lines = ['VORQELI · ПРОВЕРКА GEOHIDE / HOSTS',
             'Только чтение. Сетевые настройки не изменяются.',
             '', '1. СИСТЕМНЫЕ DNS-СЕРВЕРЫ']
    value = data.get('dns_configured')
    if value is True:
        lines.append('GeoHide IPv4 указан в настройках DNS хотя бы одного адаптера.')
    elif value is False:
        lines.append('Пара DNS GeoHide не обнаружена в настройках DNS адаптеров.')
    else:
        lines.append('Не удалось определить активные DNS-серверы.')
    for entry in data.get('adapters', []):
        lines.append(f"  {entry['alias']}: {', '.join(entry['servers']) or 'нет IPv4 DNS'}")
    lines.extend(['', '2. ПРЯМЫЕ DNS-ЗАПРОСЫ К GEOHIDE (БЕЗ HOSTS)'])
    for server in GEOHIDE_IPV4:
        lines.append('  ' + server + ': ' + data.get('direct', {}).get(server, 'Не проверено'))
    lines.extend(['', '3. ЛОКАЛЬНЫЙ ФАЙЛ HOSTS'])
    names = data.get('hosts', [])
    if names:
        lines.append(f'Найдены ручные записи для {len(names)} проверяемых доменов:')
        lines.extend('  • ' + name for name in names[:25])
        lines.append('Сравнение с DNS может быть недостоверным: hosts переопределяет имена.')
    else:
        lines.append('Записей для YouTube, Discord, Telegram не обнаружено (или чтение не удалось).')
    for error in data.get('errors', []):
        lines.extend(['', 'Ошибка проверки: ' + error])
    lines.extend(['', 'ВАЖНО',
                  'DNS-ответ не подтверждает обход DPI или работу видео.',
                  'Браузерный Secure DNS / DoH может не использовать системный DNS.',
                  'Для проверки DPI сравните доступность сайта при отключённом и включённом DPI.',
                  'Не удаляйте файл hosts целиком; сначала сохраните резервную копию.'])
    return '\n'.join(lines)
