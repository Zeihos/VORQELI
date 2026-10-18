"""Windows logon start. Elevated task is required for silent driver/DNS reconnect."""
from __future__ import annotations
import ctypes
import ntpath
import xml.etree.ElementTree as ET
import os
import subprocess
import sys
import threading
from pathlib import Path

TASK_NAME = 'VORQELI Connect'
RUN_PATH = r'Software\Microsoft\Windows\CurrentVersion\Run'
_STARTUP_LOCK = threading.RLock()


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
    """Serialize registry/task operations across GUI and connection workers."""
    with _STARTUP_LOCK:
        return _configure_startup_impl(enabled, elevated=elevated)


def _task_exists() -> bool:
    """Query Task Scheduler without treating access denial as task absence.

    schtasks returns nonzero for both missing tasks and access failures.
    Recognise only the documented missing-file response (English/Russian);
    any other failure is unknown and must NOT trigger a second startup entry.
    """
    result = _task_call('/Query', '/TN', TASK_NAME)
    if result.returncode == 0:
        return True
    detail = (str(getattr(result, 'stderr', '') or '') + '\n' +
              str(getattr(result, 'stdout', '') or '')).lower()
    missing = ('cannot find the file specified', 'cannot find the specified file',
               'не удается найти', 'не удаётся найти', 'не найден указанный файл')
    if any(marker in detail for marker in missing):
        return False
    raise RuntimeError('Невозможно проверить задачу автозапуска: ' +
                       (detail.strip()[:280] or f'код {result.returncode}'))


def _local_name(tag: str) -> str:
    """Task Scheduler XML uses a default namespace."""
    return tag.rsplit('}', 1)[-1]


def _expected_task_command() -> tuple[str, str]:
    args = launch_args()
    return args[0], subprocess.list2cmdline(args[1:])


def inspect_task_xml(document: str, *, executable: str, arguments: str) -> bool:
    """Verify that one logon action launches exactly our current executable.

    Only the executable, arguments, trigger, run level and action cardinality
    matter. Never execute, modify or trust user-controlled XML instructions.
    """
    if not document or len(document) > 1024 * 1024:
        return False
    try:
        root = ET.fromstring(document.lstrip('\ufeff\r\n '))
    except ET.ParseError:
        return False
    if _local_name(root.tag) != 'Task':
        return False
    actions = [node for node in root.iter() if _local_name(node.tag) in ('Exec', 'ComHandler')]
    if len(actions) != 1 or _local_name(actions[0].tag) != 'Exec':
        return False
    values = {_local_name(child.tag): (child.text or '').strip() for child in actions[0]}
    actual_program = values.get('Command', '').strip('"')
    expected_program = executable.strip().strip('"')
    if not actual_program or not ntpath.isabs(actual_program) or not ntpath.isabs(expected_program):
        return False
    if ntpath.normcase(ntpath.normpath(actual_program)) != ntpath.normcase(ntpath.normpath(expected_program)):
        return False
    if values.get('Arguments', '') != arguments:
        return False
    # A task with a different trigger or privilege level must not be treated as ours.
    triggers = [node for parent in root.iter() if _local_name(parent.tag) == 'Triggers'
                for node in parent]
    if len(triggers) != 1 or _local_name(triggers[0].tag) != 'LogonTrigger':
        return False
    if any(_local_name(child.tag) == 'Enabled' and
           (child.text or '').strip().lower() == 'false' for child in triggers[0]):
        return False
    principals = [node for parent in root.iter() if _local_name(parent.tag) == 'Principals'
                  for node in parent if _local_name(node.tag) == 'Principal']
    if len(principals) != 1:
        return False
    return any(_local_name(node.tag) == 'RunLevel' and
               (node.text or '').strip() == 'HighestAvailable' for node in principals[0])


def _task_identity() -> str:
    """Return trusted/untrusted/unknown without leaking a command line."""
    try:
        result = _task_call('/Query', '/TN', TASK_NAME, '/XML')
        if result.returncode != 0:
            return 'unknown'
        executable, arguments = _expected_task_command()
        return ('trusted' if inspect_task_xml(result.stdout or '', executable=executable,
                                              arguments=arguments) else 'untrusted')
    except (OSError, RuntimeError, ValueError, AttributeError, UnicodeError):
        return 'unknown'


def _require_owned_task():
    identity = _task_identity()
    if identity != 'trusted':
        raise RuntimeError('Автозапуск: задача существует, но её команда '
                           'не подтверждена как VORQELI. Ничего не изменено. '
                           'Проверьте её вручную в Планировщике заданий Windows.')


RUN_VALUE = 'VORQELI Connect'


def _registry_identity() -> str:
    r"""Classify HKCU\Run without exposing or executing its command line.

    A similarly named entry is *not* ours just because its value is nonempty.
    Do not expand environment strings: REG_EXPAND_SZ may redirect on login.
    The exact canonical command produced by this installed version is trusted.
    """
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_PATH) as key:
            value, kind = winreg.QueryValueEx(key, RUN_VALUE)
    except FileNotFoundError:
        return 'missing'
    if kind != winreg.REG_SZ or not isinstance(value, str):
        return 'untrusted'
    return 'trusted' if value == launch_command() else 'untrusted'


def _require_owned_registry() -> bool:
    """Refuse to overwrite/delete an unrelated Run entry with our name."""
    identity = _registry_identity()
    if identity == 'untrusted':
        raise RuntimeError('Автозапуск: запись реестра не подтверждена как VORQELI. '
                           'Ничего не изменено. Проверьте HKCU\\' + RUN_PATH + ' вручную.')
    return identity == 'trusted'


def registration_status() -> str:
    """Read-only, enum-only audit of both Windows autostart mechanisms.

    If a task or Run entry cannot be verified, expose ``untrusted`` or
    ``unknown``. A conflicting pair of *owned* registrations is ``conflict``.
    """
    if os.name != 'nt':
        return 'unsupported'
    try:
        has_task = _task_exists()
        if has_task:
            identity = _task_identity()
            if identity != 'trusted':
                return 'untrusted' if identity == 'untrusted' else 'unknown'
        registry = _registry_identity()
    except (OSError, RuntimeError, ValueError, TypeError):
        return 'unknown'
    if registry == 'untrusted':
        return 'untrusted'
    has_run = registry == 'trusted'
    if has_task and has_run:
        return 'conflict'
    return 'task' if has_task else 'registry' if has_run else 'missing'


def _configure_startup_impl(enabled: bool, *, elevated: bool = True) -> str:
    """Register exactly one autostart mechanism; never knowingly duplicate it.

    A scheduled task with elevated permissions takes priority. If that task
    already exists but this process lacks rights to update it, do not add an
    HKCU Run entry in parallel. The user should launch the installed app as
    administrator and retry, or disable the existing task first.
    """
    if os.name != 'nt':
        raise OSError('Автозапуск поддерживается только в Windows')
    import winreg
    task_exists = _task_exists()
    if task_exists:
        # A similarly-named task can point to an unrelated/changed executable.
        # Neither elevated reinstall nor uninstall may modify that task.
        _require_owned_task()
    # Check the other mechanism BEFORE changing either one; otherwise an
    # attacker-controlled Run entry could be overwritten or deleted silently.
    registry_exists = _require_owned_registry()
    if not enabled:
        if task_exists:
            result = _task_call('/Delete', '/TN', TASK_NAME, '/F')
            if result.returncode != 0:
                raise RuntimeError('Не удалось удалить задачу автозапуска Windows')
        if registry_exists:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_PATH, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, RUN_VALUE)
        return 'disabled'

    can_install_task = elevated and is_admin() and trusted_install_path()
    if can_install_task:
        # An already verified existing task needs no rewrite. This reduces
        # privileged mutations and avoids a race with background startup sync.
        if not task_exists:
            result = _task_call('/Create', '/F', '/SC', 'ONLOGON', '/RL', 'HIGHEST',
                                '/TN', TASK_NAME, '/TR', launch_command())
            if result.returncode != 0:
                raise RuntimeError('Не удалось создать повышенную задачу автозапуска Windows')
        if registry_exists:
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_PATH, 0, winreg.KEY_SET_VALUE) as key:
                    # Recheck identity to guard against concurrent changes.
                    if _registry_identity() != 'trusted':
                        raise RuntimeError('Запись автозапуска изменилась при переключении режима')
                    winreg.DeleteValue(key, RUN_VALUE)
            except Exception:
                # Only roll back a task created by this invocation. Never
                # delete a pre-existing verified task as a side effect.
                if not task_exists and _task_identity() == 'trusted':
                    _task_call('/Delete', '/TN', TASK_NAME, '/F')
                raise
        return 'task'

    if task_exists:
        raise RuntimeError(
            'Задача автозапуска уже существует. Для её изменения '
            'запустите установленный VORQELI от администратора; '
            'запасной автозапуск через реестр не создан.')
    if not registry_exists:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_PATH) as key:
            winreg.SetValueEx(key, RUN_VALUE, 0, winreg.REG_SZ, launch_command())
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
