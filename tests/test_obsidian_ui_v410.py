"""VORQELI 0.41.0: restrained dark UI and repeat-click regression checks.

No networking, registry, DNS or system HOSTS changes.
"""
from types import SimpleNamespace as NS
from pathlib import Path
from vorqeli_connect import native_ui as ui
from test_native_ui_v401 import FakeApp


def test_2026_palette_uses_violet_on_neutral_dark_surfaces():
    assert ui.C['bg'] == '#0C0A12'
    assert ui.C['sidebar'] != ui.C['surface']
    assert ui.C['blue'] != '#116BEC'
    assert all(len(ui.C[k]) == 7 and ui.C[k][0] == '#'
               for k in ('bg','sidebar','surface','surface2','text','muted','edgehi'))


def test_render_has_no_pretend_online_status_or_painted_screens(monkeypatch):
    monkeypatch.setattr(ui.Scene, 'logo', lambda *args: True)
    monkeypatch.setattr(ui.Scene, 'brand_icon', lambda *args: True)
    monkeypatch.setattr(ui, 'recent_events', lambda limit=100: [])
    monkeypatch.setattr(ui, 'load_history', lambda: [])
    app = FakeApp()
    before = vars(app.settings).copy()
    for page in ui.PAGES:
        app.selected_page = page
        ui.draw(app)
        assert app._controls
    assert vars(app.settings) == before
    assert not app.actions
    source = Path(ui.__file__).read_text(encoding='utf-8')
    assert 'premium/home.png' not in source
    assert 'premium/settings.png' not in source


def test_mouse_double_activation_clears_pointer_focus_and_preserves_keyboard_route():
    app = FakeApp()
    scene = ui.Scene(app)
    presses = []
    scene.button((380,310,630,370), 'ПОДКЛЮЧИТЬ', lambda: presses.append(1))
    index = next(i for i, (_, _, label) in enumerate(app._controls) if label == 'ПОДКЛЮЧИТЬ')
    app._focused_control_index = index
    scene.activate_mouse(index)
    assert app._focused_control_index is None
    scene.activate_mouse(index)
    assert presses == [1, 1]
    # Keyboard handling still uses ConnectApp._focus_control/_keyboard_activate.
    assert callable(app._controls[index][1])


def test_pointer_callbacks_do_not_call_legacy_focus_method():
    app = FakeApp()
    app._focus_control = lambda _: (_ for _ in ()).throw(AssertionError('pointer must not focus'))
    scene = ui.Scene(app)
    scene.button((380,310,630,370), 'ПОДКЛЮЧИТЬ', lambda: app.actions.append('click'))
    scene.activate_mouse(len(app._controls)-1)
    assert app.actions == ['click']


def test_disabled_dns_transport_still_not_clickable(monkeypatch):
    monkeypatch.setattr(ui.Scene, 'logo', lambda *args: True)
    app = FakeApp(); app.selected_page = 'Сеть и стратегии'
    app.settings.desired_enabled = True
    ui.draw(app)
    labels = [label for _, _, label in app._controls]
    assert 'IPv4 DNS' not in labels and 'DoH / HTTPS' not in labels
    assert all('ALT'+str(i) in labels for i in range(1,14))


def test_unavailable_services_never_show_success():
    for status in ('HTTP 403', 'HTTP 429', 'Нет ответа'):
        assert ui.classify_service(status)[1] != ui.C['green']


def test_window_uses_native_ui_primitives_and_live_status():
    app = FakeApp()
    scene = ui.Scene(app)
    assert scene.report.overall == 'off'
    assert scene.sx == scene.sy == scene.sf
    assert ui.MIN_READABLE_SCALE >= 0.8
