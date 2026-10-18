"""Deterministic Smart DPI tests; no external network or privileged programs."""
from pathlib import Path
import json
import pytest
from vorqeli_connect.smart_dpi import (
    PROFILES, TARGETS, SelectionCancelled, Trial, https_reachable,
    probe_targets, select_strategy,
)
from vorqeli_connect.config import Settings, load_settings, save_settings
from vorqeli_connect.support_report import build_report
from vorqeli_connect.unified import ConnectionReport


class FakeEngine:
    def __init__(self, broken=()):
        self.active = None
        self.history = []
        self.broken = set(broken)

    def start(self, mode):
        self.history.append(('start', mode))
        if mode in self.broken:
            raise OSError('cannot launch')
        self.active = mode

    def stop(self):
        self.history.append(('stop', self.active))
        self.active = None

    def running(self):
        return self.active is not None

    def select(self, probes, cancelled=lambda: False):
        return select_strategy(start=self.start, stop=self.stop, running=self.running,
                               cancelled=cancelled, probe=lambda _: probes[self.active])


def test_auto_full_first_does_not_restart():
    engine=FakeEngine()
    choice=engine.select({'fake':(True,True)})
    assert choice.active_mode == 'fake'
    assert choice.all_targets_reachable and choice.warning == ''
    assert len(choice.trials) == 1
    assert engine.history == [('start','fake')]


def test_auto_selects_second_if_score_higher():
    engine=FakeEngine()
    choice=engine.select({'fake':(True,False),'multisplit':(True,True)})
    assert choice.active_mode == 'multisplit'
    assert choice.all_targets_reachable
    assert engine.history == [('start','fake'),('stop','fake'),('start','multisplit')]


def test_auto_keeps_best_partial_and_warns_not_proven():
    engine=FakeEngine()
    choice=engine.select({'fake':(True,False),'multisplit':(False,False)})
    assert choice.active_mode == 'fake'
    assert not choice.all_targets_reachable
    assert 'не подтверждена' in choice.warning
    assert engine.history == [('start','fake'),('stop','fake'),('start','multisplit'),
                              ('stop','multisplit'),('start','fake')]


def test_auto_all_unreachable_is_not_claimed_as_success():
    engine=FakeEngine()
    choice=engine.select({'fake':(False,False),'multisplit':(False,False)})
    assert choice.active_mode == 'fake'
    assert not choice.all_targets_reachable
    assert '0/2' in choice.warning


def test_auto_handles_launch_failure_then_tries_second():
    engine=FakeEngine(broken=('fake',))
    choice=engine.select({'multisplit':(True,False)})
    assert choice.active_mode == 'multisplit'
    assert choice.trials[0] == Trial('fake',0,2,False)
    assert engine.running()


def test_auto_both_launches_fail():
    engine=FakeEngine(broken=('fake','multisplit'))
    with pytest.raises(RuntimeError, match='Ни одна'):
        engine.select({})
    assert engine.active is None


def test_manual_off_before_start_prevents_launch():
    engine=FakeEngine()
    with pytest.raises(SelectionCancelled):
        engine.select({}, cancelled=lambda:True)
    assert engine.history == []


def test_manual_off_after_first_probe_never_starts_second():
    engine=FakeEngine()
    cancelled=[False]
    def probe(_):
        cancelled[0]=True
        return (False,False)
    with pytest.raises(SelectionCancelled):
        select_strategy(start=engine.start,stop=engine.stop,running=engine.running,
                        cancelled=lambda:cancelled[0],probe=probe)
    assert ('start','multisplit') not in engine.history


def test_bad_probe_shape_is_unverified_not_success():
    engine=FakeEngine()
    choice=engine.select({'fake':(True,), 'multisplit':()})
    assert not choice.all_targets_reachable
    assert all(t.reachable == 0 for t in choice.trials)


def test_broken_probe_does_not_claim_success():
    engine=FakeEngine()
    def probe(_):
        raise OSError('network down')
    selected=select_strategy(start=engine.start,stop=engine.stop,running=engine.running,
                            cancelled=lambda:False,probe=probe)
    assert not selected.all_targets_reachable


def test_probe_cancellation_between_requests():
    visited=[]
    state=[False]
    def request(url):
        visited.append(url)
        state[0]=True
        return True
    with pytest.raises(SelectionCancelled):
        probe_targets(lambda:state[0],request=request)
    assert visited == [TARGETS[0]]


def test_probe_accepts_ordinary_bool_results_without_network():
    assert probe_targets(lambda:False,request=lambda url: url == TARGETS[0]) == (True,False)


def test_probe_denies_unapproved_urls():
    with pytest.raises(ValueError):
        https_reachable('http://localhost:8080/')


def test_auto_config_can_be_saved_and_loaded(tmp_path):
    path=tmp_path/'settings.json'
    save_settings(Settings(dpi_mode='auto',launch_at_startup=False,connect_telegram=False),path)
    assert load_settings(path).dpi_mode == 'auto'


def test_auto_support_export_whitelists_mode():
    report=build_report(Settings(dpi_mode='auto'), ConnectionReport('off','off','off','off'),
                        [],'0.26.0')
    assert report['dpi_mode'] == 'auto'
    assert 'telegram_secret' not in json.dumps(report)


def test_profile_list_limited_and_ordered():
    assert PROFILES == ('fake','multisplit')
    assert len(TARGETS)==2 and all(url.startswith('https://') for url in TARGETS)


def test_unified_auto_mode_uses_real_selector_with_injected_https(monkeypatch,tmp_path):
    from vorqeli_connect import unified
    from vorqeli_connect.smart_dpi import select_strategy as real_selector
    from vorqeli_connect.engine_adapters import LaunchSpec
    monkeypatch.setattr(unified,'save_settings',lambda _:None)
    monkeypatch.setattr(unified,'APP_DIR',tmp_path)
    monkeypatch.setattr(unified.time,'sleep',lambda _:None)
    monkeypatch.setattr(unified,'build_dpi_spec',lambda folder,mode:LaunchSpec((mode,),tmp_path,mode))
    monkeypatch.setattr(unified,'select_strategy',lambda **kwargs:real_selector(
        **kwargs, probe=lambda cancelled: (True,False) if engine.mode=='fake' else (True,True)))
    events=[]
    class SimEngine:
        def __init__(self): self.mode=None;self.history=[]
        @property
        def running(self): return self.mode is not None
        def start(self,spec,*args,**kwargs):
            self.mode=spec.argv[0];self.history.append(self.mode)
        def stop(self,*args,**kwargs): self.mode=None
    engine=SimEngine()
    settings=Settings(dpi_mode='auto',connect_dpi=True,connect_telegram=False,
                      connect_dns=False,launch_at_startup=False)
    controller=unified.UnifiedController(settings,assets=lambda **kwargs:tmp_path,
                                        emit=lambda key,value:events.append((key,value)))
    controller.dpi=engine
    report=controller.connect()
    assert report.overall=='connected'
    assert controller.active_dpi_mode == 'multisplit'
    assert engine.history == ['fake','multisplit']
    assert controller.disconnect().overall=='off'
    assert controller.active_dpi_mode is None


def test_unified_auto_mode_zero_https_warns(monkeypatch,tmp_path):
    from vorqeli_connect import unified
    from vorqeli_connect.smart_dpi import select_strategy as real_selector
    from vorqeli_connect.engine_adapters import LaunchSpec
    monkeypatch.setattr(unified,'save_settings',lambda _:None)
    monkeypatch.setattr(unified,'APP_DIR',tmp_path)
    monkeypatch.setattr(unified.time,'sleep',lambda _:None)
    monkeypatch.setattr(unified,'build_dpi_spec',lambda folder,mode:LaunchSpec((mode,),tmp_path,mode))
    monkeypatch.setattr(unified,'select_strategy',lambda **kwargs:real_selector(
        **kwargs, probe=lambda cancelled:(False,False)))
    class FakeProcess:
        def __init__(self): self.mode=None
        @property
        def running(self): return self.mode is not None
        def start(self,spec,*a,**k): self.mode=spec.argv[0]
        def stop(self,*a,**k): self.mode=None
    controller=unified.UnifiedController(
        Settings(dpi_mode='auto',connect_telegram=False,connect_dns=False,launch_at_startup=False),
        assets=lambda **kw:tmp_path)
    controller.dpi=FakeProcess()
    result=controller.connect()
    assert result.overall == 'connected'  # Process alive, NOT proof of bypass.
    assert 'Работа обхода не подтверждена' in result.detail
    assert controller.active_dpi_mode == 'fake'
