"""UI-403 regressions for compact displays and truthful network state.

Uses fake Canvas/ConnectApp: no live networking, registry or HOSTS writes.
"""
from types import SimpleNamespace as NS
from vorqeli_connect import native_ui as ui
from test_native_ui_v401 import FakeApp


def capture(monkeypatch):
    lines=[]
    original=ui.Scene.txt
    def store(self,x,y,text,*args,**kwargs):
        lines.append(str(text))
        return original(self,x,y,text,*args,**kwargs)
    monkeypatch.setattr(ui.Scene,'txt',store)
    monkeypatch.setattr(ui.Scene,'logo',lambda *args: True)
    monkeypatch.setattr(ui.Scene,'brand_icon',lambda *args: True)
    return lines


def test_compact_window_uses_scrollbars_and_legible_scale(monkeypatch):
    capture(monkeypatch)
    app=FakeApp()
    app.canvas.winfo_width=lambda: 800
    app.canvas.winfo_height=lambda: 540
    bounds=[]
    app._sync_scrollbars=lambda w,h: bounds.append((w,h))
    ui.draw(app)
    assert bounds[-1]==(round(ui.W*ui.MIN_READABLE_SCALE),round(ui.H*ui.MIN_READABLE_SCALE))
    assert bounds[-1][0]>800 and bounds[-1][1]>540
    assert any(bounds and b[0][2]>1000 for b in app._controls)


def test_normal_window_needs_no_scrollbars(monkeypatch):
    capture(monkeypatch)
    app=FakeApp()
    app.canvas.winfo_width=lambda:1260
    app.canvas.winfo_height=lambda:840
    extents=[]
    app._sync_scrollbars=lambda w,h:extents.append((w,h))
    ui.draw(app)
    assert extents[-1][0]<=1260 and extents[-1][1]<=840


def test_nonstandard_aspect_ratio_does_not_stretch_circles(monkeypatch):
    capture(monkeypatch)
    app=FakeApp()
    app.canvas.winfo_width=lambda:1200
    app.canvas.winfo_height=lambda:600
    scene=ui.Scene(app)
    assert scene.sx==scene.sy==scene.sf
    assert scene.content_width>1200 or scene.content_height>600


def test_error_is_not_reported_as_disconnected(monkeypatch):
    texts=capture(monkeypatch)
    app=FakeApp()
    app.controller.status=lambda:NS(overall='error',dpi='error',telegram='error',dns='error')
    ui.draw(app)
    assert 'Ошибка подключения' in texts
    assert 'ОШИБКА МОДУЛЕЙ' in texts
    assert 'Обход отключён' not in texts


def test_connected_state_does_not_claim_network_access(monkeypatch):
    texts=capture(monkeypatch)
    app=FakeApp()
    app.settings.desired_enabled=True
    app.controller.status=lambda:NS(overall='connected',dpi='on',telegram='on',dns='on')
    ui.draw(app)
    assert 'Модули запущены' in texts
    assert any('не проверка доступа к сайтам' in t for t in texts)
    assert 'Обход активен' not in texts


def test_compact_controls_keep_usable_dimensions(monkeypatch):
    capture(monkeypatch)
    app=FakeApp()
    app.canvas.winfo_width=lambda:790
    app.canvas.winfo_height=lambda:520
    ui.draw(app)
    controls=[b for b,callback,label in app._controls if label=='ПОДКЛЮЧИТЬ']
    assert len(controls)==1
    x1,y1,x2,y2=controls[0]
    assert x2-x1>=210 and y2-y1>=52
