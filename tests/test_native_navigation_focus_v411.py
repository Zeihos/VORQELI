"""Native six-page navigation and redraw-safe keyboard action focus.

No OS, networking, registry, DNS or HOSTS side effects.
"""
from types import SimpleNamespace as NS
import pytest
from vorqeli_connect import native_ui as ui
from vorqeli_connect.ui_navigation import reconcile_action_focus
from vorqeli_connect.app import ConnectApp
from test_native_ui_v401 import FakeApp


@pytest.fixture(autouse=True)
def no_real_images(monkeypatch):
    monkeypatch.setattr(ui.Scene,'logo',lambda *args: True)
    monkeypatch.setattr(ui.Scene,'brand_icon',lambda *args: True)
    monkeypatch.setattr(ui,'recent_events',lambda limit=100: [])
    monkeypatch.setattr(ui,'load_history',lambda: [])


@pytest.mark.parametrize('page',ui.PAGES)
def test_every_page_has_a_distinct_sidebar_item(page):
    app=FakeApp()
    app.selected_page=page
    ui.draw(app)
    labels=[label for _,_,label in app._controls]
    assert labels.count('Раздел: '+page)==1
    assert len([label for label in labels if label.startswith('Раздел: ')])==6


def test_network_page_reachable_directly_from_sidebar():
    app=FakeApp()
    ui.draw(app)
    app.canvas.tags[('nav_5','<Button-1>')](NS())
    assert app.selected_page=='Сеть и стратегии'


def test_reconcile_focus_clears_missing_and_ambiguous_targets():
    assert reconcile_action_focus('ПРОВЕРИТЬ',[]) is None
    controls=[((0,0,1,1),lambda:None,'ПРОВЕРИТЬ'),
              ((0,0,1,1),lambda:None,'ПРОВЕРИТЬ')]
    assert reconcile_action_focus('ПРОВЕРИТЬ',controls) is None
    assert reconcile_action_focus('Другой',controls) is None
    assert reconcile_action_focus('Раздел: Главная',
        [((0,0,1,1),lambda:None,'Другое'),
         ((0,0,1,1),lambda:None,'Раздел: Главная')])==1


def test_keyboard_focus_cleared_after_disabled_button_redraw():
    app=NS(_focused_control_index=0)
    app._controls=[]
    def action():
        app._controls=[((0,0,1,1),lambda:None,'Случайная другая кнопка')]
    app._controls=[((0,0,1,1),action,'ПРОВЕРИТЬ')]
    rendered=[]
    app._render_focus=lambda:rendered.append(app._focused_control_index)
    result=ConnectApp._keyboard_activate(app,NS())
    assert result=='break'
    assert app._focused_control_index is None
    assert rendered==[None]


def test_keyboard_focus_survives_same_unique_action():
    app=NS(_focused_control_index=0)
    app._controls=[]
    def action():
        app._controls=[((0,0,1,1),lambda:None,'Раздел: Главная')]
    app._controls=[((0,0,1,1),action,'Раздел: Главная')]
    app._render_focus=lambda:None
    ConnectApp._keyboard_activate(app,NS())
    assert app._focused_control_index==0


def test_navigation_icon_click_target_shares_tag():
    app=FakeApp()
    ui.draw(app)
    for index in range(6):
        assert ('nav_'+str(index),'<Button-1>') in app.canvas.tags
