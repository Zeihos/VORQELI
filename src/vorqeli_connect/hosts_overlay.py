"""Optional, explicit HOSTS overlay; GeoHide DNS is a separate resolver feature.

Never edit HOSTS during connection, launch, or shutdown. All modifications need
an affirmative user action. Preserve pre-existing manual lines verbatim; only
VORQELI-delimited additions can be removed. No automatic IP updates.
"""
from __future__ import annotations

import ipaddress
import os
import re
import tempfile
from pathlib import Path

START = '# VORQELI OPTIONAL HOSTS START'
END = '# VORQELI OPTIONAL HOSTS END'
_DOMAIN = re.compile(r'^[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)+$')
MAX_HOSTS_BYTES = 2 * 1024 * 1024


def hosts_path() -> Path:
    return Path(os.environ.get('SystemRoot', r'C:\Windows'))/'System32'/'drivers'/'etc'/'hosts'


def parse_mappings(source: str) -> dict[str, str]:
    records: dict[str, str] = {}
    for line in source.splitlines():
        clean = line.partition('#')[0].strip()
        if not clean:
            continue
        pieces = clean.split()
        if len(pieces) != 2:
            raise ValueError('Каждая HOSTS-запись должна содержать IP и один домен')
        ip, hostname = pieces
        try:
            ip = str(ipaddress.IPv4Address(ip))
        except ipaddress.AddressValueError as exc:
            raise ValueError('Недопустимый IPv4-адрес в HOSTS') from exc
        hostname = hostname.lower().rstrip('.')
        if len(hostname) > 253 or not _DOMAIN.fullmatch(hostname):
            raise ValueError('Недопустимый домен в HOSTS')
        if hostname in records and records[hostname] != ip:
            raise ValueError('В списке HOSTS противоречивые записи: ' + hostname)
        records[hostname] = ip
        if len(records) > 400:
            raise ValueError('Слишком много HOSTS-записей')
    if not records:
        raise ValueError('Список HOSTS пуст')
    return records


def _read(path: Path) -> str:
    if path.is_symlink() or (path.is_file() and path.stat().st_size > MAX_HOSTS_BYTES):
        raise ValueError('HOSTS содержит ссылку либо превышает предел размера')
    if not path.is_file():
        raise FileNotFoundError('Системный HOSTS не найден')
    return path.read_bytes().decode('utf-8', errors='surrogateescape')


def _managed_span(text: str) -> tuple[int, int] | None:
    if text.count(START) != text.count(END):
        raise ValueError('Повреждён блок VORQELI в HOSTS — ручная проверка обязательна')
    if not text.count(START):
        return None
    if text.count(START) != 1 or text.count(END) != 1:
        raise ValueError('Обнаружено несколько HOSTS-блоков VORQELI')
    begin = text.index(START)
    finish = text.index(END)
    if finish <= begin or (begin > 0 and text[begin-1] != '\n'):
        raise ValueError('Неизвестная структура HOSTS-блока VORQELI')
    # Delete through end of the managed line including its CRLF/LF.
    end = finish + len(END)
    if text[end:end+2] == '\r\n':
        end += 2
    elif text[end:end+1] == '\n':
        end += 1
    # Never trust an edited block with garbage before the END marker.
    block = text[begin:end]
    if block.count(START) != 1 or block.count(END) != 1:
        raise ValueError('Повреждён HOSTS-блок VORQELI')
    return (begin, end)


def analyze_hosts(existing: str, reference: str) -> dict[str, object]:
    mapping = parse_mappings(reference)
    span = _managed_span(existing)
    unmanaged = existing if span is None else existing[:span[0]] + existing[span[1]:]
    present: dict[str, str] = {}
    for raw in unmanaged.splitlines():
        bits = raw.partition('#')[0].split()
        if len(bits) < 2:
            continue
        try:
            ip = str(ipaddress.IPv4Address(bits[0]))
        except ipaddress.AddressValueError:
            continue
        for label in bits[1:]:
            present[label.lower().rstrip('.')] = ip
    conflict = {name: (old, ip) for name, ip in mapping.items()
                if (old := present.get(name)) is not None and old != ip}
    existing_matches = sum(present.get(name) == ip for name, ip in mapping.items())
    needed = {name: ip for name, ip in mapping.items() if name not in present}
    return {'count': len(mapping), 'existing': existing_matches,
            'conflicts': conflict, 'needed': needed, 'managed': span is not None}


def _replace(path: Path, value: str) -> None:
    """Atomic same-directory replacement: preserves unrelated HOSTS content."""
    fd, tmp_name = tempfile.mkstemp(prefix='.vorqeli-hosts-', dir=str(path.parent))
    temp = Path(tmp_name)
    try:
        with os.fdopen(fd, 'wb') as output:
            output.write(value.encode('utf-8', errors='surrogateescape'))
            output.flush()
            os.fsync(output.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def apply_optional_hosts(path: Path, reference: str) -> dict[str, object]:
    """Add only absent mappings; refuse conflicts and concurrent manual edits."""
    original = _read(path)
    status = analyze_hosts(original, reference)
    if status['conflicts']:
        raise ValueError(f'Найдены конфликтующие ручные записи HOSTS: {len(status["conflicts"])}')
    span = _managed_span(original)
    if span:
        # Never overwrite existing managed content; user must explicitly remove it.
        raise ValueError('HOSTS-блок VORQELI уже существует: сначала удалите его')
    needed = status['needed']
    if not needed:
        return status
    newline = '\r\n' if '\r\n' in original else '\n'
    prefix = '' if not original or original.endswith(('\r','\n')) else newline
    addition = newline.join([START, *(f'{ip} {name}' for name, ip in needed.items()), END, ''])
    # Re-read before mutation; block optimistic collision.
    if _read(path) != original:
        raise RuntimeError('HOSTS изменился во время проверки, повторите действие')
    _replace(path, original + prefix + addition)
    return status


def remove_optional_hosts(path: Path) -> bool:
    original = _read(path)
    span = _managed_span(original)
    if span is None:
        return False
    new = original[:span[0]] + original[span[1]:]
    if _read(path) != original:
        raise RuntimeError('HOSTS изменился во время проверки, повторите действие')
    _replace(path, new)
    return True
