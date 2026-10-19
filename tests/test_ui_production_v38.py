"""v0.38: headless real production visual renderer and accessible action wiring."""
from __future__ import annotations
from types import SimpleNamespace
from PIL import Image
import pytest
from vorqeli_connect import redesign_ui as ui


def test_six_screens_and_five_services_remain_unchanged():
    assert len(ui.PAGES)==6
    assert len(ui.SERVICE_NAMES)==5
    assert ui.SERVICE_NAMES[-1]=='Microsoft (Copilot, Designer, Xbox)'
    assert 'Claude' not in ui.SERVICE_NAMES


@pytest.mark.parametrize('name',ui.PAGES)
def test_real_background_rasters(name):
    im=ui.background(1060,710,name)
    assert im.mode=='RGB'
    assert im.size==(1060,710)
    assert im.getpixel((0,0))!=im.getpixel((300,300))
    assert im.getpixel((275,190))!=im.getpixel((275,90))


def test_background_cached_and_designed_hero():
    im=ui.background(1182,780,'Главная')
    assert im is ui.background(1182,780,'Главная')
    assert im.getpixel((280,205)) != im.getpixel((280,397))
    # Blue waves and glows are clipped: header and sidebar are not covered.
    assert im.getpixel((20,300))==ui.background(1182,780,'Диагностика').getpixel((20,300))


def test_diagnostic_status_truthful():
    assert ui.service_summary('Доступен')==('HTTPS OK',ui.GREEN)
    assert ui.service_summary('HTTP 403')[1]!=ui.GREEN
    assert '403' in ui.service_summary('HTTP 403')[0]
    assert ui.service_summary('Нет ответа')[1]==ui.RED
    assert ui.service_summary('Copilot: OK | Designer: OK | Xbox: OK')[0]=='3/3 HTTPS OK'
    assert ui.service_summary('Copilot: OK | Designer: нет | Xbox: OK')[0]=='Частичный ответ'


class StubCanvas:
    def __init__(self):self.number=0;self.calls=[]
    def _id(self,*a,**k):
        self.number+=1;self.calls.append((a,k));return self.number
    create_line=create_oval=create_polygon=create_rectangle=create_image=create_text=_id
    tag_bind=_id
    itemconfigure=_id
    addtag_withtag=_id
    delete=_id
    configure=_id
    def winfo_width(self):return 1182
    def winfo_height(self):return 780


class StubApp:
    def __init__(self):
        self.canvas=StubCanvas();self._quitting=False
        self.settings=SimpleNamespace(desired_enabled=True,connect_dpi=True,connect_telegram=True,
            connect_dns=True,dns_mode='plain',dpi_mode='alt_auto',launch_at_startup=True,
            minimize_to_tray=True,admin_on_launch=True,restore_last_mode=True)
        self.controller=SimpleNamespace(status=lambda:SimpleNamespace(overall='connected',dpi='on',telegram='on',dns='on'),
            active_dpi_mode='alt2')
        self.selected_page='Главная';self._disconnecting=False;self.running_job=False
        self.detail='Подключено'
        self.last_results=[('Discord','Доступен'),('YouTube','HTTP 403'),('Telegram Web','Доступен'),
          ('ChatGPT','Нет ответа'),('Microsoft (Copilot, Designer, Xbox)','Copilot: OK | Designer: нет | Xbox: OK')]
        self._controls=[]
    def _rounded_coords(self,x1,y1,x2,y2,r):
        return [x1+r,y1,x2-r,y1,x2,y1,x2,y1+r,x2,y2-r,x2,y2,x2-r,y2,x1+r,y2,x1,y2,x1,y2-r,x1,y1+r,x1,y1]
    def _text(self,*args,**kwargs):return self.canvas._id(*args,**kwargs)
    def _register_control(self,bounds,callback,label):
        index=len(self._controls)
        self._controls.append((bounds,callback,label))
        return index
    def _sync_scrollbars(self,w,h):self.scroll=(w,h)
    def _render_focus(self):pass
    def winfo_exists(self):return True
    def _draw(self):pass
    def _mouse_activate(self,index):pass
    def _page(self,page):pass
    def _start_connect(self):pass
    def _start_disconnect(self):pass
    def _diagnose(self):pass
    def _diagnose_service(self,name):pass
    def _show_dns_audit(self):pass
    def _show_engine_logs(self):pass
    def _show_telegram_web_audit(self):pass
    def _export_diagnostics(self):pass
    def _check_updates(self):pass
    def _toggle_setting(self,key):pass
    def _set_dpi_mode(self,mode):pass
    def _set_dns_mode(self,mode):pass
    def _restore_dns(self):pass
    def _show_hosts_manager(self):pass


@pytest.mark.parametrize('page',ui.PAGES)
def test_every_page_paints_and_has_accessible_controls(monkeypatch,page):
    monkeypatch.setattr(ui.ImageTk,'PhotoImage',lambda picture:picture)
    monkeypatch.setattr(ui,'recent_events',lambda limit=80:[
        {'timestamp':'2026-10-19T14:32:16','kind':'connection','message':'DPI подключён'}])
    monkeypatch.setattr(ui,'load_history',lambda:[{'results':{'Discord':'Доступен'}}])
    app=StubApp()
    app.selected_page=page
    ui.draw(app)
    assert app.scroll==(1182,780)
    assert len(app._controls)>=6
    assert all(callable(callback) and 0<=x<xr<=1182 and 0<=y<yb<=780
               for (x,y,xr,yb),callback,label in app._controls)
    assert all(isinstance(label,str) and label for _,_,label in app._controls)
    if page in ('Главная','Диагностика','О проекте','Настройки','Сеть и стратегии'):
        assert len(app._button_images)>0


def test_diagnostics_only_five_service_buttons(monkeypatch):
    monkeypatch.setattr(ui.ImageTk,'PhotoImage',lambda picture:picture)
    app=StubApp();app.selected_page='Диагностика'
    ui.draw(app)
    assert sum(label=='ПРОВЕРИТЬ' for _,_,label in app._controls)==5
    assert sum('ПРОВЕРИТЬ ВСЁ' in label for _,_,label in app._controls)==1


def test_network_files_not_edited_by_renderer():
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    source=(root/'src/vorqeli_connect/redesign_ui.py').read_text(encoding='utf-8')
    assert 'Set-DnsClientServerAddress' not in source
    assert 'winreg' not in source
    assert 'ShellExecute' not in source
    assert 'subprocess.run' not in source
