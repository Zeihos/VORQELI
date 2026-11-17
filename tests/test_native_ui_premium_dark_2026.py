"""2026 premium dark visual system: behavior-preserving offline regression gates."""
from types import SimpleNamespace as NS
import pytest
from vorqeli_connect import native_ui as ui
from test_native_ui_v401 import FakeApp


@pytest.fixture(autouse=True)
def stable_assets(monkeypatch):
    monkeypatch.setattr(ui.Scene, 'logo', lambda *args: True)
    monkeypatch.setattr(ui.Scene, 'brand_icon', lambda *args: True)
    monkeypatch.setattr(ui, 'recent_events', lambda limit=100: [])
    monkeypatch.setattr(ui, 'load_history', lambda: [])


def test_premium_palette_is_neutral_and_legible():
    assert ui.C['bg'] == '#0B0A10'
    assert ui.C['sidebar'] != ui.C['surface']
    assert ui.C['strong'].startswith('#')
    assert ui.C['red'] != ui.C['green']


@pytest.mark.parametrize('page', ui.PAGES)
def test_every_page_keeps_real_controls(page):
    app = FakeApp()
    app.selected_page = page
    ui.draw(app)
    assert len(app._controls) >= 7
    assert app.canvas.num > 40
    assert app.actions == []


def test_real_connect_callback_preserved():
    app = FakeApp()
    ui.draw(app)
    controls = [cb for _, cb, label in app._controls if label == 'ПОДКЛЮЧИТЬ']
    assert len(controls) == 1
    controls[0]()
    assert app.actions == ['connect']


def test_error_status_is_not_success(monkeypatch):
    shown = []
    old = ui.Scene.txt
    def watch(self, x, y, value, *args, **kwargs):
        shown.append(str(value))
        return old(self, x, y, value, *args, **kwargs)
    monkeypatch.setattr(ui.Scene, 'txt', watch)
    app = FakeApp()
    app.controller.status = lambda: NS(overall='error', dpi='error',
                                        telegram='off', dns='off')
    ui.draw(app)
    assert 'Ошибка подключения' in shown
    assert not any('Соединение защищено' in x for x in shown)
    assert not any('Ваш IP' in x for x in shown)


def test_pointer_repeated_activation_remains_keyboard_focus_independent():
    app = FakeApp()
    ui.draw(app)
    scene = ui.Scene(app)
    called = []
    app._controls = [((0, 0, 100, 40), lambda: called.append(1), 'Проверить')]
    app._focused_control_index = 0
    scene.activate_mouse(0)
    scene.activate_mouse(0)
    assert called == [1, 1]
    assert app._focused_control_index is None
