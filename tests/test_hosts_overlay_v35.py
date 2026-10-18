from pathlib import Path
import pytest
from vorqeli_connect.hosts_overlay import (START, END, parse_mappings, analyze_hosts,
                                           apply_optional_hosts, remove_optional_hosts)

REFERENCE='149.154.167.220 telegram.org\n104.25.158.178 example.discord.media\n'


def test_reference_is_valid():
    root=Path(__file__).resolve().parents[1]
    from_file=(root/'assets/VORQELI-hosts-optional.txt').read_text(encoding='utf8')
    assert len(parse_mappings(from_file)) == 241
    assert 'web.telegram.org' in parse_mappings(from_file)


def test_restore_preserves_manual_lines(tmp_path):
    host=tmp_path/'hosts'
    initial=b'# manual\r\n127.0.0.1 localhost\r\n149.154.167.220 telegram.org\r\n'
    host.write_bytes(initial)
    state=apply_optional_hosts(host,REFERENCE)
    assert state['existing']==1 and len(state['needed'])==1
    assert START in host.read_text()
    assert 'example.discord.media' in host.read_text()
    assert remove_optional_hosts(host)
    assert host.read_bytes()==initial
    assert not remove_optional_hosts(host)


def test_manual_conflict_refuses_and_preserves(tmp_path):
    path=tmp_path/'hosts'
    original='1.1.1.1 telegram.org\n'
    path.write_text(original)
    with pytest.raises(ValueError,match='конфликтующие'):
        apply_optional_hosts(path,REFERENCE)
    assert path.read_text()==original


def test_preexisting_all_never_written(tmp_path):
    path=tmp_path/'hosts'
    path.write_text(REFERENCE)
    state=apply_optional_hosts(path,REFERENCE)
    assert not state['needed']
    assert path.read_text()==REFERENCE


def test_malformed_managed_block_refuses(tmp_path):
    path=tmp_path/'hosts'
    path.write_text(START+'\n149.154.167.220 telegram.org\n')
    with pytest.raises(ValueError,match='Повреждён'):
        remove_optional_hosts(path)
    with pytest.raises(ValueError,match='Повреждён'):
        apply_optional_hosts(path,REFERENCE)


def test_untrusted_mapping_rejected():
    for bad in ('127.0.0.1 localhost extra','111.111.111.999 example.com',
                '1.1.1.1 a.com\n2.2.2.2 a.com','1.1.1.1 localhost'):
        with pytest.raises(ValueError):parse_mappings(bad)


def test_overlays_never_modify_when_read_only(tmp_path):
    path=tmp_path/'hosts'
    path.write_text('# hi\n')
    before=path.read_bytes()
    report=analyze_hosts(path.read_text(),REFERENCE)
    assert report['count']==2
    assert path.read_bytes()==before
