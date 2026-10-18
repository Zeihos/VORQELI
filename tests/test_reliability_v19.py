"""v0.19 regression tests for crash-recovery and one-click lifecycle."""
import json
import queue
from types import SimpleNamespace

import pytest

from vorqeli_connect import geohide, unified, app
from vorqeli_connect.config import Settings


def record(index, ips, manual=''):
    return {'index': index, 'alias': f'Adapter {index}', 'before': list(ips), 'manual': manual}


def test_failed_dns_enable_rolls_back_only_touched_adapters(tmp_path, monkeypatch):
    path = tmp_path / 'dns-restore.json'
    state = {1: ['1.1.1.1'], 2: ['8.8.8.8'], 3: ['9.9.9.9']}
    original = {i: list(v) for i, v in state.items()}
    calls = []
    monkeypatch.setattr(geohide, 'query_dns_state',
                        lambda: [record(i, ips, ips[0]) for i, ips in state.items()])

    def apply(index, addresses):
        calls.append((index, addresses))
        if index == 2 and addresses == list(geohide.GEOHIDE_IPV4):
            raise RuntimeError('Windows refused adapter 2')
        state[index] = list(addresses or original[index])

    monkeypatch.setattr(geohide, '_apply_one', apply)
    with pytest.raises(RuntimeError, match='Windows refused'):
        geohide.enable_dns(path, probe=False)
    assert state == original
    assert not path.exists()
    assert calls == [(1, list(geohide.GEOHIDE_IPV4)),
                     (2, list(geohide.GEOHIDE_IPV4)),
                     (1, ['1.1.1.1'])]
    assert all(index != 3 for index, _ in calls)


def test_failed_dns_enable_keeps_only_unresolved_adapters(tmp_path, monkeypatch):
    path = tmp_path / 'dns-restore.json'
    state = {1: ['1.1.1.1'], 2: ['8.8.8.8']}
    monkeypatch.setattr(geohide, 'query_dns_state',
                        lambda: [record(i, ips, '1.1.1.1' if i == 1 else '8.8.8.8')
                                 for i, ips in state.items()])

    def apply(index, addresses):
        if index == 1 and addresses == ['1.1.1.1']:
            raise OSError('rollback blocked')
        if index == 2:
            raise OSError('apply blocked')
        state[index] = list(addresses)

    monkeypatch.setattr(geohide, '_apply_one', apply)
    with pytest.raises(RuntimeError, match='Восстановление не завершено'):
        geohide.enable_dns(path, probe=False)
    assert path.exists()
    assert [x['index'] for x in json.loads(path.read_text(encoding='utf-8'))['interfaces']] == [1]


def test_failed_dns_enable_no_adapter_changed_removes_backup(tmp_path, monkeypatch):
    path = tmp_path / 'dns-restore.json'
    monkeypatch.setattr(geohide, 'query_dns_state', lambda:[record(5,['9.9.9.9'],'9.9.9.9')])
    monkeypatch.setattr(geohide, '_apply_one', lambda *args: (_ for _ in ()).throw(OSError('no change')))
    with pytest.raises(OSError,match='no change'):
        geohide.enable_dns(path,probe=False)
    assert not path.exists()


class FakeTelegram:
    def __init__(self, ready=False):
        self.running = True
        self.ready = ready
        self.calls = []
    def stop(self):
        self.calls.append('stop')
        self.running = False
    def start(self, spec, logfile, env=None):
        self.calls.append('start')
        self.running = True
        self.ready = True


def _telegram_controller(monkeypatch, worker):
    monkeypatch.setattr(unified, 'save_settings', lambda *_: None)
    monkeypatch.setattr(unified, 'build_worker_spec', lambda port: object())
    monkeypatch.setattr(unified, 'port_is_listening', lambda port: worker.ready)
    monkeypatch.setattr(unified, 'port_is_free', lambda port: True)
    monkeypatch.setattr(unified.time, 'sleep', lambda *_: None)
    settings = Settings(telegram_secret='a'*32, connect_dpi=False,
                        connect_dns=False, connect_telegram=True,launch_at_startup=False)
    c = unified.UnifiedController(settings)
    c.telegram = worker
    return c


def test_unresponsive_own_telegram_is_restarted(monkeypatch):
    worker = FakeTelegram(ready=False)
    c = _telegram_controller(monkeypatch,worker)
    assert c.connect().overall == 'connected'
    assert worker.calls == ['stop','start']


def test_responsive_worker_is_not_restarted(monkeypatch):
    worker = FakeTelegram(ready=True)
    c = _telegram_controller(monkeypatch,worker)
    assert c.connect().overall == 'connected'
    assert worker.calls == []


def test_foreign_port_never_killed(monkeypatch):
    worker = FakeTelegram(ready=False)
    worker.running = False
    c = _telegram_controller(monkeypatch,worker)
    monkeypatch.setattr(unified, 'port_is_free', lambda port: False)
    result = c.connect()
    assert result.overall == 'error'
    assert 'другой программой' in result.detail
    # Error cleanup calls stop() on *our* child handle only; it never kills the foreign owner.
    assert worker.calls == ['stop']


def test_hide_to_tray_does_not_block_on_disk_failure(monkeypatch):
    monkeypatch.setattr(app,'save_settings',lambda *_: (_ for _ in ()).throw(OSError('disk full')))
    calls=[]
    fake=SimpleNamespace(state=lambda:'normal',settings=Settings(),geometry=lambda:'1100x720',
                         _tray_ready=True, withdraw=lambda:calls.append('hide'),
                         iconify=lambda:calls.append('minimize'), detail='')
    app.ConnectApp.hide_to_tray(fake)
    assert calls == ['hide']
    assert 'не сохранено' in fake.detail


def test_real_exit_still_stops_engines_on_disk_failure(monkeypatch):
    monkeypatch.setattr(app,'save_settings',lambda *_: (_ for _ in ()).throw(OSError('disk full')))
    calls=[]
    class FakeThread:
        def __init__(self, target, **kwargs):self.target=target
        def start(self):self.target()
    monkeypatch.setattr(app.threading,'Thread',FakeThread)
    class Controller:
        def disconnect(self,remember):
            calls.append(('disconnect',remember))
            return SimpleNamespace(overall='off')
    fake=SimpleNamespace(_quitting=False,settings=Settings(),geometry=lambda:'1100x720',
                         controller=Controller(),events=queue.Queue(),after=lambda *_:calls.append('after'),
                         _check_exit=lambda:None)
    app.ConnectApp.quit_app(fake)
    assert fake._quitting
    assert calls == [('disconnect',False),'after']
    assert fake.events.get_nowait()[0] == 'exit_done'


def test_restore_after_crash_skips_adapters_never_modified(tmp_path, monkeypatch):
    backup=tmp_path/'dns-restore.json'
    records=[record(1,['1.1.1.1'],'1.1.1.1'),record(2,['8.8.8.8'],'8.8.8.8')]
    geohide._save_state(records,backup)
    current=[record(1,list(geohide.GEOHIDE_IPV4)),record(2,['8.8.8.8'])]
    monkeypatch.setattr(geohide,'query_dns_state',lambda:current)
    applied=[]
    def apply(idx, addresses):
        applied.append((idx, addresses))
        for adapter in current:
            if adapter['index'] == idx:
                adapter['before'] = addresses
    monkeypatch.setattr(geohide,'_apply_one',apply)
    assert geohide.restore_dns(backup)
    assert applied == [(1,['1.1.1.1'])]
    assert not backup.exists()

def test_restore_after_crash_when_nothing_changed(tmp_path, monkeypatch):
    backup=tmp_path/'dns-restore.json'
    geohide._save_state([record(4,['9.9.9.9'],'9.9.9.9')],backup)
    monkeypatch.setattr(geohide,'query_dns_state',lambda:[record(4,['9.9.9.9'])])
    monkeypatch.setattr(geohide,'_apply_one',lambda *args: (_ for _ in ()).throw(AssertionError('unneeded change')))
    assert geohide.restore_dns(backup)
    assert not backup.exists()


def test_tray_backend_only_reports_ready_after_setup_callback():
    calls=[]
    q=queue.Queue()
    class FakeTray:
        def run(self,setup):
            calls.append('registered')
            setup(self)
    fake=SimpleNamespace(_tray=FakeTray(),events=q)
    app.ConnectApp._run_tray(fake)
    assert calls == ['registered']
    assert [q.get_nowait()[0],q.get_nowait()[0]] == ['tray_ready','tray_stopped']


def test_failed_tray_does_not_hide_autostart_window():
    calls=[]
    fake=SimpleNamespace(_start_minimized=True,_quitting=False,_tray_ready=False,
                         iconify=lambda:calls.append('iconify'),withdraw=lambda:calls.append('withdraw'))
    app.ConnectApp._minimize_after_startup(fake)
    assert calls == ['iconify']


def test_ready_tray_can_safely_hide_autostart_window():
    calls=[]
    fake=SimpleNamespace(_start_minimized=True,_quitting=False,_tray_ready=True,
                         iconify=lambda:calls.append('iconify'),withdraw=lambda:calls.append('withdraw'))
    app.ConnectApp._minimize_after_startup(fake)
    assert calls == ['withdraw']
    assert not fake._start_minimized
