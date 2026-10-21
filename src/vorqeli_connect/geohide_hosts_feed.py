"""Official GeoHide RU classic HOSTS import with explicit consent and reversible overlay.

Only a user-confirmed action mutates system HOSTS. The bundled optional HOSTS
block is merged non-destructively and can be restored when GeoHide is removed.
This module does not change adapter DNS, proxy, WinWS or Telegram processes.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import ipaddress
import json
import os
from pathlib import Path
import re
import tempfile
from urllib.error import HTTPError
from urllib.request import Request, build_opener, HTTPRedirectHandler, ProxyHandler

SOURCE_URL = 'https://raw.githubusercontent.com/Internet-Helper/GeoHideDNS/main/hosts/hosts'
SOURCE_PAGE = 'https://github.com/Internet-Helper/GeoHideDNS/blob/main/hosts/hosts'
START = '# VORQELI GEOHIDE HOSTS START'
END = '# VORQELI GEOHIDE HOSTS END'
LEGACY_START = '# VORQELI OPTIONAL HOSTS START'
LEGACY_END = '# VORQELI OPTIONAL HOSTS END'
MAX_SOURCE = 1024 * 1024
MAX_HOSTS = 2 * 1024 * 1024
MAX_MAPPINGS = 10000
HOST_RE = re.compile(r'(?i)^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+$')
REGION_RE = re.compile(r'^# Регион серверов:\s*RU\s*$', re.M)
UPDATED_RE = re.compile(r'^# Последнее обновление:\s*([^\r\n]+)', re.M)
SHA_LINE = '# CONTENT SHA256: '


@dataclass(frozen=True)
class Snapshot:
    records: tuple[tuple[str, str], ...]
    updated: str
    sha256: str
    domain_count: int


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        raise ValueError('GeoHide source redirected: refused')


def fetch_official(timeout: int = 12) -> str:
    """Download only the published GitHub raw URL, with bounded streaming."""
    if not 1 <= timeout <= 45:
        raise ValueError('Invalid timeout')
    opener = build_opener(ProxyHandler({}), NoRedirect())
    request = Request(SOURCE_URL, headers={'Accept': 'text/plain',
                                          'User-Agent': 'VORQELI-Connect-GeoHide/0.39'})
    with opener.open(request, timeout=timeout) as response:
        if response.geturl() != SOURCE_URL or response.status != 200:
            raise ValueError('Unexpected GeoHide source response')
        data = response.read(MAX_SOURCE + 1)
    if len(data) > MAX_SOURCE:
        raise ValueError('GeoHide source is oversized')
    return data.decode('utf-8-sig', errors='strict')


def parse_official(text: str, *, min_domains: int = 200) -> Snapshot:
    """Retain all official public IP alternatives and reject malformed feeds."""
    if not isinstance(text, str) or len(text.encode('utf-8')) > MAX_SOURCE:
        raise ValueError('Invalid GeoHide source length')
    if not text.startswith('### geohide.ru: hosts file') or not REGION_RE.search(text):
        raise ValueError('Not the official GeoHide RU classic HOSTS format')
    if '### geohide.ru: end hosts file' not in text:
        raise ValueError('GeoHide source is incomplete')
    updated = UPDATED_RE.search(text)
    if not updated:
        raise ValueError('GeoHide update timestamp missing')
    result = []
    seen = set()
    domains = set()
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.partition('#')[0].strip()
        if not line:
            continue
        bits = line.split()
        if len(bits) != 2:
            raise ValueError(f'Incorrect GeoHide HOSTS entry at line {number}')
        ip, host = bits
        host = host.rstrip('.').lower()
        try:
            address = ipaddress.ip_address(ip)
        except ValueError as exc:
            raise ValueError(f'Invalid GeoHide IP at line {number}') from exc
        # Never replace local loopback/OS names from an external feed.
        if host in ('localhost', 'ip6-localhost'):
            continue
        if not HOST_RE.fullmatch(host) or len(host) > 253:
            raise ValueError(f'Invalid GeoHide domain at line {number}')
        if not address.is_global:
            raise ValueError(f'GeoHide contains non-public IP at line {number}')
        record = (str(address), host)
        if record not in seen:
            result.append(record)
            seen.add(record)
            domains.add(host)
        if len(result) > MAX_MAPPINGS:
            raise ValueError('GeoHide source contains too many mappings')
    if len(domains) < min_domains:
        raise ValueError('GeoHide source is truncated or unexpectedly small')
    return Snapshot(tuple(result), updated.group(1).strip(), sha256(text.encode('utf-8')).hexdigest(),len(domains))


def _bytes(path: Path, *, optional: bool = False) -> bytes:
    if path.is_symlink():
        raise ValueError('Refusing a symlink')
    if not path.exists():
        if optional:
            return b''
        raise FileNotFoundError('System HOSTS file not found')
    if not path.is_file() or path.stat().st_size > MAX_HOSTS:
        raise ValueError('HOSTS file type or size is invalid')
    return path.read_bytes()


def _decode(data: bytes) -> str:
    return data.decode('utf-8', errors='surrogateescape')


def _encode(data: str) -> bytes:
    return data.encode('utf-8', errors='surrogateescape')


def _span(text: str, start: str, end: str) -> tuple[int, int] | None:
    if text.count(start) != text.count(end):
        raise ValueError('HOSTS managed section has unmatched markers')
    if not text.count(start):
        return None
    if text.count(start) != 1 or text.count(end) != 1:
        raise ValueError('HOSTS contains repeated managed markers')
    at = text.find(start)
    close = text.find(end)
    if close <= at or (at and text[at-1] not in ('\r', '\n')):
        raise ValueError('Malformed HOSTS block')
    tail = close + len(end)
    if text[tail:tail+2] == '\r\n':tail += 2
    elif text[tail:tail+1] == '\n':tail += 1
    if text[at:tail].splitlines()[0] != start or end not in text[at:tail].splitlines():
        raise ValueError('HOSTS markers are not on their own lines')
    return at, tail


def _outside(existing: str) -> tuple[str, str, str]:
    geo = _span(existing, START, END)
    legacy = _span(existing, LEGACY_START, LEGACY_END)
    if geo and legacy and not (geo[1] <= legacy[0] or legacy[1] <= geo[0]):
        raise ValueError('Overlapping managed HOSTS sections')
    blocks = sorted([(p, name) for p,name in ((geo,'geo'),(legacy,'legacy')) if p], reverse=True)
    remaining = existing
    saved = {'geo':'', 'legacy':''}
    for (begin,finish),name in blocks:
        saved[name]=remaining[begin:finish]
        remaining=remaining[:begin]+remaining[finish:]
    return remaining,saved['geo'],saved['legacy']


def _assert_known_geo_block(block: str, journal: dict | None) -> None:
    if not block:
        return
    if not journal or not isinstance(journal.get('active_block_sha256'), str):
        raise ValueError('Existing GeoHide section has no trusted recovery journal')
    if sha256(_encode(block)).hexdigest() != journal['active_block_sha256']:
        raise ValueError('GeoHide section was edited outside VORQELI: refusing overwrite')


def _unmanaged_domains(content: str) -> set[str]:
    result = set()
    for line in content.splitlines():
        bits = line.partition('#')[0].split()
        if len(bits) < 2:
            continue
        try:
            ipaddress.ip_address(bits[0])
        except ValueError:
            continue
        for name in bits[1:]:
            result.add(name.lower().rstrip('.'))
    return result


def _legacy_records(block: str, fallback: str) -> list[tuple[str,str]]:
    """Preserve the prior VORQELI HOSTS block or the bundled Telegram set.

    Official GeoHide wins on overlapping domains; other legacy lines remain.
    """
    text = block or fallback
    result = []
    for row in text.splitlines():
        bits = row.partition('#')[0].strip().split()
        if len(bits) != 2:
            continue
        try:
            addr=ipaddress.ip_address(bits[0]);name=bits[1].lower().rstrip('.')
        except ValueError:
            continue
        if addr.is_global and HOST_RE.fullmatch(name):
            result.append((str(addr),name))
    return result


def _make_block(records: list[tuple[str,str]], snapshot: Snapshot) -> str:
    data = '\n'.join(f'{ip} {domain}' for ip,domain in records) + '\n'
    digest=sha256(data.encode('utf-8')).hexdigest()
    return '\n'.join([START, '# Source: '+SOURCE_PAGE,
                      '# RU updated: '+snapshot.updated,
                      '# Source SHA256: '+snapshot.sha256,
                      SHA_LINE+digest, data.rstrip('\n'), END,''])


def _journal_read(path: Path) -> dict | None:
    raw = _bytes(path, optional=True)
    if not raw:
        return None
    if len(raw)>MAX_HOSTS:
        raise ValueError('Invalid GeoHide journal')
    d=json.loads(raw.decode('utf-8'))
    if not isinstance(d, dict) or d.get('schema')!=1:
        raise ValueError('Invalid GeoHide journal schema')
    if not isinstance(d.get('legacy_block'),str) or len(d['legacy_block'])>MAX_HOSTS:
        raise ValueError('Invalid GeoHide recovery block')
    return d


def _atomic(path: Path, raw: bytes, *, expected: bytes | None = None) -> None:
    # Recheck to avoid replacing concurrent manual changes.
    if expected is not None and _bytes(path,optional=True)!=expected:
        raise RuntimeError('HOSTS changed since preview; repeat the operation')
    path.parent.mkdir(parents=True,exist_ok=True)
    fd, fname=tempfile.mkstemp(prefix='.vorqeli-geo-',dir=str(path.parent))
    temp=Path(fname)
    try:
        with os.fdopen(fd,'wb') as out:
            out.write(raw);out.flush();os.fsync(out.fileno())
        if expected is not None and _bytes(path,optional=True)!=expected:
            raise RuntimeError('HOSTS changed during update')
        os.replace(temp,path)
    finally:
        temp.unlink(missing_ok=True)


def preview(existing: str, snapshot: Snapshot, legacy_fallback: str = '', journal: dict | None = None) -> dict:
    unmanaged,geo,old_legacy = _outside(existing)
    _assert_known_geo_block(geo,journal)
    preserved=_unmanaged_domains(unmanaged)
    official_domains={name for _,name in snapshot.records}
    official=[(ip,name) for ip,name in snapshot.records if name not in preserved]
    old_legacy = (journal['legacy_block'] if geo and journal else old_legacy)
    legacy=[(ip,name) for ip,name in _legacy_records(old_legacy,legacy_fallback)
            if name not in official_domains and name not in preserved]
    unique=[];seen=set()
    for record in official+legacy:
        if record not in seen:
            seen.add(record);unique.append(record)
    block = _make_block(unique,snapshot)
    newline='\r\n' if '\r\n' in existing else '\n'
    separator='' if not unmanaged or unmanaged.endswith(('\r','\n')) else newline
    result=unmanaged+separator+block.replace('\n',newline)
    if len(_encode(result))>MAX_HOSTS:
        raise ValueError('Final HOSTS would exceed size limit')
    return {'content':result,'new_block':block.replace('\n',newline),
            'legacy_block':old_legacy,'official_entries':len(official),
            'legacy_entries':len(legacy),'protected_domains':len(official_domains&preserved),
            'unique_domains':len({n for _,n in unique}),'source_updated':snapshot.updated}


def apply(path: Path, snapshot: Snapshot, journal_path: Path, legacy_fallback: str = '') -> dict:
    before=_bytes(path)
    journal=_journal_read(journal_path)
    plan=preview(_decode(before),snapshot,legacy_fallback,journal)
    # Journal first, to leave a recovery trail before touching system HOSTS.
    new_journal={'schema':1,'legacy_block':plan['legacy_block'],
                 'active_block_sha256':sha256(_encode(plan['new_block'])).hexdigest(),
                 'source_sha256':snapshot.sha256,'updated':snapshot.updated}
    journal_old=_bytes(journal_path,optional=True)
    _atomic(journal_path,(json.dumps(new_journal,ensure_ascii=False,indent=2)+'\n').encode('utf-8'),expected=journal_old)
    try:
        _atomic(path,_encode(plan['content']),expected=before)
    except BaseException:
        # Journal is needed for recovery only if block was written.
        if _bytes(path)==before:
            _atomic(journal_path,journal_old,expected=_bytes(journal_path)) if journal_old else journal_path.unlink(missing_ok=True)
        raise
    return {k: v for k,v in plan.items() if k not in ('content','new_block','legacy_block')}


def remove(path: Path, journal_path: Path) -> bool:
    before=_bytes(path)
    journal=_journal_read(journal_path)
    original=_decode(before)
    unmanaged,geo,legacy=_outside(original)
    if not geo:
        return False
    _assert_known_geo_block(geo,journal)
    if legacy:
        raise ValueError('Unexpected legacy HOSTS block alongside GeoHide')
    saved=journal.get('legacy_block','')
    if saved:
        # Insert legacy only if it doesn't overwrite new manual additions.
        insertion='' if not unmanaged or unmanaged.endswith(('\r','\n')) else ('\r\n' if '\r\n' in unmanaged else '\n')
        unmanaged+=insertion+saved
    _atomic(path,_encode(unmanaged),expected=before)
    try:journal_path.unlink(missing_ok=True)
    except OSError:pass
    return True


def readonly_status(path: Path, journal_path: Path) -> dict[str, object]:
    """Read-only, bounded assessment; no HOSTS contents, credentials or paths returned.

    Unknown/mismatched state is NOT converted to healthy. The GUI/CLI should
    require manual recovery when the journal and managed block disagree.
    """
    raw = _bytes(path)
    existing = _decode(raw)
    unmanaged, geo, legacy = _outside(existing)
    journal = _journal_read(journal_path)
    verified = False
    if geo and journal:
        try:
            _assert_known_geo_block(geo, journal)
            verified = True
        except ValueError:
            verified = False
    active = bool(geo)
    state = ('needs_attention' if (bool(journal) != active or (active and not verified))
             else 'installed_verified' if active else 'not_installed')
    lines = geo.splitlines() if active else []
    entries = []
    for line in lines:
        parts = line.partition('#')[0].split()
        if len(parts) == 2:
            try:
                ipaddress.ip_address(parts[0])
            except ValueError:
                continue
            entries.append(parts[1])
    # Export only counts and status, never user-managed mappings or paths.
    return {'schema': 1, 'status': state, 'geohide_installed': active,
            'restore_journal_present': bool(journal), 'journal_verified': verified,
            'managed_domains': len(set(entries)), 'managed_ip_entries': len(entries),
            'legacy_block_present': bool(legacy)}
