import json
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from vorqeli_connect import geohide, unified
from vorqeli_connect.config import Settings
from vorqeli_connect.doctor import create_report


def _state(index, before, manual=''):
    return {'index':index, 'alias':f'adapter-{index}', 'manual':manual, 'before':before}


def test_changed_dns_does_not_discard_backup(tmp_path, monkeypatch):
    backup=tmp_path/'dns.json'
    geohide._save_state([_state(4,['8.8.8.8'])], backup)
    monkeypatch.setattr(geohide,'query_dns_state',lambda:[_state(4,['1.1.1.1'])])
    changed=[]
    monkeypatch.setattr(geohide,'_apply_one',lambda *a:changed.append(a))
    with pytest.raises(RuntimeError,match='другой программой'):
        geohide.restore_dns(backup)
    assert changed == []
    assert json.loads(backup.read_text())['interfaces'][0]['index']==4


def test_unplugged_adapter_keeps_backup(tmp_path,monkeypatch):
    backup=tmp_path/'dns.json'
    geohide._save_state([_state(4,['8.8.8.8'])], backup)
    monkeypatch.setattr(geohide,'query_dns_state',lambda:[])
    with pytest.raises(RuntimeError,match='отсутствует'):
        geohide.restore_dns(backup)
    assert backup.exists()


def test_partial_restore_keeps_only_pending_adapter(tmp_path,monkeypatch):
    backup=tmp_path/'dns.json'
    geohide._save_state([_state(4,['8.8.8.8'], '8.8.8.8'),
                         _state(9,['9.9.9.9'])], backup)
    current=[_state(4,list(geohide.GEOHIDE_IPV4)), _state(9,['1.1.1.1'])]
    monkeypatch.setattr(geohide,'query_dns_state',lambda:current)
    applied=[]
    def apply(idx, addresses):
        applied.append((idx, addresses))
        for adapter in current:
            if adapter['index'] == idx:
                adapter['before'] = addresses
    monkeypatch.setattr(geohide,'_apply_one',apply)
    with pytest.raises(RuntimeError,match='не полностью'):
        geohide.restore_dns(backup)
    assert applied == [(4,['8.8.8.8'])]
    assert [x['index'] for x in json.loads(backup.read_text())['interfaces']] == [9]


def test_direct_disconnect_stops_engines_even_if_save_fails(monkeypatch):
    monkeypatch.setattr(unified,'save_settings',lambda s: (_ for _ in ()).throw(OSError('disk full')))
    ctrl=unified.UnifiedController(Settings(desired_enabled=True,launch_at_startup=False))
    stopped=[]
    ctrl.dpi.stop=lambda:stopped.append('dpi')
    ctrl.telegram.stop=lambda:stopped.append('tg')
    result=ctrl.disconnect()
    assert stopped == ['dpi','tg']
    assert result.overall == 'error'
    assert 'Не удалось сохранить' in result.detail
    assert not ctrl.settings.desired_enabled


def test_dns_restore_failure_is_not_reported_as_off(monkeypatch):
    monkeypatch.setattr(unified,'save_settings',lambda s:None)
    ctrl=unified.UnifiedController(Settings(connect_dns=True,launch_at_startup=False),dns_off=lambda: False)
    ctrl._dns_managed=True
    result=ctrl.disconnect()
    assert result.overall == 'error'
    assert result.dns == 'error'
    assert ctrl._dns_managed is True


def test_doctor_report_never_contains_secret_paths_or_addresses():
    s=Settings(telegram_secret='fe'*16,telegram_source_dir='C:/Users/SecretUser/Documents',
               desired_enabled=True,launch_at_startup=True)
    data=create_report(s,is_windows=True,admin=True,tray_available=True,
                       telegram_available=False,dpi_available=True,dns_backup_present=True,
                       startup_mode='task')
    text=json.dumps(data)
    assert s.telegram_secret not in text
    assert 'SecretUser' not in text
    assert '127.0.0.1' not in text
    assert 'administrator' in text
    assert data['desired_connection']=='on'
    assert data['dns_recovery_pending']


def test_doctor_rejects_unexpected_startup_status():
    s=Settings()
    kwargs=dict(is_windows=False,admin=False,tray_available=False,
                telegram_available=False,dpi_available=False,dns_backup_present=False)
    assert create_report(s,startup_mode='C:/Users/Private',**kwargs)['startup_registration']=='unknown'


def test_doctor_can_write_windowed_exe_report(tmp_path, monkeypatch):
    from vorqeli_connect import doctor
    monkeypatch.setattr(doctor,'collect_report',lambda:{'schema':1,'telegram_secret_status':'configured'})
    monkeypatch.setattr(doctor.sys,'stdout',None)
    output=tmp_path/'report.json'
    assert doctor.print_diagnostic(output)==output
    assert json.loads(output.read_text(encoding='utf-8'))['schema']==1
