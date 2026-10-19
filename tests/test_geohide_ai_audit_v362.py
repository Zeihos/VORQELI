"""VORQELI v0.36.2: no Windows DNS/hosts/registry writes in these tests."""
from types import SimpleNamespace
from unittest.mock import patch
import pytest
from vorqeli_connect import network_audit as audit


def test_parse_default_route_formats():
    assert audit.parse_default_route_aliases('[]') == []
    assert audit.parse_default_route_aliases('{"InterfaceAlias":"VPN"}') == ['VPN']
    assert audit.parse_default_route_aliases('[{"InterfaceAlias":"Wi-Fi"},{"InterfaceAlias":"Wi-Fi"},{"InterfaceAlias":"VPN"}]') == ['Wi-Fi','VPN']
    with pytest.raises(ValueError):
        audit.parse_default_route_aliases('true')


def test_default_route_verification_fails_closed_for_unlisted_vpn():
    nic = [{'alias':'Wi-Fi','servers':list(audit.GEOHIDE_IPV4)}]
    assert audit.default_route_dns_status(nic,['Wi-Fi']) == 'all'
    assert audit.default_route_dns_status(nic,['Wi-Fi','Tunnel']) == 'unknown'
    assert audit.default_route_dns_status(nic,["Wi-Fi","Wi-Fi"]) == 'all'
    assert audit.default_route_dns_status(nic,["Ethernet"]) == 'unknown'
    assert audit.default_route_dns_status([{'alias':'Wi-Fi','servers':['8.8.8.8']}],['Wi-Fi']) == 'none'
    assert audit.default_route_dns_status(nic + [{'alias':'VPN','servers':['9.9.9.9']}],['Wi-Fi','VPN']) == 'partial'


def test_ai_target_validation_prevents_arbitrary_powershell():
    with pytest.raises(ValueError):
        audit._direct_ai_dns('8.8.8.8','chatgpt.com')
    with pytest.raises(ValueError):
        audit._direct_ai_dns(audit.GEOHIDE_IPV4[0],"chatgpt.com';Remove-Item")


def test_ai_hostnames_are_in_readonly_hosts_audit():
    text='127.0.0.1 auth.openai.com api.claude.ai\n127.0.0.1 badchatgpt.com'
    assert audit.affected_hosts(text) == ['api.claude.ai','auth.openai.com']


def test_deep_geo_audit_is_readonly_and_isolates_failed_domain(monkeypatch):
    calls=[]
    def check(server, domain):
        calls.append((server,domain))
        if domain == 'claude.ai':
            raise RuntimeError('DNS unavailable')
        return 'Ответ получен'
    monkeypatch.setattr(audit, '_direct_ai_dns', check)
    monkeypatch.setattr(audit, '_direct_dns', lambda server: 'Ответ получен')
    monkeypatch.setattr(audit, '_hosts_matches', lambda: [])
    monkeypatch.setattr(audit, '_system_dns', lambda: [{'alias':'Wi-Fi','servers':list(audit.GEOHIDE_IPV4)}])
    monkeypatch.setattr(audit, '_default_route_aliases', lambda: ['Wi-Fi'])
    monkeypatch.setattr(audit, '_doh_profile_verified', lambda: True)
    monkeypatch.setattr(audit, 'os', SimpleNamespace(name='nt'))
    from vorqeli_connect import config
    monkeypatch.setattr(config, 'load_settings', lambda: SimpleNamespace(connect_dns=True,dns_mode='plain'))
    result=audit.run_dns_audit(deep=True)
    assert result['default_route_dns'] == 'all'
    assert len(calls) == 4
    assert all(x == 'Ответ получен' for x in result['ai_dns']['chatgpt.com'].values())
    assert all(x.startswith('Нет ответа') for x in result['ai_dns']['claude.ai'].values())
    assert 'CHATGPT / CLAUDE' in audit.format_dns_audit(result)
    assert 'не подтверждает обход DPI' in audit.format_dns_audit(result)


def test_default_dns_audit_remains_lightweight(monkeypatch):
    monkeypatch.setattr(audit, 'os', SimpleNamespace(name='posix'))
    def must_not_run(*args,**kwargs):
        raise AssertionError('Network/PowerShell accessed')
    monkeypatch.setattr(audit, '_direct_ai_dns', must_not_run)
    result = audit.run_dns_audit()
    assert 'ai_dns' not in result or result['ai_dns'] == {}
