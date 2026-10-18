import threading
from types import SimpleNamespace
from pathlib import Path
import pytest
from vorqeli_connect.config import Settings
from vorqeli_connect import unified


class FakeEngine:
    def __init__(self,*args):self.running=False;self.started=False
    def start(self,*args,**kwargs):self.running=True;self.started=True
    def stop(self,*args,**kwargs):self.running=False


def test_disabled_components(monkeypatch,tmp_path):
    monkeypatch.setattr(unified.EngineProcess,'start',lambda *args,**kw:None)
    monkeypatch.setattr(unified,'save_settings',lambda s:None)
    events=[]
    state=Settings(connect_dpi=False,connect_telegram=False,connect_dns=False,launch_at_startup=False)
    c=unified.UnifiedController(state,emit=lambda k,v:events.append(k))
    r=c.connect()
    assert state.desired_enabled
    assert r.overall=='error'
    c.disconnect()
    assert not state.desired_enabled


def test_dns_only_remembers_state(monkeypatch,tmp_path):
    monkeypatch.setattr(unified,'save_settings',lambda s:None)
    monkeypatch.setattr(unified,'STATE_FILE',tmp_path/'dns.json')
    applied=[]
    state=Settings(connect_dpi=False,connect_telegram=False,connect_dns=True,launch_at_startup=False)
    c=unified.UnifiedController(state,dns_on=lambda:applied.append('on'),dns_off=lambda:applied.append('off'))
    assert c.connect().overall=='connected'
    assert state.desired_enabled
    assert c.disconnect().overall=='off'
    assert not state.desired_enabled
    assert applied==['on','off']


def test_telegram_worker_spec_requires_install_or_frozen(monkeypatch):
    from vorqeli_connect import bundled_telegram as tg
    monkeypatch.setattr(tg,'proxy_available',lambda:True)
    s=tg.build_worker_spec(1443)
    assert '--tg-worker' in s.argv
    assert '--port' in s.argv
    with pytest.raises(ValueError):tg.build_worker_spec(12)


def test_false_proxy_install_raises(monkeypatch):
    from vorqeli_connect import bundled_telegram as tg
    monkeypatch.setattr(tg,'proxy_available',lambda:False)
    with pytest.raises(RuntimeError,match='tg-ws-proxy'):
        tg.build_worker_spec(1443)


def test_explicit_off_wins_over_queued_connect(monkeypatch,tmp_path):
    monkeypatch.setattr(unified,'save_settings',lambda s:None)
    called=[]
    settings=Settings(connect_dpi=False,connect_telegram=False,connect_dns=True,
                      launch_at_startup=False)
    c=unified.UnifiedController(settings, dns_on=lambda:called.append('dns'))
    c.request_connect()
    c.request_disconnect()
    result=c.connect(requested=False)
    assert result.overall=='off'
    assert settings.desired_enabled is False
    assert called==[]


def test_runtime_health_reports_module_failure(monkeypatch,tmp_path):
    monkeypatch.setattr(unified,'save_settings',lambda s:None)
    monkeypatch.setattr(unified,'STATE_FILE',tmp_path/'dns.json')
    settings=Settings(desired_enabled=True,connect_dpi=True,connect_telegram=False,
                      connect_dns=True, launch_at_startup=False)
    c=unified.UnifiedController(settings)
    c.dpi._proc=type('P',(),{'poll':lambda self:None})()
    # Real process is alive but GeoHide DNS is missing => partial connection.
    health=c.runtime_health()
    assert health.overall=='partial'
    assert health.dpi=='on' and health.dns=='error'
