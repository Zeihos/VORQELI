"""RC 0.40.4: real control activation, stale HTTPS states and error feedback.

Pure Canvas simulations; never touch user networking, registry, HOSTS, or DNS.
"""
from types import SimpleNamespace as NS
import pytest
from vorqeli_connect import native_ui as ui
from test_native_ui_v401 import FakeApp


@pytest.fixture(autouse=True)
def _icons(monkeypatch):
    monkeypatch.setattr(ui.Scene,'logo',lambda *args: True)
    monkeypatch.setattr(ui.Scene,'brand_icon',lambda *args: True)


def _texts(monkeypatch):
    gathered=[]
    old=ui.Scene.txt
    def record(self,x,y,s,*a,**k):
        gathered.append(str(s))
        return old(self,x,y,s,*a,**k)
    monkeypatch.setattr(ui.Scene,'txt',record)
    return gathered


@pytest.mark.parametrize('width,height',[(1260,840),(1000,650),(800,540),(640,480)])
def test_controls_have_matching_logical_canvas_extent(width,height):
    app=FakeApp()
    app.canvas.winfo_width=lambda:width
    app.canvas.winfo_height=lambda:height
    ui.draw(app)
    extent=(round(ui.W*max(ui.MIN_READABLE_SCALE,min(width/ui.W,height/ui.H))),
            round(ui.H*max(ui.MIN_READABLE_SCALE,min(width/ui.W,height/ui.H))))
    assert app._logical_size==extent
    assert app._controls
    assert all(0<=bounds[0]<bounds[2]<=extent[0]+1 and
               0<=bounds[1]<bounds[3]<=extent[1]+1
               for bounds,_,_ in app._controls)


def test_first_click_works_with_focus_implementation_that_requires_logical_size():
    app=FakeApp()
    def focus_sensitive_click(index):
        w,h=app._logical_size  # Equivalent precondition to ConnectApp._focus_control
        bounds,callback,label=app._controls[index]
        assert bounds[2]<=w and bounds[3]<=h
        callback()
    app._mouse_activate=focus_sensitive_click
    ui.draw(app)
    index=next(i for i,(_,_,label) in enumerate(app._controls) if label=='ПОДКЛЮЧИТЬ')
    app._mouse_activate(index)
    assert app.actions==['connect']


def test_side_panel_exposes_actual_error(monkeypatch):
    captured=_texts(monkeypatch)
    app=FakeApp()
    app.controller.status=lambda:NS(overall='error',dpi='error',telegram='error',dns='error')
    ui.draw(app)
    assert 'Ошибка соединения' in captured
    assert 'Ожидание' not in captured


def test_single_service_rescan_hides_only_its_stale_result(monkeypatch):
    captured=_texts(monkeypatch)
    app=FakeApp();app.selected_page='Диагностика';app.running_job=True
    app.detail='Проверяем сервис: YouTube'
    app.last_results=[(k,'Доступен') for k in ui.SERVICE_NAMES]
    ui.draw(app)
    assert captured.count('Проверяется…')==1
    assert captured.count('HTTPS OK')==4
    assert 'ЗАНЯТО' in captured
    assert app.actions==[]
    assert not any(label=='ПРОВЕРИТЬ' for _,_,label in app._controls)


def test_full_rescan_hides_all_stale_green(monkeypatch):
    captured=_texts(monkeypatch)
    app=FakeApp();app.selected_page='Диагностика';app.running_job=True
    app.detail='Диагностика выполняется…'
    app.last_results=[(k,'Доступен') for k in ui.SERVICE_NAMES]
    ui.draw(app)
    assert captured.count('Проверяется…')==5
    assert 'HTTPS OK' not in captured
    assert not any(label=='ПРОВЕРИТЬ' for _,_,label in app._controls)


def test_unrelated_busy_operation_does_not_fake_a_rescan(monkeypatch):
    captured=_texts(monkeypatch)
    app=FakeApp();app.selected_page='Диагностика';app.running_job=True
    app.detail='Обновление программы…'
    app.last_results=[(k,'Доступен') for k in ui.SERVICE_NAMES]
    ui.draw(app)
    assert 'Проверяется…' not in captured
    assert captured.count('HTTPS OK')==5
    assert 'ЗАНЯТО' in captured


def test_idle_results_return_to_real_values(monkeypatch):
    captured=_texts(monkeypatch)
    app=FakeApp();app.selected_page='Диагностика';app.running_job=False
    app.last_results=[('ChatGPT','HTTP 403')]
    ui.draw(app)
    assert 'HTTP 403 · ограничение' in captured
    assert 'Проверяется…' not in captured
    assert [x for _,_,x in app._controls].count('ПРОВЕРИТЬ')==5


def test_network_view_does_not_hide_dns_error(monkeypatch):
    captured=_texts(monkeypatch)
    app=FakeApp();app.selected_page='Сеть и стратегии'
    app.controller.status=lambda:NS(overall='error',dpi='off',telegram='off',dns='error')
    ui.draw(app)
    assert 'Модуль: ошибка' in captured


def test_missing_icon_tcl_failure_is_graceful(monkeypatch):
    from tkinter import TclError
    monkeypatch.undo()
    app=FakeApp();scene=ui.Scene(app)
    # Tk image creation may fail because of a destroyed toplevel or bad UI
    # resources.  Show the fallback logo/icon instead of crashing the GUI.
    monkeypatch.setattr(ui,'_scaled_icon',lambda *args: (_ for _ in ()).throw(TclError('image failed')))
    assert scene.logo(20,20,40) is False
    assert scene.brand_icon('discord',20,20) is False


def test_read_only_render_no_fake_network_calls(monkeypatch):
    app=FakeApp()
    monkeypatch.setattr(ui,'recent_events',lambda limit=100:[])
    monkeypatch.setattr(ui,'load_history',lambda:[])
    for name in ui.PAGES:
        app.selected_page=name
        ui.draw(app)
    assert app.actions==[]
