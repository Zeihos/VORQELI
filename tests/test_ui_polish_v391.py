"""Production UI regression checks for v0.39.1: real data, not screenshot samples."""
from __future__ import annotations
import json
from types import SimpleNamespace as NS

from PIL import ImageChops
import pytest
from vorqeli_connect import premium_ui as ui, frameless


def make_app(active=False):
    s=NS(desired_enabled=active,connect_dpi=True,connect_telegram=True,connect_dns=True,
         dns_mode='plain',dpi_mode='alt_auto',telegram_secret='x'*32)
    value='on' if active else 'off'
    c=NS(status=lambda:NS(overall='connected' if active else 'off',
                          dpi=value,telegram=value,dns=value),active_dpi_mode=None)
    return NS(settings=s,controller=c,selected_page='Главная',last_results=[],
              _visual_history_filter='Все события',_visual_history_page=0)


def test_live_hero_is_neutral_when_disconnected():
    on=ui._live_hero('connected')
    off=ui._live_hero('off')
    assert on.mode=='RGBA' and off.mode=='RGBA'
    assert ImageChops.difference(on.convert('RGB'),off.convert('RGB')).getbbox()
    assert off.getpixel((0,0))[3]==0   # rounded corner: no black square
    assert on.getpixel((0,0))[3]==0


def test_real_off_and_on_state_render():
    on=ui.build_frame(make_app(True))
    off=ui.build_frame(make_app(False))
    assert on.size==off.size==(1536,1024)
    assert ImageChops.difference(on,off).getbbox()


def test_history_filters_read_actual_action_schema(monkeypatch):
    rows=[
        {'timestamp':'2026-10-20T10:00:00','action':'connection', 'message':'Соединение включено'},
        {'timestamp':'2026-10-20T10:00:02','action':'settings','message':'Выбрано ALT11'},
        {'timestamp':'2026-10-20T10:00:03','action':'error','message':'Ошибка соединения'},
    ]
    monkeypatch.setattr(ui,'recent_events',lambda limit=100:rows)
    a=make_app()
    assert len(ui._history_events(a))==3
    for name,action in [('Подключение','connection'),('Настройки','settings'),('Ошибки','error')]:
        a._visual_history_filter=name
        assert any(x['action']==action for x in ui._history_events(a))


def test_history_pagination_boundaries(monkeypatch):
    rows=[{'timestamp':'2026-10-20T10:00:00','action':'event','message':str(i)} for i in range(25)]
    monkeypatch.setattr(ui,'recent_events',lambda limit=100:rows)
    a=make_app();draws=[];a._draw=lambda:draws.append(True)
    ui._history_turn(a,1)
    assert a._visual_history_page==1
    ui._history_turn(a,200)
    assert a._visual_history_page==2
    ui._history_turn(a,-200)
    assert a._visual_history_page==0 and len(draws)==3


def test_actual_history_is_exported_not_diagnostics(monkeypatch,tmp_path):
    from tkinter import filedialog
    dest=tmp_path/'history.json'
    monkeypatch.setattr(filedialog,'asksaveasfilename',lambda **kw:str(dest))
    monkeypatch.setattr(ui,'recent_events',lambda limit=100:[
        {'timestamp':'2026-10-20T10:00:00','action':'connection',
         'message':'secret='+('x'*32)}])
    a=make_app()
    ui.export_history(a)
    report=json.loads(dest.read_text('utf-8'))
    assert report['events'][0]['action']=='connection'
    assert 'x'*32 not in dest.read_text('utf-8')
    assert '[СКРЫТО]' in report['events'][0]['message']
    assert 'results' not in report


def test_canvas_hit_targets_do_not_darken_artwork():
    class Canvas:
        def __init__(self):self.bindings={};self.created=[];self.cursor=''
        def bind(self,key,callback,add=None):self.bindings[key]=callback
        def canvasx(self,x):return x
        def canvasy(self,y):return y
        def configure(self,**kw):self.cursor=kw['cursor']
        def create_rectangle(self,*a,**kw):self.created.append((a,kw))
    class App:
        def __init__(self):self.canvas=Canvas();self.controls=[];self.pressed=[]
        def _register_control(self,bounds,callback,label):
            self.controls.append((bounds,callback,label));return len(self.controls)-1
        def _mouse_activate(self,i):self.pressed.append(i)
    a=App();r=ui.HitRegistry(a,1,1)
    r.target((40,45,110,100),lambda:None,'Проверка')
    r.install()
    assert not a.canvas.created  # Previously overlaid dark black stipple on UI
    event=NS(x=60,y=60)
    a.canvas.bindings['<Motion>'](event)
    assert a.canvas.cursor=='hand2'
    a.canvas.bindings['<Button-1>'](event)
    assert a.pressed==[0]


def test_frameless_fixed_size_and_single_restore_binding():
    for sw,sh in ((1920,1080),(1366,768),(1024,600)):
        geom=frameless.fixed_geometry(sw,sh)
        size=geom.split('+')[0]
        w,h=map(int,size.split('x'))
        assert w<=sw and h<=sh

    class FakeApp:
        def __init__(self):self.count=0;self._premium_minimized=False
        def winfo_exists(self):return True
        def overrideredirect(self,val=None):return True if val is None else None
        def bind(self,*args,**kwargs):self.count+=1
        def iconify(self):pass
    a=FakeApp()
    frameless.minimize(a);frameless.minimize(a)
    assert a.count==1
