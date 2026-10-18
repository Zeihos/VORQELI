"""Windows startup safety regressions, without touching host registry or tasks."""
import sys
from types import SimpleNamespace
import pytest
from vorqeli_connect import startup, doctor


class FakeKey:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class FakeWinreg:
    HKEY_CURRENT_USER = 'HKCU'
    REG_SZ = 1
    KEY_SET_VALUE = 2

    def __init__(self, initial=None):
        self.entries = dict(initial or {})
        self.created = []

    def OpenKey(self, parent, name, *args):
        if not self.entries:
            raise FileNotFoundError(name)
        return FakeKey()

    def CreateKey(self, parent, name):
        self.created.append(name)
        return FakeKey()

    def QueryValueEx(self, key, name):
        if name not in self.entries:
            raise FileNotFoundError(name)
        return self.entries[name], self.REG_SZ

    def DeleteValue(self, key, name):
        if name not in self.entries:
            raise FileNotFoundError(name)
        self.entries.pop(name)

    def SetValueEx(self, key, name, zero, kind, value):
        self.entries[name] = value


@pytest.fixture
def fake_windows(monkeypatch):
    winreg = FakeWinreg()
    monkeypatch.setitem(sys.modules, 'winreg', winreg)
    monkeypatch.setattr(startup, 'os', SimpleNamespace(name='nt'))
    monkeypatch.setattr(startup, 'is_admin', lambda: False)
    monkeypatch.setattr(startup, 'trusted_install_path', lambda: False)
    monkeypatch.setattr(startup, 'launch_command', lambda: '"C:/Program Files/VORQELI.exe" --minimized')
    monkeypatch.setattr(startup, 'launch_args', lambda: ['C:/Program Files/VORQELI.exe', '--minimized'])
    return winreg


def fake_tasks(monkeypatch, *, present=False, create_rc=0, delete_rc=0):
    calls = []

    def call(*args):
        calls.append(args)
        if args[0] == '/Query':
            xml = ("<Task><Triggers><LogonTrigger/></Triggers>"
                   "<Principals><Principal><RunLevel>HighestAvailable</RunLevel></Principal></Principals>"
                   "<Actions><Exec><Command>C:/Program Files/VORQELI.exe</Command>"
                   "<Arguments>--minimized</Arguments></Exec></Actions></Task>")
            return SimpleNamespace(returncode=0 if present else 1,
                                   stdout=xml if present else '',
                                   stderr='' if present else 'ERROR: The system cannot find the file specified.')
        if args[0] == '/Create':
            return SimpleNamespace(returncode=create_rc)
        if args[0] == '/Delete':
            return SimpleNamespace(returncode=delete_rc)
        raise AssertionError(args)

    monkeypatch.setattr(startup, '_task_call', call)
    return calls


def test_existing_elevated_task_never_creates_parallel_registry_start(fake_windows, monkeypatch):
    calls = fake_tasks(monkeypatch, present=True)
    with pytest.raises(RuntimeError, match='администратора'):
        startup.configure_startup(True)
    assert not fake_windows.entries
    assert all(call[0] != '/Create' for call in calls)


def test_registry_fallback_only_when_task_absent(fake_windows, monkeypatch):
    fake_tasks(monkeypatch, present=False)
    assert startup.configure_startup(True) == 'registry'
    assert '--minimized' in fake_windows.entries['VORQELI Connect']


def test_upgrading_to_elevated_task_removes_old_registry_autostart(fake_windows, monkeypatch):
    fake_windows.entries['VORQELI Connect'] = startup.launch_command()
    monkeypatch.setattr(startup, 'is_admin', lambda: True)
    monkeypatch.setattr(startup, 'trusted_install_path', lambda: True)
    calls = fake_tasks(monkeypatch, present=False)
    assert startup.configure_startup(True) == 'task'
    assert 'VORQELI Connect' not in fake_windows.entries
    assert any(call[0] == '/Create' for call in calls)


def test_scheduled_task_creation_failure_never_silently_falls_back(fake_windows, monkeypatch):
    fake_windows.entries['VORQELI Connect'] = startup.launch_command()
    monkeypatch.setattr(startup, 'is_admin', lambda: True)
    monkeypatch.setattr(startup, 'trusted_install_path', lambda: True)
    fake_tasks(monkeypatch, present=False, create_rc=1)
    with pytest.raises(RuntimeError, match='повышенную задачу'):
        startup.configure_startup(True)
    assert fake_windows.entries['VORQELI Connect'] == startup.launch_command()


def test_disabling_autostart_removes_both_mechanisms(fake_windows, monkeypatch):
    fake_windows.entries['VORQELI Connect'] = startup.launch_command()
    calls = fake_tasks(monkeypatch, present=True)
    assert startup.configure_startup(False) == 'disabled'
    assert 'VORQELI Connect' not in fake_windows.entries
    assert any(call[0] == '/Delete' for call in calls)


def test_failed_task_delete_preserves_registry_for_manual_recovery(fake_windows, monkeypatch):
    fake_windows.entries['VORQELI Connect'] = startup.launch_command()
    fake_tasks(monkeypatch, present=True, delete_rc=1)
    with pytest.raises(RuntimeError, match='удалить задачу'):
        startup.configure_startup(False)
    assert fake_windows.entries['VORQELI Connect'] == startup.launch_command()


@pytest.mark.parametrize('present,registry,expected', [
    (True, 'owned', 'conflict'), (True, None, 'task'),
    (False, 'owned', 'registry'), (False, None, 'missing'),
])
def test_doctor_detects_task_registry_conflict(fake_windows, monkeypatch, present, registry, expected):
    fake_tasks(monkeypatch, present=present)
    if registry:
        fake_windows.entries['VORQELI Connect'] = startup.launch_command() if registry == 'owned' else registry
    assert startup.registration_status() == expected
    assert doctor.startup_registration() == expected


def test_doctor_reports_unknown_when_task_query_fails(fake_windows, monkeypatch):
    monkeypatch.setattr(startup, '_task_call', lambda *args: (_ for _ in ()).throw(OSError('denied')))
    assert startup.registration_status() == 'unknown'


def test_report_accepts_conflict_without_sensitive_paths():
    from vorqeli_connect.config import Settings
    report = doctor.create_report(Settings(), is_windows=True, admin=False,
        tray_available=True, telegram_available=True, dpi_available=False,
        dns_backup_present=False, startup_mode='conflict')
    assert report['startup_registration'] == 'conflict'
    assert not any('C:/' in str(value) for value in report.values())


def test_layout_requires_installer_mutex(tmp_path):
    from pathlib import Path
    import importlib.util
    import shutil
    script = Path(__file__).resolve().parents[1] / 'scripts/check_repo_layout.py'
    spec = importlib.util.spec_from_file_location('repo_verify23', script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    src = script.parent.parent
    assert module.check_layout(src) == []
    staged = tmp_path / 'repo'
    shutil.copytree(src, staged, ignore=shutil.ignore_patterns('__pycache__', '.pytest_cache'))
    iscc = staged / 'installer/VORQELI.iss'
    iscc.write_text(iscc.read_text(encoding='utf-8').replace(
        'AppMutex=Local\\VORQELI-Connect-Instance', 'AppMutex=wrong'), encoding='utf-8')
    assert any('защищён' in x for x in module.check_layout(staged))


def test_access_denied_task_query_cannot_create_second_startup(fake_windows, monkeypatch):
    fake_windows.entries['VORQELI Connect'] = startup.launch_command()
    monkeypatch.setattr(startup, '_task_call', lambda *args: SimpleNamespace(
        returncode=1, stderr='ERROR: Access is denied.'))
    with pytest.raises(RuntimeError, match='Невозможно проверить'):
        startup.configure_startup(True)
    assert fake_windows.entries['VORQELI Connect'] == startup.launch_command()
    assert startup.registration_status() == 'unknown'


def test_empty_failed_task_query_is_not_treated_as_missing(fake_windows, monkeypatch):
    monkeypatch.setattr(startup, '_task_call', lambda *args: SimpleNamespace(
        returncode=1, stderr=''))
    with pytest.raises(RuntimeError, match='Невозможно проверить'):
        startup.configure_startup(True)
    assert not fake_windows.entries
