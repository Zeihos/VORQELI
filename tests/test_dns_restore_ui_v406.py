"""Regression tests for GUI DNS restore concurrency, without changing real DNS."""
from __future__ import annotations
from queue import Queue
from types import SimpleNamespace as NS
from pathlib import Path

import pytest
from vorqeli_connect import app as app_module
from vorqeli_connect.app import ConnectApp


@pytest.fixture
def fake(monkeypatch,tmp_path):
    copy=tmp_path/'dns-restore.json';copy.write_text('{}',encoding='utf8')
    monkeypatch.setattr(app_module,'STATE_FILE',copy)
    monkeypatch.setattr(app_module,'DOH_STATE_FILE',tmp_path/'doh-restore.json')
    return NS(settings=NS(desired_enabled=False),_quitting=False,
              running_job=False,_disconnecting=False,_dns_restore_busy=False,
              _worker_restore_dns=lambda:None,detail='',_draw=lambda:None,
              events=Queue())


def test_two_clicks_do_not_spawn_two_workers(fake,monkeypatch):
    launches=[]
    class Thread:
        def __init__(self,**kw):
            launches.append(kw)
        def start(self):
            pass
    monkeypatch.setattr(app_module.threading,'Thread',Thread)
    ConnectApp._restore_dns(fake)
    ConnectApp._restore_dns(fake)
    assert len(launches)==1
    assert fake._dns_restore_busy is True
    assert launches[0]['name']=='GeoHideDnsRestore'


@pytest.mark.parametrize('flag',('running_job','_disconnecting','_quitting','_dns_restore_busy'))
def test_dns_restore_blocked_during_other_work(fake,monkeypatch,flag):
    setattr(fake,flag,True)
    def blocked(**kw):
        raise AssertionError('Thread must not be started')
    monkeypatch.setattr(app_module.threading,'Thread',blocked)
    ConnectApp._restore_dns(fake)


def test_failed_thread_start_releases_busy_guard(fake,monkeypatch):
    class Failed:
        def __init__(self,**kw):pass
        def start(self):raise RuntimeError('thread quota')
    monkeypatch.setattr(app_module.threading,'Thread',Failed)
    ConnectApp._restore_dns(fake)
    assert fake._dns_restore_busy is False
    assert 'thread quota' in fake.detail


def test_no_dns_backup_does_not_spawn_thread(fake,monkeypatch):
    app_module.STATE_FILE.unlink()
    monkeypatch.setattr(app_module.messagebox,'showinfo',lambda *args,**kw:None)
    def blocked(**kw):raise AssertionError('Unexpected worker')
    monkeypatch.setattr(app_module.threading,'Thread',blocked)
    ConnectApp._restore_dns(fake)
    assert fake._dns_restore_busy is False


@pytest.mark.parametrize('outcome,message',[(True,'восстановлены'),(False,'уже нет')])
def test_worker_truthful_message_and_completion_event(fake,monkeypatch,outcome,message):
    monkeypatch.setattr(app_module,'restore_geo_dns',lambda:outcome)
    ConnectApp._worker_restore_dns(fake)
    first=fake.events.get_nowait();second=fake.events.get_nowait()
    assert first[0]=='progress' and message in first[1]
    assert second==('dns_restore_done',None)


def test_worker_exception_still_sends_completion_event(fake,monkeypatch):
    def fail():raise PermissionError('blocked')
    monkeypatch.setattr(app_module,'restore_geo_dns',fail)
    ConnectApp._worker_restore_dns(fake)
    assert fake.events.get_nowait()[0]=='error'
    assert fake.events.get_nowait()==('dns_restore_done',None)


def test_network_restore_button_is_disabled_while_pending(monkeypatch):
    from vorqeli_connect import native_ui as ui
    import inspect
    source=inspect.getsource(ui.Scene.network)
    assert "'_dns_restore_busy'" in source
    assert 'enabled=not getattr' in source
    assert 'running_job' in source
    assert '_disconnecting' in source


def test_tk_poll_clears_flag_for_restore_done():
    import inspect
    source=inspect.getsource(ConnectApp._poll)
    assert "typ=='dns_restore_done'" in source
    assert 'self._dns_restore_busy = False' in source
