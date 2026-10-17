"""Windows logon start. Elevated task is required for silent driver/DNS reconnect."""
from __future__ import annotations
import ctypes
import os
import subprocess
import sys
from pathlib import Path

TASK_NAME = 'VORQELI Connect'
RUN_PATH = r'Software\Microsoft\Windows\CurrentVersion\Run'


def is_admin() -> bool:
    if os.name != 'nt':
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (AttributeError, OSError):
        return False


def launch_args(*, minimized: bool = True) -> list[str]:
    if getattr(sys, 'frozen', False):
        result = [sys.executable]
    else:
        python = Path(sys.executable)
        pythonw = python.with_name('pythonw.exe')
        result = [str(pythonw if os.name == 'nt' and pythonw.is_file() else python), '-m', 'vorqeli_connect']
    if minimized:
        result.append('--minimized')
    return result


def launch_command() -> str:
    return subprocess.list2cmdline(launch_args())


def trusted_install_path() -> bool:
    """Only authorize a UAC-free elevated logon task for installed EXEs.

    A task pointing at a user-writable portable EXE would allow silent
    privilege escalation by swapping that executable. This path check is a
    baseline guard; the installer must preserve Program Files ACLs.
    """
    if os.name != 'nt' or not getattr(sys, 'frozen', False):
        return False
    try:
        executable = Path(sys.executable).resolve()
        bases = [os.environ.get('ProgramFiles',''), os.environ.get('ProgramFiles(x86)','')]
        return any(base and executable.is_relative_to(Path(base).resolve()) for base in bases)
    except (ValueError, OSError):
        return False

def _task_call(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(['schtasks.exe', *args], capture_output=True, text=True, timeout=20,
                          creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))


def configure_startup(enabled: bool, *, elevated: bool = True) -> str:
    """Try an elevated per-user logon task; otherwise current-user Run registry.

    Do not silently claim elevation: returning 'registry' means that DPI/DNS may
    require UAC at next logon. Call from user-facing opt-in settings.
    """
    if os.name != 'nt':
        raise OSError('Автозапуск поддерживается только в Windows')
    import winreg
    # Remove the existing task if possible, to avoid double launch.
    if not enabled:
        exists = _task_call('/Query', '/TN', TASK_NAME).returncode == 0
        if exists:
            result = _task_call('/Delete', '/TN', TASK_NAME, '/F')
            if result.returncode != 0:
                raise RuntimeError('Не удалось удалить задачу автозапуска Windows')
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_PATH) as k:
            try:
                winreg.DeleteValue(k, 'VORQELI Connect')
            except FileNotFoundError:
                pass
        return 'disabled'
    if elevated and is_admin() and trusted_install_path():
        cmd = launch_command()
        result = _task_call('/Create', '/F', '/SC', 'ONLOGON', '/RL', 'HIGHEST',
                            '/TN', TASK_NAME, '/TR', cmd)
        if result.returncode == 0:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_PATH) as k:
                try:
                    winreg.DeleteValue(k, 'VORQELI Connect')
                except FileNotFoundError:
                    pass
            return 'task'
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_PATH) as k:
        winreg.SetValueEx(k, 'VORQELI Connect', 0, winreg.REG_SZ, launch_command())
    return 'registry'


def relaunch_elevated() -> bool:
    """Request standard UAC prompt. Caller exits only after ShellExecute succeeds."""
    if os.name != 'nt':
        return False
    args = launch_args(minimized=False)
    args.append('--elevation-retry')
    result = ctypes.windll.shell32.ShellExecuteW(
        None, 'runas', args[0], subprocess.list2cmdline(args[1:]), None, 1)
    return int(result) > 32
