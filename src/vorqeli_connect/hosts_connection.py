"""Transactional HOSTS-only GeoHide + Flowseal connection.

The feature never changes adapter DNS or executes service.bat. The two trusted
HTTPS sources are parsed before any system file is modified. The existing
GeoHide journal provides an integrity-checked reversible managed HOSTS block.
"""
from __future__ import annotations

from hashlib import sha256
import ipaddress
from pathlib import Path
from urllib.request import Request, ProxyHandler, build_opener

from .config import APP_DIR
from .hosts_overlay import hosts_path
from . import geohide_hosts_feed as geo

FLOWSEAL_HOSTS_URL = (
    'https://raw.githubusercontent.com/Flowseal/zapret-discord-youtube/main/.service/hosts'
)
HOSTS_JOURNAL = APP_DIR / 'geohide-hosts-restore.json'
FLOWSEAL_MAX_BYTES = 96 * 1024


def fetch_flowseal_hosts(*, timeout: int = 12) -> str:
    """Read a bounded, HTTPS-only source without following redirects."""
    if type(timeout) is not int or not 1 <= timeout <= 45:
        raise ValueError('Invalid timeout')
    opener = build_opener(ProxyHandler({}), geo.NoRedirect())
    request = Request(FLOWSEAL_HOSTS_URL, headers={
        'Accept': 'text/plain', 'User-Agent': 'VORQELI-Connect/0.41'})
    with opener.open(request, timeout=timeout) as response:
        if response.status != 200 or response.geturl() != FLOWSEAL_HOSTS_URL:
            raise ValueError('Unexpected Flowseal HOSTS source')
        raw = response.read(FLOWSEAL_MAX_BYTES + 1)
    if len(raw) > FLOWSEAL_MAX_BYTES:
        raise ValueError('Flowseal HOSTS is too large')
    return raw.decode('utf-8-sig', errors='strict')


def parse_flowseal_hosts(text: str) -> tuple[tuple[str, str], ...]:
    if not isinstance(text, str) or len(text.encode('utf-8')) > FLOWSEAL_MAX_BYTES:
        raise ValueError('Invalid Flowseal HOSTS size')
    rows = []
    seen = set()
    for line in text.splitlines():
        body = line.partition('#')[0].strip()
        if not body:
            continue
        pieces = body.split()
        if len(pieces) != 2:
            raise ValueError('Malformed Flowseal HOSTS line')
        raw_ip, raw_name = pieces
        name = raw_name.rstrip('.').lower()
        try:
            ip = ipaddress.ip_address(raw_ip)
        except ValueError as exc:
            raise ValueError('Malformed Flowseal IP') from exc
        if not ip.is_global or not geo.HOST_RE.fullmatch(name) or len(name) > 253:
            raise ValueError('Unsafe Flowseal HOSTS record')
        record = (str(ip), name)
        if record not in seen:
            rows.append(record)
            seen.add(record)
        if len(rows) > 500:
            raise ValueError('Too many Flowseal HOSTS records')
    hosts = {name for _, name in rows}
    if len(hosts) < 15 or not {'discord.com', 'github.com'}.issubset(hosts):
        raise ValueError('Flowseal HOSTS is truncated or unexpected')
    return tuple(rows)


def merge_sources(geohide_text: str, flowseal_text: str, *,
                  geo_min_domains: int = 200) -> geo.Snapshot:
    """GeoHide keeps priority on overlaps, then append distinct Flowseal names."""
    g = geo.parse_official(geohide_text, min_domains=geo_min_domains)
    f = parse_flowseal_hosts(flowseal_text)
    geo_names = {name for _, name in g.records}
    extras = [entry for entry in f if entry[1] not in geo_names]
    records = tuple(g.records) + tuple(extras)
    digest = sha256((g.sha256 + '\n' + sha256(flowseal_text.encode('utf-8')).hexdigest()).encode('ascii')).hexdigest()
    return geo.Snapshot(records, g.updated, digest,
                        len({name for _, name in records}))


def enable_hosts_only(*, path: Path | None = None,
                      journal_path: Path | None = None,
                      geo_fetch=None, flowseal_fetch=None) -> dict:
    """Fetch and validate both sources before touching HOSTS; no DNS changes."""
    if geo_fetch is None:
        geo_fetch = geo.fetch_official
    if flowseal_fetch is None:
        flowseal_fetch = fetch_flowseal_hosts
    target = path or hosts_path()
    journal = journal_path or HOSTS_JOURNAL
    try:
        # Always prefer current official mappings when reachable.
        geohide_text = geo_fetch()
        flowseal_text = flowseal_fetch()
    except OSError:
        # A reconnect after an outage must not rewrite or discard a previously
        # verified, managed HOSTS section. Never use a missing/edited journal.
        if status_hosts_only(path=target, journal_path=journal):
            return {'reused_verified': True, 'fresh': False}
        raise
    # Invalid source data must fail closed: never silently trust a bad feed.
    source = merge_sources(geohide_text, flowseal_text)
    applied = geo.apply(target, source, journal)
    return {**applied, 'reused_verified': False, 'fresh': True}


def restore_hosts_only(*, path: Path | None = None,
                       journal_path: Path | None = None) -> bool:
    return geo.remove(path or hosts_path(), journal_path or HOSTS_JOURNAL)


def status_hosts_only(*, path: Path | None = None,
                      journal_path: Path | None = None) -> bool:
    try:
        status = geo.readonly_status(path or hosts_path(), journal_path or HOSTS_JOURNAL)
        return status['status'] == 'installed_verified'
    except (OSError, ValueError):
        return False
