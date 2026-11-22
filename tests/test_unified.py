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

def test_single_connect_starts_all_three_selected_components(monkeypatch, tmp_path):
    """One request must activate all selected modules without real networking."""
    monkeypatch.setattr(unified, 'save_settings', lambda settings: None)
    monkeypatch.setattr(unified, 'build_dpi_spec',
                        lambda bundle, mode: SimpleNamespace(argv=('winws',), label=mode))
    monkeypatch.setattr(unified, 'build_worker_spec',
                        lambda port: SimpleNamespace(argv=('telegram',), label='Telegram'))
    monkeypatch.setattr(unified, 'port_is_free', lambda port: True)
    monkeypatch.setattr(unified, 'port_is_listening', lambda port: True)
    monkeypatch.setattr(unified.time, 'sleep', lambda seconds: None)
    settings = Settings(dpi_mode='alt1', launch_at_startup=False)
    applied = []
    controller = unified.UnifiedController(
        settings, assets=lambda **kwargs: tmp_path,
        dns_on=lambda: applied.append('dns'))
    controller.dpi = FakeEngine()
    controller.telegram = FakeEngine()
    result = controller.connect()
    assert result.overall == 'connected'
    assert (result.dpi, result.telegram, result.dns) == ('on', 'on', 'on')
    assert controller.dpi.started and controller.telegram.started
    assert applied == ['dns']


def test_connect_keeps_partial_status_if_dns_fails(monkeypatch, tmp_path):
    monkeypatch.setattr(unified, 'save_settings', lambda settings: None)
    monkeypatch.setattr(unified, 'build_dpi_spec',
                        lambda bundle, mode: SimpleNamespace(argv=('winws',), label=mode))
    monkeypatch.setattr(unified, 'build_worker_spec',
                        lambda port: SimpleNamespace(argv=('telegram',), label='Telegram'))
    monkeypatch.setattr(unified, 'port_is_free', lambda port: True)
    monkeypatch.setattr(unified, 'port_is_listening', lambda port: True)
    monkeypatch.setattr(unified.time, 'sleep', lambda seconds: None)
    def failed_dns():
        raise RuntimeError('DNS adapter unavailable')
    controller = unified.UnifiedController(
        Settings(dpi_mode='alt1', launch_at_startup=False),
        assets=lambda **kwargs: tmp_path, dns_on=failed_dns)
    controller.dpi = FakeEngine()
    controller.telegram = FakeEngine()
    result = controller.connect()
    assert result.overall == 'partial'
    assert (result.dpi, result.telegram, result.dns) == ('on', 'on', 'error')
    assert 'DNS adapter unavailable' in result.detail


def test_legacy_auto_is_always_alt_only(monkeypatch, tmp_path):
    from vorqeli_connect import unified
    monkeypatch.setattr(unified, 'save_settings', lambda _: None)
    monkeypatch.setattr(unified, 'build_dpi_spec',
                        lambda bundle, mode: SimpleNamespace(argv=('winws',), label=mode))
    profiles_seen = []
    def selector(**kwargs):
        profiles_seen.extend(kwargs['profiles'])
        kwargs['start']('alt1')
        return SimpleNamespace(active_mode='alt1', warning='', all_targets_reachable=True)
    monkeypatch.setattr(unified, 'select_strategy', selector)
    monkeypatch.setattr(unified.time, 'sleep', lambda x: None)
    ctrl = unified.UnifiedController(
        Settings(dpi_mode='auto', connect_dpi=True,
                 connect_telegram=False, connect_dns=False, launch_at_startup=False),
        assets=lambda **kw: tmp_path)
    ctrl.dpi = FakeEngine()
    assert ctrl.connect().dpi == 'on'
    assert set(profiles_seen) == set(unified.ALT_PRIORITY)
    assert len(profiles_seen) == 13


def test_cached_hosts_reconnect_reports_explicit_warning(monkeypatch, tmp_path):
    from vorqeli_connect import unified
    monkeypatch.setattr(unified, 'save_settings', lambda _: None)
    monkeypatch.setattr(unified, 'STATE_FILE', tmp_path / 'dns.json')
    monkeypatch.setattr(unified, 'DOH_STATE_FILE', tmp_path / 'doh.json')
    monkeypatch.setattr(unified, 'enable_hosts_only',
                        lambda: {'reused_verified': True, 'fresh': False})
    settings = Settings(connect_dpi=False, connect_telegram=False,
                        connect_dns=True, launch_at_startup=False)
    controller = unified.UnifiedController(settings)
    result = controller.connect()
    assert result.dns == 'on'
    assert 'проверенного локального блока' in result.detail


def test_cancel_during_telegram_start_stops_previously_started_dpi(monkeypatch, tmp_path):
    """Never claim OFF with a WinWS process still owned by VORQELI."""
    monkeypatch.setattr(unified, 'save_settings', lambda _: None)
    monkeypatch.setattr(unified, 'build_dpi_spec',
                        lambda bundle, mode: SimpleNamespace(argv=('winws',), label=mode))
    monkeypatch.setattr(unified, 'build_worker_spec',
                        lambda port: SimpleNamespace(argv=('telegram',), label='tg'))
    monkeypatch.setattr(unified, 'port_is_free', lambda port: True)
    monkeypatch.setattr(unified.time, 'sleep', lambda seconds: None)
    settings = Settings(dpi_mode='alt1', connect_dpi=True, connect_telegram=True,
                        connect_dns=False, launch_at_startup=False)
    controller = unified.UnifiedController(settings, assets=lambda **kwargs: tmp_path)
    controller.dpi = FakeEngine()
    class CancelWhenStarted(FakeEngine):
        def start(self, *args, **kwargs):
            super().start(*args, **kwargs)
            controller.request_disconnect()
    controller.telegram = CancelWhenStarted()
    monkeypatch.setattr(unified, 'port_is_listening', lambda port: False)
    result = controller.connect()
    assert result.overall == 'off'
    assert result.dpi == 'off' and result.telegram == 'off'
    assert not controller.dpi.running and not controller.telegram.running
    assert controller.active_dpi_mode is None
    assert not settings.desired_enabled


def test_cancel_during_hosts_apply_restores_overlay_and_stops_dpi(monkeypatch, tmp_path):
    """A late OFF during a blocking HOSTS apply must immediately clean up."""
    monkeypatch.setattr(unified, 'save_settings', lambda _: None)
    monkeypatch.setattr(unified, 'build_dpi_spec',
                        lambda bundle, mode: SimpleNamespace(argv=('winws',), label=mode))
    monkeypatch.setattr(unified.time, 'sleep', lambda seconds: None)
    settings = Settings(dpi_mode='alt1', connect_dpi=True, connect_telegram=False,
                        connect_dns=True, launch_at_startup=False)
    actions = []
    controller = None
    def on_hosts():
        actions.append('apply')
        controller.request_disconnect()
    controller = unified.UnifiedController(
        settings, assets=lambda **kwargs: tmp_path,
        dns_on=on_hosts, dns_off=lambda: actions.append('restore') or True)
    controller.dpi = FakeEngine()
    result = controller.connect()
    assert result.overall == 'off'
    assert (result.dpi, result.telegram, result.dns) == ('off','off','off')
    assert actions == ['apply', 'restore']
    assert not controller.dpi.running and not controller._dns_managed
    assert not settings.desired_enabled


def test_failed_cancel_cleanup_never_reports_false_off(monkeypatch, tmp_path):
    monkeypatch.setattr(unified, 'save_settings', lambda _: None)
    monkeypatch.setattr(unified, 'build_dpi_spec',
                        lambda bundle, mode: SimpleNamespace(argv=('winws',), label=mode))
    monkeypatch.setattr(unified.time, 'sleep', lambda seconds: None)
    settings = Settings(dpi_mode='alt1', connect_dpi=True, connect_telegram=False,
                        connect_dns=True, launch_at_startup=False)
    controller = None
    def on_hosts():
        controller.request_disconnect()
    controller = unified.UnifiedController(
        settings, assets=lambda **kwargs: tmp_path, dns_on=on_hosts,
        dns_off=lambda: True)
    class UnstoppableEngine(FakeEngine):
        def stop(self, *args, **kwargs):
            raise OSError('driver still busy')
    controller.dpi = UnstoppableEngine()
    result = controller.connect()
    assert result.overall == 'error'
    assert result.dpi == 'error'
    assert 'driver still busy' in result.detail
    assert controller.dpi.running
