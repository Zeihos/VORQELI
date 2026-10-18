"""Fail-closed Windows uninstallation preflight.

The installer MUST NOT remove VORQELI while its UI is still running, a
scheduled start is active, or a GeoHide DNS backup could not be restored.

This check does not kill arbitrary processes or silently discard DNS backups.
"""
from __future__ import annotations

import ctypes
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .geohide import STATE_FILE
from .geohide_doh import restore_geo_dns, _journal_path
from .startup import configure_startup, registration_status

INSTANCE_MUTEX = r'Local\VORQELI-Connect-Instance'


class UninstallPreflightError(RuntimeError):
    """A problem requiring manual intervention before removing VORQELI."""


@dataclass(frozen=True)
class CleanupResult:
    success: bool
    details: tuple[str, ...] = ()


def running_instance() -> bool:
    """Determine if GUI owns the named mutex in the current Windows session.

    Access denied and other unexpected errors are treated as 'possibly
    running', because deleting an active elevated networking app is unsafe.
    """
    if os.name != 'nt':
        return False
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenMutexW.argtypes = (ctypes.c_uint, ctypes.c_int, ctypes.c_wchar_p)
    kernel.OpenMutexW.restype = ctypes.c_void_p
    kernel.CloseHandle.argtypes = (ctypes.c_void_p,)
    kernel.CloseHandle.restype = ctypes.c_int
    handle = kernel.OpenMutexW(0x00100000, False, INSTANCE_MUTEX)  # SYNCHRONIZE
    if handle:
        kernel.CloseHandle(handle)
        return True
    err = ctypes.get_last_error()
    if err == 2:  # ERROR_FILE_NOT_FOUND
        return False
    # ACCESS_DENIED or any other OS error: do not proceed with deletion.
    raise UninstallPreflightError(f'Не удалось проверить работающий экземпляр (Win32: {err}).')


def startup_cleanup_confirmed(observed: str, *, windows: bool) -> bool:
    """Only verified absence is safe on Windows; tests use unsupported off-Windows."""
    return observed == ('missing' if windows else 'unsupported')


def cleanup_for_uninstall(
    *,
    check_running: Callable[[], bool] = running_instance,
    disable_startup: Callable[[bool], str] = configure_startup,
    restore: Callable[[], bool] = restore_geo_dns,
    audit_startup: Callable[[], str] = registration_status,
    backup: Path | None = None,
) -> CleanupResult:
    """Perform reversible cleanup, returning failure if any critical step fails.

    Inno Setup calls this BEFORE deleting executable files. A failed result
    leaves files installed so the user can fix DNS/startup and retry.
    """
    failures: list[str] = []
    try:
        if check_running():
            return CleanupResult(False, ('Сначала полностью выйдите из VORQELI через трей.',))
    except Exception as exc:
        return CleanupResult(False, (f'Проверка работающего приложения: {exc}',))

    try:
        outcome = disable_startup(False)
        if outcome not in ('disabled', 'off'):
            raise UninstallPreflightError('Команда отключения не подтвердила результат')
        observed = audit_startup()
        # An unsupported platform is useful for offline unit tests; on Windows
        # ONLY an independently observed missing registration is sufficient.
        if not startup_cleanup_confirmed(observed, windows=os.name == 'nt'):
            raise UninstallPreflightError('Автозапуск остался включён либо результат проверки неизвестен')
    except Exception as exc:
        failures.append(f'Не удалось отключить автозапуск: {exc}')

    target = STATE_FILE if backup is None else backup
    doh_backup = _journal_path(target)
    if target.is_file() or doh_backup.is_file():
        try:
            if restore() is not True:
                raise UninstallPreflightError('DNS не подтверждён как восстановленный')
            if target.exists() or doh_backup.exists():
                raise UninstallPreflightError('Резервная копия DNS/DoH всё ещё присутствует')
        except Exception as exc:
            failures.append(f'Не удалось восстановить GeoHide DNS: {exc}')

    return CleanupResult(not failures, tuple(failures))
