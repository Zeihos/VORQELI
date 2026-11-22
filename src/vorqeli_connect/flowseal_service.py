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
