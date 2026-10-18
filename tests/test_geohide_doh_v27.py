"""Offline native DoH lifecycle and safe rollback / no-plaintext-fallback tests."""
from __future__ import annotations
import json
from pathlib import Path
import pytest
from vorqeli_connect import geohide, geohide_doh as doh
from vorqeli_connect.config import Settings, load_settings, save_settings
from vorqeli_connect.doctor import create_report
from vorqeli_connect.unified import UnifiedController


@pytest.fixture
def env(tmp_path, monkeypatch):
    maps = {}
    actions = []
    dns = {'on': False, 'fail': False}
    monkeypatch.setattr(geohide, '_dns_probe', lambda: actions.append('probe'))
    monkeypatch.setattr(geohide, '_ps', lambda cmd: actions.append('capability'))
    monkeypatch.setattr(doh, '_read_mappings', lambda: dict(maps))
    def add(ip):
        actions.append(('add', ip))
        maps[ip] = {'template': geohide.DOH_TEMPLATE, 'upgrade': True, 'fallback': False}
    def remove(ip):
        actions.append(('remove', ip))
        maps.pop(ip, None)
    monkeypatch.setattr(doh, '_add_mapping', add)
    monkeypatch.setattr(doh, '_remove_mapping', remove)
    def start(path, *, probe=True):
        actions.append('dns_on')
        if dns['fail']:
            raise RuntimeError('DNS adapter failed')
        path.write_text('dns-backup', encoding='utf-8')
        dns['on'] = True
        return 1
    def stop(path):
        actions.append('dns_off')
        path.unlink()
        dns['on'] = False
        return True
    monkeypatch.setattr(geohide, 'enable_dns', start)
    monkeypatch.setattr(geohide, 'restore_dns', stop)
    return {'maps': maps, 'actions': actions, 'dns': dns,
            'path': tmp_path/'dns-restore.json',
            'journal': tmp_path/'dns-restore-doh.json'}


def _mapping(template=geohide.DOH_TEMPLATE, upgrade=True, fallback=False):
    return {'template': template, 'upgrade': upgrade, 'fallback': fallback}


def test_doh_success_and_cleanup_preserves_order(env):
    path = env['path']
    assert doh.enable_geo_dns(mode='doh', path=path) == 1
    assert env['journal'].is_file()
    assert env['actions'][:2] == ['probe', 'capability']
    assert env['actions'].index('dns_on') > env['actions'].index(('add', geohide.GEOHIDE_IPV4[-1]))
    assert all(doh._expected(v) for v in env['maps'].values())
    assert doh.restore_geo_dns(path) is True
    assert env['actions'].index('dns_off') < env['actions'].index(('remove',geohide.GEOHIDE_IPV4[0]))
    assert not path.exists() and not env['journal'].exists() and not env['maps']


def test_existing_exact_mappings_are_not_removed(env):
    first = geohide.GEOHIDE_IPV4[0]
    env['maps'][first] = _mapping()
    doh.enable_geo_dns(mode='doh', path=env['path'], probe=False)
    assert json.loads(env['journal'].read_text())['created'] == [geohide.GEOHIDE_IPV4[1]]
    doh.restore_geo_dns(env['path'])
    assert env['maps'] == {first: _mapping()}
    assert ('remove', first) not in env['actions']


def test_exact_preexisting_both_mappings_untouched(env):
    for ip in geohide.GEOHIDE_IPV4:
        env['maps'][ip] = _mapping()
    doh.enable_secure_dns(env['path'], probe=False)
    assert json.loads(env['journal'].read_text())['created'] == []
    assert ('add', geohide.GEOHIDE_IPV4[0]) not in env['actions']
    doh.restore_geo_dns(env['path'])
    assert len(env['maps']) == 2


@pytest.mark.parametrize('conflict', [
    _mapping('https://someone-else.example/dns-query'),
    _mapping(fallback=True),
    _mapping(upgrade=False),
])
def test_existing_conflict_fails_before_modifications(env, conflict):
    env['maps'][geohide.GEOHIDE_IPV4[0]] = conflict
    with pytest.raises(RuntimeError, match='другой DoH'):
        doh.enable_secure_dns(env['path'], probe=False)
    assert not env['journal'].exists()
    assert not env['path'].exists()
    assert env['actions'] == ['capability']


def test_unsupported_windows_fails_without_plaintext_fallback(env,monkeypatch):
    def unsupported(cmd):
        raise RuntimeError('Не поддерживается системой')
    monkeypatch.setattr(geohide,'_ps',unsupported)
    with pytest.raises(RuntimeError,match='поддерживается'):
        doh.enable_geo_dns(mode='doh',path=env['path'],probe=False)
    assert not env['path'].exists() and not env['journal'].exists()
    assert 'dns_on' not in env['actions']


def test_restore_rejects_changed_mapping_preserves_journal(env):
    doh.enable_secure_dns(env['path'],probe=False)
    env['maps'][geohide.GEOHIDE_IPV4[1]] = _mapping('https://another.example/dns-query')
    with pytest.raises(RuntimeError,match='не полностью'):
        doh.restore_geo_dns(env['path'])
    assert not env['path'].exists()
    assert env['journal'].exists()
    assert env['maps'][geohide.GEOHIDE_IPV4[1]]['template'].startswith('https://another.')
    assert json.loads(env['journal'].read_text())['created'] == [geohide.GEOHIDE_IPV4[1]]


def test_restore_refuses_to_remove_encrypted_mapping_when_dns_rollback_fails(env,monkeypatch):
    doh.enable_secure_dns(env['path'],probe=False)
    monkeypatch.setattr(geohide,'restore_dns',lambda path: (_ for _ in ()).throw(RuntimeError('offline')))
    with pytest.raises(RuntimeError,match='offline'):
        doh.restore_geo_dns(env['path'])
    assert len(env['maps']) == 2 and env['journal'].exists() and env['path'].exists()


def test_restore_after_crash_without_adapter_backup(env):
    doh._save_journal(list(geohide.GEOHIDE_IPV4),env['journal'])
    env['maps'][geohide.GEOHIDE_IPV4[0]] = _mapping()
    assert doh.restore_geo_dns(env['path'])
    assert not env['journal'].exists() and not env['maps']


def test_stale_journal_refuses_new_connection(env):
    doh._save_journal(list(geohide.GEOHIDE_IPV4),env['journal'])
    with pytest.raises(RuntimeError,match='Сначала восстановите DNS'):
        doh.enable_secure_dns(env['path'],probe=False)
    with pytest.raises(RuntimeError,match='Сначала восстановите GeoHide'):
        doh.enable_geo_dns(mode='plain',path=env['path'],probe=False)


def test_repeated_secure_connect_verifies_existing_mappings(env):
    doh.enable_secure_dns(env['path'],probe=False)
    assert doh.enable_secure_dns(env['path'],probe=False)==1
    assert len([x for x in env['actions'] if isinstance(x,tuple) and x[0]=='add'])==2
    env['maps'].pop(geohide.GEOHIDE_IPV4[0])
    with pytest.raises(RuntimeError,match='изменились'):
        doh.enable_secure_dns(env['path'],probe=False)


def test_failed_dns_apply_rolls_back_doh(env):
    env['dns']['fail'] = True
    with pytest.raises(RuntimeError,match='DNS adapter failed'):
        doh.enable_secure_dns(env['path'],probe=False)
    assert env['maps']=={} and not env['journal'].exists() and not env['path'].exists()


def test_dns_fail_and_mapping_rollback_error_retains_journal(env,monkeypatch):
    env['dns']['fail'] = True
    def fail_removal(ip):
        raise OSError('access denied')
    monkeypatch.setattr(doh,'_remove_mapping',fail_removal)
    with pytest.raises(RuntimeError,match='требуется восстановление'):
        doh.enable_secure_dns(env['path'],probe=False)
    assert env['journal'].exists()
    assert len(env['maps'])==2


def test_delete_ignored_by_windows_keeps_recovery_journal(env,monkeypatch):
    doh.enable_secure_dns(env['path'],probe=False)
    monkeypatch.setattr(doh,'_remove_mapping',lambda ip: None)
    with pytest.raises(RuntimeError,match='не подтвердил'):
        doh.restore_geo_dns(env['path'])
    assert env['journal'].exists()


def test_journal_rejects_malformed_or_injected_ips(tmp_path):
    path=tmp_path/'doh.json'
    for data in ({'provider':'geohide_doh','version':1,'created':['1.1.1.1']},
                 {'provider':'geohide_doh','version':1,'created':[geohide.GEOHIDE_IPV4[0]]*2},
                 {'provider':'geohide_doh','version':1,'created':['$(whoami)']},
                 {'provider':'geohide_doh','version':1,'created':'hello'},
                 {'provider':'foreign','version':1,'created':[]}):
        path.write_text(json.dumps(data))
        with pytest.raises(ValueError):doh._load_journal(path)


def test_powershell_commands_fixed_profile(monkeypatch):
    scripts=[]
    monkeypatch.setattr(geohide,'_ps',lambda s:scripts.append(s))
    doh._add_mapping(geohide.GEOHIDE_IPV4[0])
    doh._remove_mapping(geohide.GEOHIDE_IPV4[0])
    assert '-AutoUpgrade $True' in scripts[0]
    assert '-AllowFallbackToUdp $False' in scripts[0]
    assert geohide.DOH_TEMPLATE in scripts[0]
    with pytest.raises(ValueError):doh._add_mapping('$(whoami)')
    assert len(scripts)==2


def test_dns_choice_validation_and_persistence(tmp_path):
    path=tmp_path/'settings.json'
    assert Settings().dns_mode=='plain'
    settings=Settings(dns_mode='doh')
    save_settings(settings,path)
    assert load_settings(path).dns_mode=='doh'
    raw=json.loads(path.read_text());raw['dns_mode']='$(whoami)'
    path.write_text(json.dumps(raw))
    assert load_settings(path).dns_mode=='plain'


def test_doctor_has_no_ips_or_server_url():
    obj=create_report(Settings(dns_mode='doh'),is_windows=True,admin=False,
                      tray_available=True,telegram_available=False,dpi_available=False,
                      dns_backup_present=True,doh_recovery_pending=True)
    s=json.dumps(obj)
    assert obj['geohide_transport']=='doh' and obj['doh_recovery_pending']
    assert geohide.GEOHIDE_IPV4[0] not in s and geohide.DOH_TEMPLATE not in s


def test_controller_selects_doh_only_when_explicit(monkeypatch):
    from vorqeli_connect import unified
    modes=[]
    monkeypatch.setattr(unified,'enable_geo_dns',lambda *,mode:modes.append(mode))
    ctrl=UnifiedController(Settings(dns_mode='plain',launch_at_startup=False))
    ctrl.dns_on()
    ctrl.settings.dns_mode='doh'
    ctrl.dns_on()
    assert modes==['plain','doh']


def test_unknown_mode_rejected_without_dns_changes(env):
    with pytest.raises(ValueError):doh.enable_geo_dns(mode='tls',path=env['path'])
    assert not env['actions']


def test_empty_doh_journal_cleans_without_windows_cmdlets(tmp_path, monkeypatch):
    journal=tmp_path/'journal.json'
    doh._save_journal([],journal)
    monkeypatch.setattr(doh,'_read_mappings',lambda: (_ for _ in ()).throw(AssertionError('must not query')))
    assert doh.restore_doh(journal)
    assert not journal.exists()


def test_global_windows_mapping_parser_rejects_unexpected_flags(monkeypatch):
    items=[{'ServerAddress': geohide.GEOHIDE_IPV4[0],
            'DohTemplate': geohide.DOH_TEMPLATE,
            'AutoUpgrade': 'true', 'AllowFallbackToUdp': False}]
    monkeypatch.setattr(geohide,'_ps',lambda _:json.dumps(items))
    with pytest.raises(RuntimeError,match='неоднозначную'):
        doh._read_mappings()


def test_windows_mapping_parser_handles_ps_single_object(monkeypatch):
    item={'ServerAddress':geohide.GEOHIDE_IPV4[1],
          'DohTemplate':geohide.DOH_TEMPLATE,
          'AutoUpgrade':True,'AllowFallbackToUdp':False}
    monkeypatch.setattr(geohide,'_ps',lambda _:json.dumps(item))
    assert doh._read_mappings()=={geohide.GEOHIDE_IPV4[1]:_mapping()}


def test_doctor_non_mutating_windows_preflight_schema():
    import runpy
    from pathlib import Path
    check = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts" / "windows_doh_readonly_smoke.py"))["check"]
    import os
    if os.name != 'nt':
        assert check()=={'platform':'other','native_doh_cmdlets_available':False}


def test_uninstall_detects_orphan_doh_journal(tmp_path):
    from vorqeli_connect.uninstall_safety import cleanup_for_uninstall
    path=tmp_path/'dns-restore.json'
    journal=tmp_path/'dns-restore-doh.json'
    journal.write_text('leftover')
    called=[]
    def cleanup():
        called.append('recover')
        journal.unlink()
        return True
    result=cleanup_for_uninstall(check_running=lambda:False,disable_startup=lambda _: 'off',
                                 restore=cleanup,backup=path)
    assert result.success and called==['recover']


def test_uninstall_blocks_on_leftover_doh_journal(tmp_path):
    from vorqeli_connect.uninstall_safety import cleanup_for_uninstall
    path=tmp_path/'dns-restore.json'
    journal=tmp_path/'dns-restore-doh.json'
    journal.write_text('leftover')
    result=cleanup_for_uninstall(check_running=lambda:False,disable_startup=lambda _: 'off',
                                 restore=lambda:True,backup=path)
    assert not result.success and journal.exists()


def test_ui_dns_selection_cannot_change_while_connected(monkeypatch):
    from vorqeli_connect.app import ConnectApp
    fake=object.__new__(ConnectApp)
    fake.settings=Settings(dns_mode='plain',desired_enabled=True)
    fake.running_job=False
    fake.detail=''
    draws=[]
    monkeypatch.setattr(ConnectApp,'_draw',lambda self:draws.append(True))
    # Tk subclass __new__ initializes no GUI; this must return before I/O.
    fake._set_dns_mode('doh')
    assert fake.settings.dns_mode=='plain' and draws
    assert 'Отключиться' in fake.detail


def test_restore_doh_checks_adapter_restore_return_value(env,monkeypatch):
    doh.enable_secure_dns(env['path'],probe=False)
    monkeypatch.setattr(geohide,'restore_dns',lambda path:False)
    with pytest.raises(RuntimeError,match='не подтвердил'):
        doh.restore_geo_dns(env['path'])
    assert env['journal'].exists() and len(env['maps'])==2


def test_doh_mapping_parser_handles_null_json(monkeypatch):
    monkeypatch.setattr(geohide,'_ps',lambda script:'null')
    assert doh._read_mappings()=={}
