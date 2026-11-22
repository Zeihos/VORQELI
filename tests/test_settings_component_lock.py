"""Component toggles must not falsify runtime health while connected."""
from types import SimpleNamespace as NS

import pytest
from vorqeli_connect.app import ConnectApp
from vorqeli_connect.config import Settings


@pytest.mark.parametrize('key', ('connect_dpi', 'connect_telegram', 'connect_dns'))
@pytest.mark.parametrize('busy,connected', [(False, True), (True, False)])
def test_live_components_cannot_change(monkeypatch, key, busy, connected):
    from vorqeli_connect import app as app_module
    monkeypatch.setattr(app_module, 'save_settings',
                        lambda settings: (_ for _ in ()).throw(
                            AssertionError('Live selection must not be saved')))
    settings = Settings(desired_enabled=connected)
    draws = []
    app = NS(settings=settings, running_job=busy,
             detail='', _draw=lambda:draws.append(True))
    original = getattr(settings, key)
    ConnectApp._toggle_setting(app, key)
    assert getattr(settings, key) is original
    assert 'отключите VORQELI' in app.detail
    assert draws == [True]


def test_offline_component_change_saves(monkeypatch):
    from vorqeli_connect import app as app_module
    saved = []
    monkeypatch.setattr(app_module, 'save_settings', lambda settings:saved.append(True))
    settings = Settings(desired_enabled=False, connect_dpi=True)
    app = NS(settings=settings, running_job=False, detail='', _draw=lambda:None)
    ConnectApp._toggle_setting(app, 'connect_dpi')
    assert not settings.connect_dpi
    assert saved == [True]


def test_native_ui_omits_live_toggle_actions(monkeypatch):
    from vorqeli_connect import native_ui as ui
    from test_native_ui_v401 import FakeApp
    monkeypatch.setattr(ui.Scene, 'logo', lambda *args: True)
    app = FakeApp()
    app.selected_page = 'Настройки'
    app.settings.desired_enabled = True
    ui.draw(app)
    labels = [label for _, _, label in app._controls]
    assert not any(label.startswith('Переключить DPI / WinWS') for label in labels)
    assert not any(label.startswith('Переключить Telegram MTProto') for label in labels)
    assert not any(label.startswith('Переключить GeoHide + Flowseal HOSTS') for label in labels)
    assert any(label.startswith('Переключить Автозапуск') for label in labels)
