import json
from vorqeli_connect.config import Settings
from vorqeli_connect.unified import ConnectionReport
from vorqeli_connect.support_report import build_report


def test_support_report_does_not_leak_credentials_or_paths():
    s=Settings(telegram_secret='deadbeef'*4,telegram_source_dir='C:/Users/private',
               dpi_bundle_dir='C:/Somewhere',desired_enabled=True)
    r=ConnectionReport('partial','on','error','on',detail='SECRET deadbeef private')
    results=[('Discord','Доступен'),('Telegram','password=hidden'),('x-secret','12345')]
    out=build_report(s,r,results,'0.16.0')
    blob=json.dumps(out,ensure_ascii=False)
    for unexpected in ('deadbeef','private','Somewhere','password','x-secret'):
        assert unexpected not in blob
    assert out['overall']=='partial'
    assert out['checks']['Telegram']=='Другой результат'


def test_report_has_only_known_statuses():
    r=ConnectionReport('unexpected','running','wat','off')
    out=build_report(Settings(),r,[], '0.16.0')
    assert out['components']['dpi']['state']=='unknown'
    assert out['overall']=='unknown'
