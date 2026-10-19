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

TARGET_DOMAINS = ('youtube.com', 'googlevideo.com', 'discord.com', 'discordapp.com', 'telegram.org',
                  'chatgpt.com', 'openai.com', 'claude.ai', 'anthropic.com')
AI_DOMAINS = ('chatgpt.com', 'claude.ai')
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


def parse_default_route_aliases(output: str) -> list[str]:
    """Read only IPv4 default-route candidates, not a claim about browser routing."""
    raw = json.loads(output or '[]')
    if raw is None:
        return []
    if isinstance(raw, dict):
        raw = [raw]
    if not isinstance(raw, list):
        raise ValueError('Неизвестный формат маршрутов Windows')
    aliases: list[str] = []
    for item in raw[:64]:
        if not isinstance(item, dict):
            continue
        alias = item.get('InterfaceAlias')
        if isinstance(alias, str) and alias.strip() and alias not in aliases:
            aliases.append(alias[:80])
    return aliases[:16]


def default_route_dns_status(adapters: list[dict[str, Any]], routes: list[str]) -> str:
    """Check *every* default-route candidate, never just any unrelated NIC."""
    if not routes:
        return 'unknown'
    known = {str(a.get('alias', '')).casefold(): tuple(a.get('servers', ()))
             for a in adapters}
    values = [known.get(route.casefold()) for route in routes]
    if any(v is None for v in values):
        return 'unknown'  # An unenumerated VPN/virtual interface may own DNS.
    good = sum(set(GEOHIDE_IPV4).issubset(set(v)) for v in values)
    return 'all' if good == len(values) else 'partial' if good else 'none'


def _default_route_aliases() -> list[str]:
    script = ("$ErrorActionPreference='Stop'; "
              "$r=@(Get-NetRoute -AddressFamily IPv4 -DestinationPrefix '0.0.0.0/0' "
              "-ErrorAction Stop | Select-Object InterfaceAlias); "
              "ConvertTo-Json -InputObject $r -Depth 3 -Compress")
    return parse_default_route_aliases(_powershell(script))


def _direct_ai_dns(server: str, domain: str) -> str:
    """A-record probe against a fixed GeoHide resolver; no hosts or OS mutations."""
    if server not in GEOHIDE_IPV4 or domain not in AI_DOMAINS:
        raise ValueError('Недопустимая цель диагностики DNS')
    script = ("$ErrorActionPreference='Stop'; "
              f"$r=@(Resolve-DnsName -Name '{domain}' -Type A "
              f"-Server '{server}' -NoHostsFile -DnsOnly -ErrorAction Stop | "
              "Where-Object { $_.Type -eq 'A' -and $_.IPAddress }); "
              "if($r.Count -eq 0){throw 'Нет A-ответа'}; 'Ответ получен'")
    _powershell(script, timeout=8)
    return 'Ответ получен'


def _doh_profile_verified() -> bool:
    """Check Windows DoH templates/flags, not TLS traffic effectiveness."""
    from .geohide_doh import _expected, _read_mappings
    mapping = _read_mappings()
    return all(_expected(mapping.get(ip, {})) for ip in GEOHIDE_IPV4)


def run_dns_audit(*, deep: bool = False) -> dict[str, Any]:
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
    if deep:
        report['ai_dns'] = {domain: {} for domain in AI_DOMAINS}
        report['default_routes'] = []
        report['default_route_dns'] = 'unknown'
        report['selected_mode'] = 'unknown'
        report['doh_profile_verified'] = None
        # Explicitly user-triggered from the diagnostics window. No periodic
        # polling or changes to DNS/hosts/registry; errors are isolated.
        try:
            from .config import load_settings
            settings = load_settings()
            report['selected_mode'] = (settings.dns_mode if settings.connect_dns
                                       else 'disabled')
        except (OSError, ValueError, TypeError) as exc:
            report['errors'].append('Режим GeoHide: ' + type(exc).__name__)
        try:
            report['default_routes'] = _default_route_aliases()
            report['default_route_dns'] = default_route_dns_status(
                report['adapters'], report['default_routes'])
        except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
            report['errors'].append('Маршрут IPv4: ' + type(exc).__name__)
        if report['selected_mode'] == 'doh':
            try:
                report['doh_profile_verified'] = _doh_profile_verified()
            except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
                report['errors'].append('Настройки DoH Windows: ' + type(exc).__name__)
        # A DNS response is NOT proof of site access: no login or HTTPS probe.
        # Execute four independent fixed-target probes concurrently to avoid
        # 32-second serial delays if the network is unavailable.
        from concurrent.futures import ThreadPoolExecutor
        checks = tuple((domain, server) for domain in AI_DOMAINS for server in GEOHIDE_IPV4)
        def one_check(pair: tuple[str, str]) -> tuple[str, str, str]:
            domain, server = pair
            try:
                result = _direct_ai_dns(server, domain)
            except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
                result = 'Нет ответа (' + type(exc).__name__ + ')'
            return domain, server, result
        with ThreadPoolExecutor(max_workers=4) as executor:
            for domain, server, result in executor.map(one_check, checks):
                report['ai_dns'][domain][server] = result
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
    if 'ai_dns' in data:
        lines.extend(['', '4. CHATGPT / CLAUDE: ПРОВЕРКА GEOHIDE (БЕЗ HOSTS)'])
        lines.append('Выбранный режим: ' + str(data.get('selected_mode', 'unknown')))
        candidates = data.get('default_routes', [])
        status = data.get('default_route_dns', 'unknown')
        lines.append('DNS на адаптерах маршрута по умолчанию: ' + {
            'all': 'GeoHide найден на всех обнаруженных маршрутах',
            'partial': 'GeoHide найден не на всех маршрутах',
            'none': 'GeoHide не найден на маршрутах',
            'unknown': 'не удалось однозначно проверить (возможен VPN/виртуальный адаптер)',
        }.get(status, 'неизвестно'))
        if candidates:
            lines.append('Адаптеры маршрутов: ' + ', '.join(candidates[:8]))
        if data.get('selected_mode') == 'doh':
            lines.append('Шаблоны DoH Windows: ' + (
                'проверены' if data.get('doh_profile_verified') is True else
                'не совпадают' if data.get('doh_profile_verified') is False else
                'не удалось проверить'))
        else:
            lines.append('Зашифрованный DoH не выбран в настройках VORQELI.')
        for domain in AI_DOMAINS:
            for server in GEOHIDE_IPV4:
                lines.append('  ' + domain + ' @ ' + server + ': ' +
                             data.get('ai_dns', {}).get(domain, {}).get(server, 'Не проверено'))
        lines.append('Это проверяет только DNS A-ответы, а не авторизацию, HTTPS или геоблокировку.')
        lines.append('IPv6 и Secure DNS в браузере могут обходить заданный IPv4 DNS.')
    for error in data.get('errors', []):
        lines.extend(['', 'Ошибка проверки: ' + error])
    lines.extend(['', 'ВАЖНО',
                  'DNS-ответ не подтверждает обход DPI или работу видео.',
                  'Браузерный Secure DNS / DoH может не использовать системный DNS.',
                  'Для проверки DPI сравните доступность сайта при отключённом и включённом DPI.',
                  'Не удаляйте файл hosts целиком; сначала сохраните резервную копию.'])
    return '\n'.join(lines)
