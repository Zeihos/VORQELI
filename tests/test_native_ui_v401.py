"""Native screen, action routing and UI integrity tests without OS/network calls."""
from pathlib import Path
from types import SimpleNamespace as NS

import pytest
from vorqeli_connect import native_ui as ui


@pytest.fixture(autouse=True)
def _no_real_tk_in_fake_canvas(monkeypatch):
    monkeypatch.setattr(ui.Scene,'brand_icon',lambda *args:True)


class FakeCanvas:
    def __init__(self):
        self.num=0
        self.tags={}
        self.bindings={}
        self.config={}
    def _item(self,*args,**kwargs):
        self.num+=1
        return self.num
    create_polygon=create_rectangle=create_line=create_oval=create_text=create_image=_item
    def delete(self,*a):pass
    def configure(self,**kwargs):self.config.update(kwargs)
    def winfo_width(self):return 1260
    def winfo_height(self):return 840
    def bind(self,key,callback):self.bindings[key]=callback
    def tag_bind(self,name,key,callback):self.tags[(name,key)]=callback
    def itemconfigure(self,*a,**kwargs):pass


class FakeApp:
    def __init__(self):
        self.canvas=FakeCanvas()
        self.settings=NS(desired_enabled=False,connect_dpi=True,connect_telegram=True,
            connect_dns=True,dpi_mode='alt_auto',dns_mode='plain',
            launch_at_startup=False,restore_last_mode=True,minimize_to_tray=True,admin_on_launch=True)
        self.controller=NS(status=lambda:NS(overall='off',dpi='off',telegram='off',dns='off'),active_dpi_mode=None)
        self._quitting=False
        self._controls=[]
        self._widgets=[]
        self._native_history_filter='Все события'
        self.selected_page='Главная'
        self.last_results=[]
        self.actions=[]
    def winfo_exists(self):return True
    def _register_control(self,bounds,callback,label):
        self._controls.append((bounds,callback,label))
        return len(self._controls)-1
    def _mouse_activate(self,idx):self._controls[idx][1]()
    def _sync_scrollbars(self,w,h):pass
    def _render_focus(self):pass
    def _draw(self):ui.draw(self)
    def _page(self,name):self.selected_page=name;self._draw()
    def _window_close(self):self.actions.append('close')
    def _start_connect(self):self.actions.append('connect')
    def _start_disconnect(self):self.actions.append('disconnect')
    def _diagnose(self):self.actions.append('all')
    def _diagnose_service(self,name):self.actions.append(name)
    def _show_dns_audit(self):self.actions.append('dns-audit')
    def _show_engine_logs(self):self.actions.append('engine-logs')
    def _show_telegram_web_audit(self):self.actions.append('telegram-web-audit')
    def _check_updates(self):self.actions.append('updates')
    def _show_hosts_manager(self):self.actions.append('hosts')
    def _restore_dns(self):self.actions.append('restore-dns')
    def _toggle_setting(self,key):setattr(self.settings,key,not getattr(self.settings,key));self._draw()
    def _set_dns_mode(self,mode):self.settings.dns_mode=mode;self._draw()
    def _set_dpi_mode(self,mode):self.settings.dpi_mode=mode;self._draw()


def test_genuine_vector_controls_not_baked_image():
    source=Path(ui.__file__).read_text(encoding='utf8')
    assert 'premium/home.png' not in source
    assert 'premium/settings.png' not in source
    assert 'create_polygon' in source and 'create_text' in source
    assert 'create_image' in source  # only actual unchanged logo, not UI bitmap
    assert 'Image.open(file)' in source


@pytest.mark.parametrize('page',ui.PAGES)
def test_every_screen_renders_real_canvas_primitives(monkeypatch,page):
    monkeypatch.setattr(ui.Scene,'logo',lambda *args:True)
    monkeypatch.setattr(ui,'recent_events',lambda limit=100:[])
    monkeypatch.setattr(ui,'load_history',lambda:[])
    app=FakeApp();app.selected_page=page
    ui.draw(app)
    assert app.canvas.num>45, (page,app.canvas.num)
    assert len(app._controls)>=7
    assert ('<ButtonPress-1>' in app.canvas.bindings)


def test_button_routes_to_existing_controller_action(monkeypatch):
    monkeypatch.setattr(ui.Scene,'logo',lambda *args:True)
    app=FakeApp();ui.draw(app)
    matches=[i for i,(bounds,cb,label) in enumerate(app._controls) if label=='ПОДКЛЮЧИТЬ']
    assert len(matches)==1
    app._mouse_activate(matches[0])
    assert app.actions==['connect']


def test_real_switch_routes_to_settings(monkeypatch):
    monkeypatch.setattr(ui.Scene,'logo',lambda *args:True)
    app=FakeApp();app.selected_page='Настройки'
    ui.draw(app)
    assert not app.settings.launch_at_startup
    app.canvas.tags[('opt_launch_at_startup','<Button-1>')](NS())
    assert app.settings.launch_at_startup


def test_diagnostic_statuses_never_label_403_as_available():
    assert ui.classify_service('HTTP 403')[1] != ui.C['green']
    assert ui.classify_service('HTTP 429')[1] != ui.C['green']
    assert ui.classify_service('Доступен') == ('HTTPS OK',ui.C['green'])
    assert ui.classify_service('Copilot: OK | Designer: HTTP403 | Xbox: OK')[1] != ui.C['green']


def test_all_five_real_service_names_are_used():
    assert len(ui.SERVICE_NAMES)==5
    assert set(ui.SERVICE_NAMES)==set(ui.SERVICES)
    assert len(ui.ALT_MODES)==13


def test_history_uses_actual_event_action(monkeypatch):
    app=FakeApp()
    monkeypatch.setattr(ui,'recent_events',lambda limit=100:[
        {'action':'connection','message':'Подключение завершено','timestamp':'2026-10-21T09:30:22Z'},
        {'action':'error','message':'Отказ','timestamp':'2026-10-21T10:30:22Z'}])
    app._native_history_filter='Ошибки'
    assert len(ui.history_events(app))==1
    assert ui.history_events(app)[0]['action']=='error'


def test_drawing_does_not_change_settings_or_request_network(monkeypatch):
    monkeypatch.setattr(ui.Scene,'logo',lambda *args:True)
    app=FakeApp();before=vars(app.settings).copy()
    for page in ui.PAGES:
        app.selected_page=page
        monkeypatch.setattr(ui,'recent_events',lambda limit=100:[])
        monkeypatch.setattr(ui,'load_history',lambda:[])
        ui.draw(app)
    assert vars(app.settings)==before
    assert not app.actions


def test_service_diagnostics_each_button_is_callable(monkeypatch):
    monkeypatch.setattr(ui.Scene,'logo',lambda *args:True)
    app=FakeApp();app.selected_page='Диагностика'
    ui.draw(app)
    assert len([c for b,c,t in app._controls if t=='ПРОВЕРИТЬ'])==5
    for _,callback,label in list(app._controls):
        if label=='ПРОВЕРИТЬ':callback()
    assert app.actions==list(ui.SERVICE_NAMES)


def test_network_has_auto_and_thirteen_modes(monkeypatch):
    monkeypatch.setattr(ui.Scene,'logo',lambda *args:True)
    app=FakeApp();app.selected_page='Сеть и стратегии'
    ui.draw(app)
    labels=[z for bounds,cb,z in app._controls]
    assert all(mode.upper() in labels for mode in ui.ALT_MODES)
    assert 'АВТО 1–13' in labels
    pos=labels.index('ALT13')
    app._controls[pos][1]()
    assert app.settings.dpi_mode=='alt13'


def test_dns_selection_is_disabled_during_live_session(monkeypatch):
    monkeypatch.setattr(ui.Scene,'logo',lambda *args:True)
    app=FakeApp();app.selected_page='Сеть и стратегии';app.settings.desired_enabled=True
    ui.draw(app)
    labels=[z for _,_,z in app._controls]
    assert 'IPv4 DNS' not in labels
    assert 'DoH / HTTPS' not in labels


def test_seven_setting_toggles_are_independent(monkeypatch):
    monkeypatch.setattr(ui.Scene,'logo',lambda *args:True)
    app=FakeApp();app.selected_page='Настройки'
    ui.draw(app)
    assert len([key for key in app.canvas.tags if key[0].startswith('opt_') and key[1]=='<Button-1>'])==7
    original=vars(app.settings).copy()
    for key in ('launch_at_startup','connect_dpi','connect_telegram','connect_dns'):
        app.canvas.tags[('opt_'+key,'<Button-1>')](NS())
        assert getattr(app.settings,key)!=original[key]


def test_history_pagination_and_filter(monkeypatch):
    monkeypatch.setattr(ui.Scene,'logo',lambda *args:True)
    monkeypatch.setattr(ui,'load_history',lambda:[])
    monkeypatch.setattr(ui,'recent_events',lambda limit=100:[
        {'timestamp':f'2026-10-21T09:30:{i:02d}Z','action':'connection','message':f'Событие {i}'}
        for i in range(24)])
    app=FakeApp();app.selected_page='История'
    ui.draw(app)
    labels=[z for _,_,z in app._controls]
    assert '›' in labels
    ix=labels.index('›')
    app._controls[ix][1]()
    assert app._native_history_page==1
    app.canvas.tags  # controls remain available on second page


def test_logo_resource_is_left_unmodified_in_patch():
    source=Path(ui.__file__).read_text(encoding='utf8')
    assert "asset('VORQELI-logo.png')" in source
    assert 'ImageTk.PhotoImage' in source
    assert '.resize((pixels,pixels)' in source


def test_all_main_actions_are_real_callbacks(monkeypatch):
    monkeypatch.setattr(ui.Scene,'logo',lambda *args:True)
    app=FakeApp();app.selected_page='Главная'
    ui.draw(app)
    labels=[z for _,_,z in app._controls]
    for required in ('ПОДКЛЮЧИТЬ','Диагностика   ›','История событий   ›','Настройки сети   ›'):
        assert required in labels


def test_no_automatic_external_calls_on_app_draw(monkeypatch):
    monkeypatch.setattr(ui.Scene,'logo',lambda *args:True)
    monkeypatch.setattr(ui,'recent_events',lambda limit=100:[])
    monkeypatch.setattr(ui,'load_history',lambda:[])
    def fail(*a,**k):raise AssertionError('draw must be read-only')
    monkeypatch.setattr(ui.webbrowser,'open',fail)
    app=FakeApp()
    for page in ui.PAGES:
        app.selected_page=page;ui.draw(app)
