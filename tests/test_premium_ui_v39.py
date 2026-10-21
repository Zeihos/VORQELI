"""Production v0.39 UI, fixed frameless dimensions and no fabricated network data."""
from __future__ import annotations
from types import SimpleNamespace as N
from pathlib import Path
import pytest
from PIL import Image, ImageChops
from vorqeli_connect import premium_ui as ui, frameless, premium_logs


def make_app(*,connected=False,results=None):
    s=N(desired_enabled=connected,connect_dpi=True,connect_telegram=True,connect_dns=True,
        dpi_mode='alt_auto',dns_mode='plain',launch_at_startup=False,
        restore_last_mode=True,minimize_to_tray=True,admin_on_launch=True)
    state='on' if connected else 'off'
    c=N(status=lambda:N(overall='connected' if connected else 'off',dpi=state,telegram=state,dns=state),
        active_dpi_mode='alt2' if connected else None)
    return N(settings=s,controller=c,selected_page='Главная',last_results=results or [],
             _visual_history_filter='Все события')


def test_exact_six_pages_five_categories():
    assert len(ui.PAGES)==6
    assert ui.SERVICE_NAMES==('Discord','YouTube','Telegram Web','ChatGPT',
                              'Microsoft (Copilot, Designer, Xbox)')


@pytest.mark.parametrize('page',ui.PAGES)
def test_all_six_approved_screens_are_bundled_and_render(page):
    original=ui.artwork(page)
    assert original.size==(1536,1024) and original.mode=='RGB'
    app=make_app();app.selected_page=page
    rendered=ui.build_frame(app)
    assert rendered.mode=='RGB' and rendered.size==(1536,1024)
    assert ImageChops.difference(original,rendered).getbbox() is not None


def test_off_state_does_not_reuse_demo_running_state():
    off=ui.build_frame(make_app())
    on=ui.build_frame(make_app(connected=True))
    assert ImageChops.difference(off,on).getbbox() is not None
    # The live status panel and hero are repainted rather than blindly copied.
    assert off.getpixel((1190,50))!=ui.artwork('Главная').getpixel((1190,50))


def test_diagnostics_are_not_faked_by_screenshot():
    a=make_app(results=[('ChatGPT','HTTP 403'),('Telegram Web','Нет ответа')]);a.selected_page='Диагностика'
    b=make_app(results=[('ChatGPT','Доступен'),('Telegram Web','Доступен')]);b.selected_page='Диагностика'
    x=ui.build_frame(a);y=ui.build_frame(b)
    assert ImageChops.difference(x,y).getbbox() is not None
    assert ui.service_summary('HTTP 403')[1]!=ui.COLORS['green']
    assert ui.service_summary('Copilot: OK | Designer: OK | Xbox: OK')[0]=='3/3 HTTPS OK'
    assert ui.service_summary('Нет ответа')[0]=='Нет ответа'
    assert ui.service_summary('Не проверено')[0]=='Не проверено'


def test_history_is_replaced_not_sample(monkeypatch):
    a=make_app();a.selected_page='История'
    monkeypatch.setattr(ui,'recent_events',lambda limit=120:[])
    empty=ui.build_frame(a)
    monkeypatch.setattr(ui,'recent_events',lambda limit=120:[
        {'timestamp':'2026-10-20T09:12:33','kind':'connection','message':'Фактическое событие ABC777'}])
    filled=ui.build_frame(a)
    assert ImageChops.difference(empty,filled).getbbox() is not None


def test_settings_and_strategy_switches_live():
    a=make_app();a.selected_page='Настройки'
    left=ui.build_frame(a);a.settings.launch_at_startup=True
    right=ui.build_frame(a)
    assert ImageChops.difference(left,right).getbbox() is not None
    a.selected_page='Сеть и стратегии';a.settings.dpi_mode='alt11'
    selected=ui.build_frame(a);a.settings.dpi_mode='alt4'
    assert ImageChops.difference(selected,ui.build_frame(a)).getbbox() is not None


@pytest.mark.parametrize('width,height',[(1920,1080),(1366,768),(1024,600),(800,600)])
def test_locked_window_fits_screen(width,height):
    geom=frameless.fixed_geometry(width,height)
    import re
    m=re.fullmatch(r'(\d+)x(\d+)\+(\d+)\+(\d+)',geom)
    assert m
    w,h,x,y=map(int,m.groups())
    assert 0<w<=width and 0<h<=height
    assert x>=0 and y>=0 and x+w<=width and y+h<=height
    assert abs(w/h-1.5)<0.02


def test_project_assets_present_and_icon_has_alpha():
    from vorqeli_connect.app import asset
    image=Image.open(asset('VORQELI-logo.png'))
    assert image.mode=='RGBA' and image.size==(512,512)
    root=Path(__file__).resolve().parents[1]
    assert (root/'assets/VORQELI.ico').read_bytes().startswith(b'\0\0\1\0')
    for s in ('discord','youtube','telegram','chatgpt','microsoft'):
        assert (ui.ASSET_DIR/'brand'/f'{s}.png').is_file()


def test_renderer_does_not_mutate_network_or_registry():
    src=Path(ui.__file__).read_text(encoding='utf8')
    for bad in ('winreg','Set-DnsClientServerAddress','subprocess.run','ShellExecuteW'):
        assert bad not in src


def test_log_viewer_keeps_bounded_redaction(monkeypatch,tmp_path):
    monkeypatch.setattr(premium_logs,'APP_DIR',tmp_path)
    secret='a'*32
    (tmp_path/'telegram-engine.log').write_text('test --secret='+secret,encoding='utf8')
    result=premium_logs.read_log('Telegram',secret)
    assert secret not in result and '[СКРЫТО]' in result
    assert premium_logs.read_log('DPI',secret)
    with pytest.raises(ValueError):premium_logs.read_log('Other',secret)


def test_existing_ui_regressions_stay_available():
    from vorqeli_connect import redesign_ui
    assert 'Главная' in redesign_ui.PAGES
    assert len(redesign_ui.SERVICE_NAMES)==5
