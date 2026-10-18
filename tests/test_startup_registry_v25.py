"""v0.25: HKCU Run ownership and safe transition to an elevated task.

These unit tests mock the registry and Task Scheduler. They NEVER change
host OS startup settings or launch other programs.
"""
from types import SimpleNamespace

import pytest

from vorqeli_connect import doctor, startup
from test_startup_v23 import fake_windows, fake_tasks


@pytest.mark.parametrize('value', [
    '',
    'C:/Temp/other-program.exe --minimized',
    '"C:/Program Files/VORQELI.exe" --minimized --other-command',
    '%APPDATA%\\VORQELI.exe --minimized',
    ' "C:/Program Files/VORQELI.exe" --minimized',
    b'not a text command',
    None,
])
def test_unrelated_run_entry_is_never_modified(fake_windows, monkeypatch, value):
    calls = fake_tasks(monkeypatch, present=False)
    fake_windows.entries[startup.RUN_VALUE] = value
    assert startup.registration_status() == 'untrusted'
    for requested in (True, False):
        with pytest.raises(RuntimeError, match='реестра не подтверждена'):
            startup.configure_startup(requested)
        assert fake_windows.entries[startup.RUN_VALUE] == value
        assert not any(x[0] in ('/Create', '/Delete') for x in calls)


@pytest.mark.parametrize('mode', ['task', 'registry'])
def test_foreign_run_entry_blocks_all_startup_modes(fake_windows, monkeypatch, mode):
    calls = fake_tasks(monkeypatch, present=False)
    fake_windows.entries[startup.RUN_VALUE] = 'C:/Temp/another.exe'
    if mode == 'task':
        monkeypatch.setattr(startup, 'is_admin', lambda: True)
        monkeypatch.setattr(startup, 'trusted_install_path', lambda: True)
    with pytest.raises(RuntimeError, match='не подтверждена'):
        startup.configure_startup(True)
    assert fake_windows.entries[startup.RUN_VALUE] == 'C:/Temp/another.exe'
    assert all(x[0] == '/Query' for x in calls)


def test_owned_run_entry_is_idempotent(fake_windows, monkeypatch):
    fake_tasks(monkeypatch, present=False)
    fake_windows.entries[startup.RUN_VALUE] = startup.launch_command()
    assert startup.registration_status() == 'registry'
    assert startup.configure_startup(True) == 'registry'
    assert fake_windows.created == []  # nothing was re-created or overwritten
    assert fake_windows.entries[startup.RUN_VALUE] == startup.launch_command()


def test_owned_registry_can_be_safely_disabled(fake_windows, monkeypatch):
    fake_tasks(monkeypatch, present=False)
    fake_windows.entries[startup.RUN_VALUE] = startup.launch_command()
    assert startup.configure_startup(False) == 'disabled'
    assert startup.registration_status() == 'missing'
    assert startup.RUN_VALUE not in fake_windows.entries


def test_empty_registry_is_not_created_while_disabling(fake_windows, monkeypatch):
    fake_tasks(monkeypatch, present=False)
    assert startup.configure_startup(False) == 'disabled'
    assert fake_windows.created == []


def test_foreign_registry_with_owned_task_is_also_untrusted(fake_windows, monkeypatch):
    calls = fake_tasks(monkeypatch, present=True)
    fake_windows.entries[startup.RUN_VALUE] = 'foreign-launcher --minimized'
    assert startup.registration_status() == 'untrusted'
    with pytest.raises(RuntimeError, match='реестра не подтверждена'):
        startup.configure_startup(False)
    with pytest.raises(RuntimeError, match='реестра не подтверждена'):
        startup.configure_startup(True)
    assert all(x[0] not in ('/Delete', '/Create') for x in calls)


def test_owned_elevated_task_does_not_get_recreated(fake_windows, monkeypatch):
    calls = fake_tasks(monkeypatch, present=True)
    monkeypatch.setattr(startup, 'is_admin', lambda: True)
    monkeypatch.setattr(startup, 'trusted_install_path', lambda: True)
    assert startup.configure_startup(True) == 'task'
    assert all(x[0] != '/Create' for x in calls)


def test_unreadable_registry_cannot_be_assumed_absent(fake_windows, monkeypatch):
    fake_tasks(monkeypatch, present=False)
    def denied(*args):
        raise PermissionError('Access denied')
    monkeypatch.setattr(fake_windows, 'OpenKey', denied)
    assert startup.registration_status() == 'unknown'
    with pytest.raises(PermissionError):
        startup.configure_startup(True)
    assert fake_windows.created == []


def test_tampered_run_command_is_not_reported_in_diagnostics(fake_windows, monkeypatch):
    fake_tasks(monkeypatch, present=False)
    secret='--secret=DO_NOT_LEAK'
    fake_windows.entries[startup.RUN_VALUE] = f'C:/foreign.exe {secret}'
    from vorqeli_connect.config import Settings
    status = startup.registration_status()
    report = doctor.create_report(
        Settings(), is_windows=True, admin=False, tray_available=True,
        telegram_available=False, dpi_available=False, dns_backup_present=False,
        startup_mode=status)
    assert report['startup_registration'] == 'untrusted'
    assert secret not in str(report)
    assert 'C:/foreign.exe' not in str(report)


def test_failed_registry_deletion_rolls_back_new_task(fake_windows, monkeypatch):
    """When transitioning registry->task, don't leave a duplicate on failures."""
    fake_windows.entries[startup.RUN_VALUE] = startup.launch_command()
    monkeypatch.setattr(startup, 'is_admin', lambda: True)
    monkeypatch.setattr(startup, 'trusted_install_path', lambda: True)
    current={'task': False}
    actions=[]
    xml = ('<Task><Triggers><LogonTrigger/></Triggers><Principals><Principal>'
           '<RunLevel>HighestAvailable</RunLevel></Principal></Principals><Actions><Exec>'
           '<Command>C:/Program Files/VORQELI.exe</Command><Arguments>--minimized</Arguments>'
           '</Exec></Actions></Task>')
    def task(*args):
        actions.append(args[0])
        if args[0] == '/Query':
            return SimpleNamespace(returncode=0 if current['task'] else 1,
                stdout=xml if current['task'] else '',
                stderr='' if current['task'] else 'The system cannot find the file specified.')
        if args[0] == '/Create':
            current['task'] = True
            return SimpleNamespace(returncode=0)
        if args[0] == '/Delete':
            current['task'] = False
            return SimpleNamespace(returncode=0)
        raise AssertionError(args)
    monkeypatch.setattr(startup, '_task_call', task)
    def delete_denied(*args):
        raise PermissionError('Registry write denied')
    monkeypatch.setattr(fake_windows, 'DeleteValue', delete_denied)
    with pytest.raises(PermissionError):
        startup.configure_startup(True)
    assert actions.count('/Create') == 1
    assert actions.count('/Delete') == 1
    assert current['task'] is False
    assert fake_windows.entries[startup.RUN_VALUE] == startup.launch_command()


def test_failed_registry_deletion_does_not_delete_preexisting_task(fake_windows, monkeypatch):
    fake_windows.entries[startup.RUN_VALUE] = startup.launch_command()
    monkeypatch.setattr(startup, 'is_admin', lambda: True)
    monkeypatch.setattr(startup, 'trusted_install_path', lambda: True)
    calls = fake_tasks(monkeypatch, present=True)
    monkeypatch.setattr(fake_windows, 'DeleteValue', lambda *args: (_ for _ in ()).throw(PermissionError('denied')))
    with pytest.raises(PermissionError):
        startup.configure_startup(True)
    assert all(x[0] not in ('/Create', '/Delete') for x in calls)


def test_registry_expand_sz_is_untrusted_even_with_matching_command(fake_windows, monkeypatch):
    fake_tasks(monkeypatch, present=False)
    fake_windows.entries[startup.RUN_VALUE] = startup.launch_command()
    original=fake_windows.QueryValueEx
    monkeypatch.setattr(fake_windows, 'QueryValueEx', lambda key, name: (original(key,name)[0], 2))
    assert startup.registration_status() == 'untrusted'
    with pytest.raises(RuntimeError, match='реестра не подтверждена'):
        startup.configure_startup(False)
    assert fake_windows.entries[startup.RUN_VALUE] == startup.launch_command()


def test_registry_type_query_error_prevents_task_creation(fake_windows, monkeypatch):
    calls = fake_tasks(monkeypatch, present=False)
    monkeypatch.setattr(startup, 'is_admin', lambda: True)
    monkeypatch.setattr(startup, 'trusted_install_path', lambda: True)
    monkeypatch.setattr(fake_windows, 'QueryValueEx', lambda *args: (_ for _ in ()).throw(PermissionError('denied')))
    fake_windows.entries[startup.RUN_VALUE] = startup.launch_command()
    assert startup.registration_status() == 'unknown'
    with pytest.raises(PermissionError):
        startup.configure_startup(True)
    assert all(x[0] != '/Create' for x in calls)
