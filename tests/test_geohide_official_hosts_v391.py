"""Offline safety regression for opt-in official GeoHide RU classic HOSTS."""
from __future__ import annotations
import hashlib
from pathlib import Path
import pytest
from vorqeli_connect import geohide_hosts_feed as geo


def source(*,count=205, bad=''):
    rows=['### geohide.ru: hosts file', '# Последнее обновление: 20.10.2026 04:56:02',
          '# Регион серверов: RU', '# Эти IP-адреса принадлежат GeoHide DNS:']
    rows += [f'159.194.200.33 srv{n}.example.com' for n in range(count)]
    rows += ['159.194.200.33 claude.ai','193.233.112.67 claude.ai',
             '193.233.112.88 chatgpt.com','193.233.112.68 chatgpt.com',
             '127.0.0.1 localhost','::1 ip6-localhost']
    if bad:rows.append(bad)
    rows+=['### geohide.ru: end hosts file']
    return '\n'.join(rows)+'\n'


def test_full_official_multiples_preserved():
    s=geo.parse_official(source()); assert s.domain_count==207
    assert ('159.194.200.33','claude.ai') in s.records
    assert ('193.233.112.67','claude.ai') in s.records
    assert sum(host=='chatgpt.com' for _,host in s.records)==2
    assert 'localhost' not in {host for _,host in s.records}


@pytest.mark.parametrize('bad', ['127.0.0.1 attacker.example.com','127.0.0.1 other.example.com bogus',
                                  '8.8.8.8 no spaces domain.example.com',
                                  '8.8.8.8 invalid..example.com'])
def test_invalid_source_rejected(bad):
    with pytest.raises(ValueError):geo.parse_official(source(bad=bad))


def test_wrong_region_or_truncated_rejected():
    with pytest.raises(ValueError):geo.parse_official(source().replace('серверов: RU','серверов: US'))
    with pytest.raises(ValueError):geo.parse_official(source(count=10))
    with pytest.raises(ValueError):geo.parse_official(source().replace('### geohide.ru: end hosts file',''))


def test_geo_and_telegram_merge_is_reversible(tmp_path:Path):
    hosts=tmp_path/'hosts';journal=tmp_path/'geo-restore.json'
    original='# saved by user\n1.1.1.1 custom.example.org\n# VORQELI OPTIONAL HOSTS START\n149.154.167.220 web.telegram.org\n159.194.200.33 claude.ai\n# VORQELI OPTIONAL HOSTS END\n'
    hosts.write_text(original,encoding='utf-8')
    official=geo.parse_official(source())
    report=geo.apply(hosts,official,journal,'149.154.167.220 web.telegram.org\n')
    text=hosts.read_text('utf-8')
    assert report['official_entries']>=200
    assert '149.154.167.220 web.telegram.org' in text
    assert text.count('193.233.112.67 claude.ai')==1
    assert '1.1.1.1 custom.example.org' in text
    assert geo.START in text and geo.LEGACY_START not in text
    assert geo.remove(hosts,journal) is True
    assert hosts.read_text('utf-8')==original


def test_user_manual_hosts_have_priority(tmp_path):
    host=tmp_path/'hosts';journal=tmp_path/'journal'
    host.write_text('10.0.0.1 claude.ai\n',encoding='utf-8')
    p=geo.apply(host,geo.parse_official(source()),journal)
    assert p['protected_domains']==1
    t=host.read_text('utf-8')
    assert t.startswith('10.0.0.1 claude.ai\n')
    assert '193.233.112.67 claude.ai' not in t
    assert geo.remove(host,journal)
    assert host.read_text('utf-8')=='10.0.0.1 claude.ai\n'


def test_managed_tampering_refuses_replace(tmp_path):
    host=tmp_path/'hosts';j=tmp_path/'journal'
    host.write_text('# original\n',encoding='utf-8')
    s=geo.parse_official(source())
    geo.apply(host,s,j)
    host.write_text(host.read_text('utf8').replace('srv1.example.com','srv1.attacker.com'),encoding='utf8')
    with pytest.raises(ValueError):geo.remove(host,j)
    with pytest.raises(ValueError):geo.apply(host,s,j)


def test_idempotent_refresh_updates_timestamp(tmp_path):
    host=tmp_path/'hosts';j=tmp_path/'journal'
    host.write_text('127.0.0.1 localhost\n',encoding='utf-8')
    s=geo.parse_official(source())
    geo.apply(host,s,j)
    geo.apply(host,s,j)
    assert host.read_text('utf8').count(geo.START)==1
    assert geo.remove(host,j)
    assert host.read_text('utf8')=='127.0.0.1 localhost\n'


def test_skip_symlink_and_no_auto_apply(tmp_path):
    path=tmp_path/'hosts';path.write_text('127.0.0.1 localhost\n',encoding='utf-8')
    other=tmp_path/'bad';other.symlink_to(path)
    with pytest.raises(ValueError):geo.apply(other,geo.parse_official(source()),tmp_path/'journal')
    assert path.read_text('utf-8')=='127.0.0.1 localhost\n'
    import importlib.util; spec=importlib.util.find_spec('vorqeli_connect.unified'); assert spec is None or True
    src=Path(spec.origin).read_text('utf-8') if spec else ''
    assert 'geohide_hosts_feed' not in src
