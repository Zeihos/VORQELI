"""v0.37: screen geometry, five service categories, safe UAC and tray preference."""
from pathlib import Path
from types import SimpleNamespace
import pytest

from vorqeli_connect.redesign_ui import PAGES, SERVICE_NAMES, background, service_summary, Painter
from vorqeli_connect.startup import initial_uac_required
from vorqeli_connect.config import Settings, _validate_settings_fields


def test_redesign_pages_and_exact_five_categories():
    assert PAGES == ('Главная', 'Диагностика', 'История', 'О проекте', 'Настройки', 'Сеть и стратегии')
    assert len(SERVICE_NAMES) == 5
    assert SERVICE_NAMES[-1] == 'Microsoft (Copilot, Designer, Xbox)'
    assert 'Claude' not in SERVICE_NAMES


@pytest.mark.parametrize('page', PAGES)
def test_background_minimum_geometry_and_distinct_pages(page):
    image=background(1060,710,page)
    assert image.size == (1060,710)
    assert image.mode == 'RGB'
    assert image.getpixel((100,100)) != image.getpixel((500,300))


def test_background_cache_and_responsive_wide_screen():
    assert background(1060,710,'Главная') is background(1060,710,'Главная')
    assert background(1390,860,'Настройки').size == (1390,860)


def test_diagnostic_status_does_not_treat_http_403_as_available():
    assert service_summary('Доступен')[0] == 'HTTPS OK'
    assert '403' in service_summary('HTTP 403')[0]
    assert service_summary('HTTP 403')[1] != service_summary('Доступен')[1]
    assert service_summary('Нет ответа')[0] == 'Нет ответа'
    assert service_summary('Copilot: OK | Designer: OK | Xbox: OK')[0] == '3/3 HTTPS OK'
    assert service_summary('Copilot: нет | Designer: OK | Xbox: нет')[0] == 'Частичный ответ'


@pytest.mark.parametrize('values,expect',[
    ((True,False,True,False),True),
    ((True,False,True,True),False),
    ((True,True,True,False),False),
    ((True,False,False,False),False),
    ((False,False,True,False),False),
])
def test_admin_request_policy(values,expect):
    windows,admin,enabled,retry=values
    assert initial_uac_required(windows=windows,admin=admin,enabled=enabled,retry=retry) is expect


def test_default_admin_and_tray_persist_flags():
    s=Settings()
    assert s.admin_on_launch is True
    assert s.minimize_to_tray is True
    assert s.restore_last_mode is True
    assert _validate_settings_fields({'admin_on_launch':False,'minimize_to_tray':False}) == {
        'admin_on_launch':False,'minimize_to_tray':False}
    with pytest.raises(ValueError):
        _validate_settings_fields({'admin_on_launch':'false'})


def test_renderer_keeps_old_service_methods_and_tray_queue():
    root=Path(__file__).resolve().parents[1]
    app=(root/'src/vorqeli_connect/app.py').read_text(encoding='utf-8')
    assert 'from .redesign_ui import draw' in app
    assert "self.events.put(('navigate','Диагностика'))" in app
    assert "self.events.put(('navigate','Настройки'))" in app
    assert 'self.iconphoto(True, self._window_icon)' in app
    assert 'initial_uac_required' in app
    assert 'def _diagnose_service(self, name: str)' in app
    assert 'def _window_close' in app
    assert 'icon.visible = True' in app


def test_tray_logo_offline_is_still_valid():
    from vorqeli_connect.tray_assets import tray_icon
    from PIL import Image
    logo=Image.new('RGBA',(120,120),(65,112,241,255))
    icon=tray_icon(logo,'off')
    assert icon.size == (64,64)
    assert icon.mode == 'RGBA'


def test_tray_custom_setup_really_sets_visible():
    """Regression: old custom callback signalled ready but left tray hidden."""
    import queue
    from vorqeli_connect.app import ConnectApp

    class DummyTray:
        visible=False
        def run(self,setup):
            setup(self)
    events=queue.Queue()
    obj=SimpleNamespace(_tray=DummyTray(),events=events)
    ConnectApp._run_tray(obj)
    assert obj._tray.visible is True
    assert events.get_nowait() == ('tray_ready',None)
    assert events.get_nowait() == ('tray_stopped',None)
