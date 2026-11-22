"""Validated Flowseal Game Filter settings (no shell or system changes)."""
from __future__ import annotations
import re

GAME_MODES = ('disabled', 'all', 'tcp', 'udp')
_PORTS = re.compile(r'[1-9][0-9]{0,4}(?:-[1-9][0-9]{0,4})?(?:,[1-9][0-9]{0,4}(?:-[1-9][0-9]{0,4})?)*\Z')


def validate_port_ranges(value: str) -> str:
    """Flowseal-compatible TCP/UDP port ranges, bounded to 1..65535."""
    if not isinstance(value, str) or len(value) > 256:
        raise ValueError('Неверный диапазон игровых портов')
    clean = value.replace(' ', '')
    if not _PORTS.fullmatch(clean):
        raise ValueError('Укажите порты от 1 до 65535 через запятую')
    for part in clean.split(','):
        ends = [int(x) for x in part.split('-')]
        if min(ends) < 1 or max(ends) > 65535 or ends[0] > ends[-1]:
            raise ValueError('Игровой диапазон портов вне 1..65535')
    return clean


def game_ports(mode: str, tcp: str, udp: str) -> tuple[str, str]:
    if mode not in GAME_MODES:
        raise ValueError('Неизвестный режим Game Filter')
    tcp = validate_port_ranges(tcp)
    udp = validate_port_ranges(udp)
    return (tcp if mode in ('all', 'tcp') else '12',
            udp if mode in ('all', 'udp') else '12')


IPSET_MODES = ('loaded', 'any', 'none')
IPSET_NONE_CIDR = '203.0.113.113/32'
FLOWSEAL_VERSION_URL = (
    'https://raw.githubusercontent.com/Flowseal/zapret-discord-youtube/main/.service/version.txt'
)


def prepare_ipset_override(mode: str, directory) -> 'Path | None':
    """Create isolated, deterministic IPSet variants outside the verified engine.

    loaded: use original validated Flowseal list; any: empty list;
    none: Flowseal's documented non-routable sentinel. Never edit zip contents.
    """
    from pathlib import Path
    import os
    import tempfile
    if mode not in IPSET_MODES:
        raise ValueError('Неизвестный режим IPSet')
    if mode == 'loaded':
        return None
    root = Path(directory)
    if root.is_symlink() or (root.exists() and not root.is_dir()):
        raise ValueError('Недопустимый каталог IPSet')
    root.mkdir(parents=True, exist_ok=True)
    target = root / ('ipset-any.txt' if mode == 'any' else 'ipset-none.txt')
    if target.is_symlink():
        raise ValueError('IPSet содержит символическую ссылку')
    content = b'' if mode == 'any' else (IPSET_NONE_CIDR + '\n').encode('ascii')
    fd, name = tempfile.mkstemp(prefix='.vorqeli-ipset-', dir=root)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, target)
    finally:
        Path(name).unlink(missing_ok=True)
    return target


def check_flowseal_version(timeout: int = 7) -> str:
    """Optional read-only official version check: never download or install binaries."""
    from urllib.request import Request, build_opener, ProxyHandler
    from .geohide_hosts_feed import NoRedirect
    if type(timeout) is not int or not 1 <= timeout <= 30:
        raise ValueError('Неверное время проверки обновления')
    request = Request(FLOWSEAL_VERSION_URL,
                      headers={'Accept': 'text/plain', 'User-Agent': 'VORQELI-Connect/0.41'})
    opener = build_opener(ProxyHandler({}), NoRedirect())
    with opener.open(request, timeout=timeout) as response:
        if response.status != 200 or response.geturl() != FLOWSEAL_VERSION_URL:
            raise ValueError('Неожиданный ответ источника Flowseal')
        data = response.read(65)
    if len(data) > 64:
        raise ValueError('Слишком длинная версия Flowseal')
    version = data.decode('ascii', errors='strict').strip()
    if not re.fullmatch(r'[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}', version):
        raise ValueError('Неверный формат версии Flowseal')
    return version


def is_newer_flowseal(available: str, installed: str) -> bool:
    if not all(isinstance(v, str) and
               re.fullmatch(r'[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}', v)
               for v in (available, installed)):
        raise ValueError('Неверные версии Flowseal')
    return tuple(map(int, available.split('.'))) > tuple(map(int, installed.split('.')))
