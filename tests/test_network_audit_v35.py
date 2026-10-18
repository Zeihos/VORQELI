from unittest.mock import patch
from types import SimpleNamespace
import pytest
from vorqeli_connect import network_audit as audit


def test_hosts_matches_exact_and_subdomains_not_near_misses():
    text = '''# 1.2.3.4 youtube.com\n1.2.3.4 www.youtube.com youtu.be\n127.0.0.1 notyoutube.com\n1.2.3.5 DISCORD.COM # comment\n::1 web.telegram.org\n'''
    assert audit.affected_hosts(text) == ['discord.com', 'web.telegram.org', 'www.youtube.com']


def test_snapshot_variants():
    assert audit.parse_dns_snapshot('[]') == []
    assert audit.parse_dns_snapshot('{"InterfaceAlias":"Ethernet","ServerAddresses":["1.1.1.1"]}') == [
        {'alias':'Ethernet', 'servers':['1.1.1.1']}]
    with pytest.raises(ValueError):
        audit.parse_dns_snapshot('true')


def test_configured_requires_same_adapter_both_addresses():
    ip1, ip2 = audit.GEOHIDE_IPV4
    assert not audit.geohide_configured([{'servers':[ip1]}, {'servers':[ip2]}])
    assert audit.geohide_configured([{'servers':[ip1, ip2]}])


def test_disallow_arbitrary_server_commands():
    with pytest.raises(ValueError):
        audit._direct_dns("8.8.8.8'; rm -rf")


def test_read_only_report_when_not_windows():
    with patch.object(audit, 'os', SimpleNamespace(name='posix')):
        result = audit.run_dns_audit()
    assert result['dns_configured'] is None
    assert result['direct'] == {}


def test_failure_isolated_by_subsystem():
    with patch.object(audit, 'os', SimpleNamespace(name='nt')), patch.object(audit, '_hosts_matches', return_value=['youtube.com']), \
            patch.object(audit, '_system_dns', side_effect=RuntimeError('not found')), \
            patch.object(audit, '_direct_dns', return_value='Ответ получен'):
        result = audit.run_dns_audit()
    assert result['hosts'] == ['youtube.com']
    assert result['dns_configured'] is None
    assert all(value == 'Ответ получен' for value in result['direct'].values())
    assert 'Системный DNS' in result['errors'][0]


def test_report_never_mislabels_dns_as_bypass():
    text = audit.format_dns_audit({'dns_configured':True,'adapters':[], 'hosts':['youtube.com'],
                                   'direct':{}, 'errors':[]})
    assert 'не подтверждает обход DPI' in text
    assert 'hosts переопределяет' in text
