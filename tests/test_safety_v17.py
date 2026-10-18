import json
from types import SimpleNamespace
import pytest
from vorqeli_connect import config, unified
from vorqeli_connect.config import Settings
from vorqeli_connect.engine_processes import EngineProcess


def test_bad_desired_enabled_uses_backup(tmp_path):
    path = tmp_path / 'settings.json'
    path.write_text(json.dumps({'desired_enabled': 'false'}), encoding='utf-8')
    path.with_suffix('.bak').write_text(json.dumps({'desired_enabled': False}), encoding='utf-8')
    assert config.load_settings(path).desired_enabled is False


@pytest.mark.parametrize('override', [
    {'launch_at_startup':'false'}, {'connect_dns':1},
    {'telegram_port':True}, {'telegram_port':70000},
    {'dpi_mode':'something'}, {'window_geometry':'999999999x123'},
    {'telegram_secret_dpapi':['bad']}, {'connect_telegram':None},
])
def test_invalid_settings_values_cannot_enable_network_automatically(tmp_path, override):
    path=tmp_path/'settings.json'
    path.write_text(json.dumps({'desired_enabled':True, **override}), encoding='utf-8')
    assert config.load_settings(path).desired_enabled is False


def test_requested_connect_does_not_switch_on_after_disk_error(monkeypatch):
    ctrl = unified.UnifiedController(Settings(launch_at_startup=False))
    monkeypatch.setattr(unified,'save_settings',lambda s: (_ for _ in ()).throw(OSError('disk full')))
    with pytest.raises(OSError, match='disk full'):
        ctrl.request_connect()
    assert ctrl.settings.desired_enabled is False
    assert not ctrl._cancel.is_set()


def test_requested_disconnect_cancels_even_when_disk_is_full(monkeypatch):
    ctrl = unified.UnifiedController(Settings(desired_enabled=True,launch_at_startup=False,
                                              connect_dpi=False,connect_dns=False,connect_telegram=False))
    monkeypatch.setattr(unified,'save_settings',lambda s: (_ for _ in ()).throw(OSError('disk full')))
    with pytest.raises(OSError):ctrl.request_disconnect()
    assert not ctrl.settings.desired_enabled
    assert ctrl._cancel.is_set()
    assert ctrl.disconnect(remember=False).overall == 'off'


def test_stop_handles_process_exit_race(monkeypatch,tmp_path):
    class ExitedBetweenCheckAndTerminate:
        pid=123
        def poll(self):return None
        def terminate(self):raise ProcessLookupError()
        def wait(self,timeout=None):return 0
    e=EngineProcess('Race')
    e._proc=ExitedBetweenCheckAndTerminate()
    e._log_handle=(tmp_path/'log.txt').open('w')
    assert e.stop()
    assert e._log_handle is None


def test_stop_closes_log_even_if_wait_errors(monkeypatch,tmp_path):
    class WaitFailure:
        def poll(self):return None
        def terminate(self):pass
        def wait(self,timeout=None):raise OSError('wait failed')
    e=EngineProcess('Wait')
    e._proc=WaitFailure()
    e._log_handle=(tmp_path/'log.txt').open('w')
    with pytest.raises(OSError):e.stop()
    assert e._log_handle is None


def test_plaintext_migration_does_not_copy_secret_into_windows_backup(tmp_path,monkeypatch):
    """Emulate Windows only for config.os.name without changing global os.name."""
    from unittest.mock import Mock
    path=tmp_path/'settings.json'
    path.write_text(json.dumps({'telegram_secret':'a'*32, 'desired_enabled':False}),encoding='utf-8')
    # Avoid mutating global os.name because pathlib itself uses it.
    stub=SimpleNamespace(name='nt', fsync=config.os.fsync)
    monkeypatch.setattr(config,'os',stub)
    monkeypatch.setattr(config,'serialize_secret',lambda s:{'telegram_secret_dpapi':'encrypted_'+s[:3]})
    config.save_settings(Settings(telegram_secret='b'*32),path)
    original=path.with_suffix('.bak').read_text(encoding='utf-8')
    assert 'a'*32 not in original
    assert json.loads(original)['telegram_secret_dpapi']=='encrypted_aaa'
    assert 'b'*32 not in path.read_text(encoding='utf-8')
