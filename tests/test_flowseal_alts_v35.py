"""Offline regression tests for safe Flowseal ALT1–ALT13 argv and preference handling."""
from pathlib import Path
import pytest
from vorqeli_connect.flowseal_alts import ALT_MODES, ALT_PRIORITY, alt_filename, build_alt_arguments
from vorqeli_connect.engine_adapters import build_dpi_spec
from vorqeli_connect.config import Settings, load_settings, save_settings


def fixture(tmp_path: Path, mode='alt2', extra='') -> Path:
    (tmp_path / 'bin').mkdir()
    (tmp_path / 'lists').mkdir()
    for path in ('bin/winws.exe', 'bin/tls_clienthello_www_google_com.bin',
                 'bin/quic_initial_www_google_com.bin','lists/list-general.txt',
                 'lists/list-exclude.txt','lists/ipset-exclude.txt'):
        (tmp_path/path).write_bytes(b'x')
    (tmp_path/'LICENSE.txt').write_text('MIT')
    body = ('@echo off\ncall service.bat load_game_filter\n'
            'start "zapret: %~n0" /min "%BIN%winws.exe" '
            '--wf-tcp=80,443,%GameFilterTCP% --wf-udp=443,%GameFilterUDP% ^\n'
            '--filter-udp=443 --hostlist="%LISTS%list-general.txt" --dpi-desync=fake '
            '--dpi-desync-fake-quic="%BIN%quic_initial_www_google_com.bin" --new ^\n'
            '--filter-tcp=80,443 --hostlist="%LISTS%list-general.txt" '
            '--hostlist="%LISTS%list-general-user.txt" '
            '--hostlist-exclude="%LISTS%list-exclude.txt" '
            '--ipset-exclude="%LISTS%ipset-exclude.txt" '
            '--dpi-desync=multisplit --dpi-desync-split-pos=2 '
            '--dpi-desync-split-seqovl-pattern="%BIN%tls_clienthello_www_google_com.bin" --new ^\n'
            '--filter-tcp=%GameFilterTCP% --dpi-desync=fake --new ^\n'
            '--filter-udp=%GameFilterUDP% --dpi-desync=fake\n' + extra)
    (tmp_path/alt_filename(mode)).write_text(body,encoding='utf-8')
    return tmp_path


def test_all_names_and_priority():
    assert ALT_MODES == tuple(f'alt{i}' for i in range(1,14))
    assert set(ALT_PRIORITY) == set(ALT_MODES)
    assert ALT_PRIORITY[0]=='alt2'
    assert alt_filename('alt1') == 'general (ALT).bat'
    assert alt_filename('alt13') == 'general (ALT13).bat'
    with pytest.raises(ValueError):alt_filename('alt14')


def test_parse_winws_not_cmd_with_space_in_path(tmp_path):
    root = tmp_path/'Folder with spaces'
    root.mkdir()
    fixture(root)
    spec=build_dpi_spec(root,'alt2')
    assert spec.argv[0]==str(root/'bin/winws.exe')
    assert spec.cwd==root/'bin'
    assert '--wf-tcp=80,443' in spec.argv
    assert '--wf-udp=443' in spec.argv
    assert '--dpi-desync=multisplit' in spec.argv
    assert '--hostlist='+str(root/'lists/list-general.txt') in spec.argv
    assert '--new' in spec.argv
    assert not any('GameFilter' in arg or 'service.bat' in arg for arg in spec.argv)
    assert not any('list-general-user' in arg for arg in spec.argv)
    assert not any(arg.lower().endswith('.bat') for arg in spec.argv)


def test_existing_user_list_is_preserved(tmp_path):
    fixture(tmp_path)
    (tmp_path/'lists/list-general-user.txt').write_text('example.com')
    args = build_alt_arguments(tmp_path,'alt2')
    assert '--hostlist='+str(tmp_path/'lists/list-general-user.txt') in args


def test_refuse_shell_tail(tmp_path):
    fixture(tmp_path,extra=' & powershell -NoProfile -Command evil')
    with pytest.raises(ValueError,match='неподдерживаемый'):
        build_alt_arguments(tmp_path,'alt2')


def test_missing_required_file_fails_closed(tmp_path):
    fixture(tmp_path)
    (tmp_path/'bin/quic_initial_www_google_com.bin').unlink()
    with pytest.raises(ValueError,match='не найден ресурс'):
        build_alt_arguments(tmp_path,'alt2')


def test_missing_alt_fails_closed(tmp_path):
    fixture(tmp_path)
    with pytest.raises(ValueError,match='отсутствует'):
        build_alt_arguments(tmp_path,'alt12')


def test_preferences_auto_and_manual(tmp_path):
    for mode in ('alt_auto','alt1','alt7','alt13'):
        path=tmp_path/(mode+'.json')
        save_settings(Settings(dpi_mode=mode),path)
        assert load_settings(path).dpi_mode==mode


def test_alt_auto_priority_stops_at_first_reachable():
    from vorqeli_connect.smart_dpi import select_strategy
    active=[]
    def start(mode):active[:]=[mode]
    def stop():active.clear()
    result=select_strategy(start=start,stop=stop,running=lambda:bool(active),
                           cancelled=lambda:False,profiles=ALT_PRIORITY,
                           probe=lambda _: (True,True) if active[0]=='alt6' else (False,False))
    assert [x.mode for x in result.trials]==['alt2','alt6']
    assert result.active_mode=='alt6'
    assert result.all_targets_reachable


def test_alt_auto_all_failures_does_not_claim_verified():
    from vorqeli_connect.smart_dpi import select_strategy
    active=[]
    result=select_strategy(start=lambda mode: active.__setitem__(slice(None),[mode]),
                           stop=lambda:active.clear(),running=lambda:bool(active),
                           cancelled=lambda:False,profiles=ALT_PRIORITY,
                           probe=lambda _: (False,False))
    assert len(result.trials)==13
    assert result.active_mode=='alt2'
    assert 'не подтверждена' in result.warning


def test_modified_alt_batch_invalidates_engine_cache(tmp_path):
    from vorqeli_connect.assets_manager import write_engine_manifest,engine_integrity
    from vorqeli_connect.flowseal_alts import ALT_MODES
    root=tmp_path/'cache'
    (root/'bin').mkdir(parents=True)
    (root/'bin/winws.exe').write_bytes(b'F')
    for mode in ALT_MODES:
        (root/alt_filename(mode)).write_text('legitimate data')
    write_engine_manifest(root,release_sha='0'*64)
    assert engine_integrity(root,release_sha='0'*64)=='verified'
    (root/alt_filename('alt2')).write_text('tampered')
    assert engine_integrity(root,release_sha='0'*64)=='tampered'
