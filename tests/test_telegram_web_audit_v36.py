"""Offline Telegram Web diagnostics tests; no real network/system changes."""
from __future__ import annotations
import json
from pathlib import Path
from types import SimpleNamespace
import socket
import ssl
import pytest
from vorqeli_connect import telegram_web_audit as a
from vorqeli_connect.config import Settings
from vorqeli_connect.support_report import build_report
from vorqeli_connect.unified import ConnectionReport


def test_parse_hosts_exact_domains_and_duplicates():
    data = ("149.154.167.220 web.telegram.org KWS2.WEB.TELEGRAM.ORG.\n"
            "149.154.167.220 web.telegram.org # duplicate\n"
            "127.0.0.1 evilweb.telegram.org web.telegram.org.bad.tld\n"
            "::1 zws4.web.telegram.org\n")
    result = a.parse_telegram_hosts(data)
    assert result == {'kws2.web.telegram.org': ('149.154.167.220',),
                      'web.telegram.org': ('149.154.167.220',),
                      'zws4.web.telegram.org': ('::1',)}


def test_hosts_ignore_invalid_and_comments():
    result = a.parse_telegram_hosts(
        '# 1.1.1.1 web.telegram.org\nnot-an-ip web.telegram.org\n'
        '1.1.1.1 unrelated.org\n')
    assert result == {}


def test_refuse_unapproved_probe():
    with pytest.raises(ValueError):
        a.probe_https('example.org','/')
    with pytest.raises(ValueError):
        a.probe_https('web.telegram.org','/../../../secret')


def test_https_returns_http_status_without_claiming_web_app_works(monkeypatch):
    calls = []
    class FakeHTTPS:
        def __init__(self, host, port, timeout, context):
            assert host == 'web.telegram.org' and port == 443 and timeout == 4
            calls.append('open')
        def request(self, method, path, headers):
            calls.append((method, path, headers['Connection']))
        def getresponse(self):
            return SimpleNamespace(status=200, read=lambda count: b'<html>')
        def close(self): calls.append('close')
    monkeypatch.setattr(a,'HTTPSConnection',FakeHTTPS)
    assert a.probe_https('web.telegram.org','/k/') == ('ok','HTTPS отвечает (HTTP 200)')
    assert calls == ['open', ('GET','/k/','close'), 'close']


def test_http_error_is_not_network_error(monkeypatch):
    class Http403:
        def __init__(self,*args,**kwargs): pass
        def request(self,*args,**kwargs): pass
        def getresponse(self): return SimpleNamespace(status=403, read=lambda _:b'')
        def close(self): pass
    monkeypatch.setattr(a,'HTTPSConnection',Http403)
    assert a.probe_https('web.telegram.org','/a/') == ('http','Сервер ответил HTTP 403')


@pytest.mark.parametrize('err,state', [
    (socket.gaierror('missing'), 'dns'),
    (ssl.SSLCertVerificationError('certificate'), 'tls'),
    (ssl.SSLError('ssl'), 'tls'),
    (TimeoutError('timeout'), 'timeout'),
    (OSError('offline'), 'network'),
])
def test_https_error_classifications(monkeypatch,err,state):
    class BadHTTPS:
        def __init__(self,*args,**kwargs): pass
        def request(self,*args,**kwargs): raise err
        def close(self): pass
    monkeypatch.setattr(a,'HTTPSConnection',BadHTTPS)
    result=a.probe_https('web.telegram.org','/k/')
    assert result[0]==state
    assert 'offline' not in result[1]


def test_windows_dns_no_hosts_filters_answers(monkeypatch):
    monkeypatch.setattr(a,'os',SimpleNamespace(name='nt'))
    class FakeSubprocess:
        CREATE_NO_WINDOW=0
        @staticmethod
        def run(argv,**kwargs):
            assert '-NoHostsFile' in argv[-1]
            assert kwargs['timeout'] == 8
            return SimpleNamespace(returncode=0,stdout='["149.154.167.220", "not-ip", "149.154.167.220"]')
    monkeypatch.setattr(a,'subprocess',FakeSubprocess)
    assert a.dns_without_hosts()==('149.154.167.220',)
    with pytest.raises(ValueError): a.dns_without_hosts('example.org')


def test_audit_runs_bounded_direct_checks_and_keeps_dns_independent(tmp_path):
    path=tmp_path/'hosts'
    path.write_text('149.154.167.220 web.telegram.org\n',encoding='utf8')
    visited=[]
    def request(host, url_path):
        visited.append((host,url_path))
        return ('ok','HTTPS отвечает (HTTP 200)')
    report=a.audit_telegram_web(hosts_file=path, request=request,
                                resolver=lambda:('1.2.3.4',), windows=True)
    assert len(report['checks'])==len(a.WEB_TARGETS)==4
    assert len(visited)==4
    assert report['dns_without_hosts']==('1.2.3.4',)
    assert 'разные IP' in a.format_telegram_web_audit(report)
    assert 'MTProto' in a.format_telegram_web_audit(report)


def test_audit_isolates_dns_and_request_failures(tmp_path):
    path=tmp_path/'hosts'
    path.write_text('bad-ip web.telegram.org',encoding='utf8')
    def broken(*args): raise OSError('test secret')
    report=a.audit_telegram_web(hosts_file=path,request=broken,
                                resolver=broken,windows=True)
    assert all(c['state']=='network' for c in report['checks'])
    assert report['dns_error']=='OSError'
    assert 'test secret' not in json.dumps(report)


def test_non_windows_audit_does_not_query_resolver(tmp_path):
    path=tmp_path/'hosts';path.write_text('',encoding='utf8')
    report=a.audit_telegram_web(hosts_file=path,windows=False,
        resolver=lambda: (_ for _ in ()).throw(AssertionError('unexpected DNS query')),
        request=lambda *_: ('timeout','Превышено время ожидания'))
    assert report['dns_without_hosts'] is None
    assert report['dns_error'] is None
    assert 'Не проверено' in a.format_telegram_web_audit(report)


def test_hosts_symlink_is_rejected(tmp_path):
    original=tmp_path/'real';original.write_text('149.154.167.220 web.telegram.org')
    link=tmp_path/'link'
    try: link.symlink_to(original)
    except (OSError,NotImplementedError): pytest.skip('No symlink privileges')
    report=a.audit_telegram_web(hosts_file=link,windows=False,
                                request=lambda *_:('ok','ok'))
    assert report['hosts']=={}
    assert report['errors']


def test_report_accepts_real_alt_modes_without_secrets():
    for dpi_mode in ('alt_auto','alt2','alt13'):
        report=build_report(Settings(dpi_mode=dpi_mode,telegram_secret='a'*32),
                ConnectionReport('connected','on','on','on'),
                [('Telegram Web','Нет ответа')], '0.36.0')
        assert report['dpi_mode']==dpi_mode
        assert report['checks']['Telegram Web']=='Нет ответа'
        assert 'aaaaaaaa' not in json.dumps(report)


def test_ui_contains_telegram_web_diagnostic_without_touching_dpi():
    code=(Path(__file__).resolve().parents[1]/'src/vorqeli_connect/app.py').read_text(encoding='utf8')
    assert 'TELEGRAM WEB' in code
    assert 'def _show_telegram_web_audit(self)' in code
    assert "('telegram_web_audit',text)" in code
    assert 'from .telegram_web_audit import audit_telegram_web' in code
