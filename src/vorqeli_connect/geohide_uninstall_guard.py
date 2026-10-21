"""Fail-closed, read-only guard for managed Windows HOSTS at uninstall.

Never remove the EXE while it is the only available UI for undoing HOSTS edits.
No registry, networking, process or file mutations occur in this module.
"""
from __future__ import annotations

from pathlib import Path

MARKERS = (
    b'# VORQELI GEOHIDE HOSTS START', b'# VORQELI GEOHIDE HOSTS END',
    b'# VORQELI OPTIONAL HOSTS START', b'# VORQELI OPTIONAL HOSTS END',
)
MAX_READ = 2 * 1024 * 1024


def inspect_pending(hosts_file: Path, journal_file: Path) -> dict[str, bool]:
    """Inspect bounded HOSTS bytes. Any unknown state raises, blocking removal.

    The journal may remain after a crash with missing/incomplete markers.
    It is therefore sufficient *on its own* to keep the cleanup UI installed.
    """
    hosts_file = Path(hosts_file)
    journal_file = Path(journal_file)
    if hosts_file.is_symlink() or journal_file.is_symlink():
        raise ValueError('HOSTS или журнал восстановления является ссылкой')
    if not hosts_file.is_file():
        raise FileNotFoundError('Системный HOSTS не найден')
    if hosts_file.stat().st_size > MAX_READ:
        raise ValueError('HOSTS превышает предельный размер безопасной проверки')
    with hosts_file.open('rb') as stream:
        raw = stream.read(MAX_READ + 1)
    if len(raw) > MAX_READ:
        raise ValueError('HOSTS изменился или слишком велик')
    if journal_file.exists() and not journal_file.is_file():
        raise ValueError('Журнал GeoHide имеет неподдерживаемый тип')
    journal = journal_file.exists()
    geo = any(marker in raw for marker in MARKERS[:2])
    legacy = any(marker in raw for marker in MARKERS[2:])
    return {'pending': journal or geo or legacy,
            'geohide_block': geo, 'optional_block': legacy,
            'journal_present': journal}
