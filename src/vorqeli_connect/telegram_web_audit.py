"""Read-only, direct Telegram Web reachability and HOSTS/DNS diagnostics.

A working local MTProto proxy is unrelated to browser access to Telegram Web.
All probes are user-initiated, use a bounded number of fixed HTTPS targets,
ignore environment HTTP proxy settings, and never change network/hosts state.
Neither a TLS handshake nor a successful HTTP response proves that the SPA
has initialized or that Telegram messages can be sent.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from http.client import HTTPSConnection
import ipaddress
import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
from typing import Callable

# Hostnames/paths are intentionally fixed, not taken from external files.
WEB_TARGETS = (
    ('Telegram Web K', 'web.telegram.org', '/k/'),
    ('Telegram Web A', 'web.telegram.org', '/a/'),
    ('K-клиент · gateway', 'kws2.web.telegram.org', '/'),
    ('A-клиент · gateway', 'zws4.web.telegram.org', '/'),
)
HOSTS_DOMAINS = frozenset(host for _, host, _ in WEB_TARGETS)


def parse_telegram_hosts(text: str) -> dict[str, tuple[str, ...]]:
    """Read the exact relevant hosts entries, including multiple addresses.

    Only recognize complete hostnames; do not mistake foo.web.telegram.org.evil
    for a Telegram domain, and do not assume a hosts line is being used by the
    browser (which may use a proxy or its own Secure DNS).
    """
    found: dict[str, set[str]] = {}
    for raw in text.splitlines():
        parts = raw.split('#', 1)[0].split()
        if len(parts) < 2:
            continue
        try:
            ip = str(ipaddress.ip_address(parts[0]))
        except ValueError:
            continue
        for entry in parts[1:]:
            host = entry.rstrip('.').lower()
            if host in HOSTS_DOMAINS:
                found.setdefault(host, set()).add(ip)
    return {host: tuple(sorted(ips)) for host, ips in sorted(found.items())}


def _system_hosts_file() -> Path:
    return (Path(os.environ.get('SystemRoot', r'C:\Windows')) /
            'System32' / 'drivers' / 'etc' / 'hosts')


def _read_hosts(path: Path) -> dict[str, tuple[str, ...]]:
    if path.is_symlink() or path.stat().st_size > 1024 * 1024:
        raise ValueError('HOSTS является ссылкой либо превышает 1 МБ')
    return parse_telegram_hosts(path.read_text(encoding='utf-8-sig', errors='replace'))


def probe_https(host: str, path: str, *, timeout: float = 4.0) -> tuple[str, str]:
    """Connect directly with verified TLS/SNI; no browser, system or env proxy.

    Returns a bounded status and detail without leaking network exception text.
    4xx/5xx are differentiated from a network failure. No redirect is followed.
    """
    if (host, path) not in {(h, p) for _, h, p in WEB_TARGETS}:
        raise ValueError('Проверка разрешена только для Telegram Web')
    connection = HTTPSConnection(host, 443, timeout=timeout, context=ssl.create_default_context())
    try:
        connection.request('GET', path, headers={
            'User-Agent': 'VORQELI-Connect/0.36 TelegramWebCheck',
            'Accept': 'text/html,*/*;q=0.5',
            'Connection': 'close',
        })
        response = connection.getresponse()
        # Drain only a tiny portion; avoid unnecessary app bundle downloads.
        response.read(512)
        status = int(response.status)
        if 200 <= status < 400:
            return ('ok', f'HTTPS отвечает (HTTP {status})')
        return ('http', f'Сервер ответил HTTP {status}')
    except socket.gaierror:
        return ('dns', 'Имя не разрешается в IP')
    except ssl.SSLCertVerificationError:
        return ('tls', 'Ошибка проверки TLS-сертификата')
    except ssl.SSLError:
        return ('tls', 'Не удалось установить TLS-соединение')
    except (TimeoutError, socket.timeout):
        return ('timeout', 'Превышено время ожидания')
    except (OSError, ConnectionError):
        return ('network', 'Ошибка TCP/HTTPS-соединения')
    finally:
        connection.close()


def dns_without_hosts(host: str = 'web.telegram.org') -> tuple[str, ...]:
    """Read A records via Windows DNS Client, bypassing HOSTS (no changes)."""
    if host != 'web.telegram.org':
        raise ValueError('Неизвестный домен для DNS-проверки')
    if os.name != 'nt':
        raise OSError('Доступно только на Windows')
    ps = ("$ErrorActionPreference='Stop'; "
          "$a=@(Resolve-DnsName -Name 'web.telegram.org' -Type A "
          "-NoHostsFile -DnsOnly -ErrorAction Stop | "
          "Where-Object { $_.Type -eq 'A' -and $_.IPAddress } | "
          "Select-Object -ExpandProperty IPAddress); "
          "$a | ConvertTo-Json -Compress")
    result = subprocess.run(
        ['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', ps],
        capture_output=True, text=True, timeout=8,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
    )
    if result.returncode:
        raise RuntimeError('Запрос DNS без HOSTS не выполнен')
    value = json.loads(result.stdout.strip() or 'null')
    values = [value] if isinstance(value, str) else value
    if not isinstance(values, list):
        return ()
    addresses: set[str] = set()
    for item in values[:16]:
        try:
            if isinstance(item, str):
                addresses.add(str(ipaddress.IPv4Address(item)))
        except ValueError:
            continue
    return tuple(sorted(addresses))


def audit_telegram_web(*, hosts_file: Path | None = None,
                       request: Callable[[str, str], tuple[str, str]] = probe_https,
                       resolver: Callable[[], tuple[str, ...]] = dns_without_hosts,
                       windows: bool | None = None) -> dict:
    """Independent failures must not suppress the other diagnostic results."""
    result = {'hosts': {}, 'dns_without_hosts': None, 'dns_error': None,
              'checks': [], 'errors': []}
    path = hosts_file if hosts_file is not None else _system_hosts_file()
    try:
        result['hosts'] = _read_hosts(path)
    except (OSError, ValueError, UnicodeError) as exc:
        result['errors'].append('HOSTS недоступен: ' + type(exc).__name__)
    if windows is None:
        windows = os.name == 'nt'
    if windows:
        try:
            result['dns_without_hosts'] = tuple(resolver())
        except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
            result['dns_error'] = type(exc).__name__
    # Four bounded checks, concurrently. No effect on Windows DNS or proxy.
    with ThreadPoolExecutor(max_workers=4) as pool:
        tasks = [pool.submit(request, host, url_path) for _, host, url_path in WEB_TARGETS]
        for (label, host, url_path), task in zip(WEB_TARGETS, tasks):
            try:
                state, detail = task.result()
                if state not in ('ok', 'http', 'dns', 'tls', 'timeout', 'network'):
                    state, detail = 'network', 'Некорректный результат проверки'
            except Exception:
                state, detail = 'network', 'Проверка завершилась ошибкой'
            result['checks'].append({'name': label, 'host': host, 'path': url_path,
                                     'state': state, 'detail': str(detail)[:90]})
    return result


def format_telegram_web_audit(report: dict) -> str:
    """Human-readable, non-assertive results for an in-app diagnostic window."""
    lines = ['VORQELI  /  TELEGRAM WEB',
             'Проверка только чтением: DNS, HOSTS, прямое HTTPS-соединение.',
             'Работающий MTProto-прокси НЕ означает доступности Telegram Web.',
             '', '1. БРАУЗЕРНЫЕ АДРЕСА (ПРЯМОЕ HTTPS, БЕЗ ПРОКСИ)']
    symbols = {'ok': 'OK', 'http': 'HTTP', 'dns': 'DNS',
               'tls': 'TLS', 'timeout': 'TIMEOUT', 'network': 'СЕТЬ'}
    for item in report.get('checks', []):
        lines.append(f'  [{symbols.get(item.get("state"), "?")}] {item["name"]}: {item["detail"]}')
    lines.extend(['', '2. ПЕРЕОПРЕДЕЛЕНИЯ В WINDOWS HOSTS'])
    mappings = report.get('hosts', {})
    if mappings:
        for host, ips in mappings.items():
            lines.append('  ' + host + ' → ' + ', '.join(ips))
        lines.append('  HOSTS может заставлять систему обращаться к фиксированному IP.')
    else:
        lines.append('  Записей для проверяемых веб-доменов не найдено.')
    lines.extend(['', '3. DNS В ОБХОД HOSTS (WINDOWS)'])
    ips = report.get('dns_without_hosts')
    if ips is None:
        lines.append('  Не проверено' + (' (' + report['dns_error'] + ')' if report.get('dns_error') else ''))
    elif ips:
        lines.append('  web.telegram.org → ' + ', '.join(ips))
        fixed = set(mappings.get('web.telegram.org', ()))
        if fixed and not fixed.intersection(ips):
            lines.append('  ВНИМАНИЕ: HOSTS и DNS возвращают разные IP. Это не обязательно ошибка,')
            lines.append('  но статический HOSTS может мешать загрузке Telegram Web.')
    else:
        lines.append('  DNS не вернул A-записей.')
    for msg in report.get('errors', []):
        lines.append('  ' + str(msg)[:120])
    lines.extend(['', 'ЧТО ЗНАЧИТ РЕЗУЛЬТАТ',
                  '  HTTPS OK: сервер отвечает, но работа веб-клиента не доказана.',
                  '  HTTP: сервер достижим, однако запрос вернул ошибку.',
                  '  TLS: проверьте сертификат, HOSTS и выбранный адрес.',
                  '  DNS: проверьте системный DNS, HOSTS и Secure DNS браузера.',
                  '  Браузер может пользоваться своим DoH, прокси или HTTP/3.',
                  '  Эта проверка не отключает ваш работающий DPI или Telegram-прокси.',
                  '  Не удаляйте личные HOSTS-записи без резервной копии.'])
    return '\n'.join(lines)
