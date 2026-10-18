"""Security-critical tests: no real Windows tasks are created or modified."""
from types import SimpleNamespace
import pytest
from vorqeli_connect import startup
from test_startup_v23 import fake_tasks, fake_windows


def xml(cmd=r'C:\\Program Files\\VORQELI Connect\\VORQELI-Connect.exe',
        arg='--minimized', *, extra='', run_level='HighestAvailable', trigger='LogonTrigger'):
    return (f'<Task xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">'
            f'<Triggers><{trigger}/></Triggers>'
            f'<Principals><Principal><RunLevel>{run_level}</RunLevel></Principal></Principals>'
            f'<Actions><Exec><Command>{cmd}</Command><Arguments>{arg}</Arguments></Exec>'
            f'{extra}</Actions></Task>')


def test_valid_scheduled_task():
    assert startup.inspect_task_xml(xml(), executable=r'C:\\Program Files\\VORQELI Connect\\VORQELI-Connect.exe',
                                    arguments='--minimized')


@pytest.mark.parametrize('changes', [
    {'cmd': r'C:\\Temp\\malware.exe'},
    {'arg': '--minimized --execute-other'},
    {'extra': '<Exec><Command>C:/malware.exe</Command></Exec>'},
    {'extra': '<ComHandler><ClassId>bad</ClassId></ComHandler>'},
    {'run_level': 'LeastPrivilege'},
    {'trigger': 'TimeTrigger'},
])
def test_untrusted_task_attributes(changes):
    assert not startup.inspect_task_xml(xml(**changes),
        executable=r'C:\\Program Files\\VORQELI Connect\\VORQELI-Connect.exe',
        arguments='--minimized')


@pytest.mark.parametrize('payload', ['', 'not XML', '<Task><Actions>'])
def test_corrupted_xml_is_rejected(payload):
    assert not startup.inspect_task_xml(payload,
        executable=r'C:\\Program Files\\VORQELI Connect\\VORQELI-Connect.exe',
        arguments='--minimized')


def test_matching_task_name_with_foreign_command_blocks_disable_and_enable(fake_windows, monkeypatch):
    fake_windows.entries['VORQELI Connect'] = 'old entry'
    actions = []
    def fake(*args):
        actions.append(args)
        if args[0] == '/Query':
            return SimpleNamespace(returncode=0, stdout=xml(cmd=r'C:\\Temp\\foreign.exe'), stderr='')
        raise AssertionError('Foreign task must never be mutated')
    monkeypatch.setattr(startup, '_task_call', fake)
    assert startup.registration_status() == 'untrusted'
    with pytest.raises(RuntimeError, match='не подтверждена'):
        startup.configure_startup(True)
    with pytest.raises(RuntimeError, match='не подтверждена'):
        startup.configure_startup(False)
    assert fake_windows.entries == {'VORQELI Connect': 'old entry'}
    assert all(item[0] == '/Query' for item in actions)


def test_xml_query_permission_denied_blocks_modification(fake_windows, monkeypatch):
    actions = []
    def fake(*args):
        actions.append(args)
        if args[0] == '/Query':
            return SimpleNamespace(returncode=1 if '/XML' in args else 0,
                                   stdout='', stderr='Access denied')
        raise AssertionError('Cannot modify unverified task')
    monkeypatch.setattr(startup, '_task_call', fake)
    assert startup.registration_status() == 'unknown'
    with pytest.raises(RuntimeError):
        startup.configure_startup(False)
    assert not any(action[0] == '/Delete' for action in actions)


def test_extra_trigger_is_untrusted():
    doc = xml().replace('</Triggers>', '<TimeTrigger/></Triggers>')
    assert not startup.inspect_task_xml(doc,
        executable=r'C:\Program Files\VORQELI Connect\VORQELI-Connect.exe',
        arguments='--minimized')


def test_disabled_logon_trigger_is_untrusted():
    doc = xml().replace('<LogonTrigger/>', '<LogonTrigger><Enabled>false</Enabled></LogonTrigger>')
    assert not startup.inspect_task_xml(doc,
        executable=r'C:\Program Files\VORQELI Connect\VORQELI-Connect.exe',
        arguments='--minimized')


def test_doctor_reports_untrusted_as_enum_only():
    from vorqeli_connect.doctor import create_report
    from vorqeli_connect.config import Settings
    report = create_report(Settings(),is_windows=True,admin=False,tray_available=True,
                           telegram_available=False,dpi_available=False,
                           dns_backup_present=False,startup_mode='untrusted')
    assert report['startup_registration']=='untrusted'
    assert 'Program Files' not in str(report)
