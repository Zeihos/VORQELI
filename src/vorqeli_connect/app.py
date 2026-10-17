"""VORQELI Connect: single-button desktop window, polished glass-like UI and tray.

The application intentionally keeps the main process alive while hidden in tray.
Only user-initiated Disconnect clears the persisted desired connection state.
"""
from __future__ import annotations
import json
import os
import queue
import re
import sys
import threading
import time
import tkinter as tk
import webbrowser
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, filedialog
from PIL import Image, ImageDraw, ImageFilter, ImageTk

from .config import APP_DIR, load_settings, save_settings
from .diagnostics import check_all
from .event_log import record_event, recent_events
from .geohide import INFO_PAGE, DOH_TEMPLATE, STATE_FILE
from .history import record_scan, load_history
from .log_tools import tail_log, redact_secrets
from .startup import is_admin, relaunch_elevated, configure_startup
from .unified import UnifiedController, ConnectionReport
from .engine_adapters import proxy_link

VERSION = '0.12.0'
BG = '#0B0F1E'
PANEL = '#1C223A'
LIGHT = '#F7F6FF'
MUTED = '#A0A9C3'
LAV = '#A38AFF'
CYAN = '#8ACBFE'
MINT = '#86E6C2'
PINK = '#EF9ADB'


def asset(name: str) -> Path:
    """Works for source checkout and PyInstaller --onefile."""
    base = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[2]))
    return base / 'assets' / name


def gradient_background(w: int, h: int) -> Image.Image:
    """Precomposed translucent layers; only drawn on resize/page change."""
    w = max(w, 600); h = max(h, 520)
    out = Image.new('RGBA', (w, h), (12, 16, 32, 255))
    pixels = ImageDraw.Draw(out)
    for y in range(h):
        f = y / max(h, 1)
        pixels.line((0, y, w, y), fill=(11+int(f*8), 15+int(f*8), 30+int(f*12), 255))
    for x, y, r, rgba in [
        (int(w*.85), int(h*.12), int(h*.47), (109, 77, 222, 70)),
        (int(w*.45), int(h*.75), int(h*.44), (40, 108, 216, 56)),
        (int(w*.10), int(h*.05), int(h*.35), (117, 60, 170, 24)),
    ]:
        glow = Image.new('RGBA', (w, h))
        ImageDraw.Draw(glow).ellipse((x-r, y-r, x+r, y+r), fill=rgba)
        out = Image.alpha_composite(out, glow.filter(ImageFilter.GaussianBlur(92)))
    layer = Image.new('RGBA',(w,h))
    d = ImageDraw.Draw(layer)
    # Semi-transparent sidebar composited above the background.
    d.rounded_rectangle((15, 15, 242, h-16), radius=26, fill=(31, 36, 60, 175), outline=(180, 167, 248, 47), width=1)
    return Image.alpha_composite(out,layer)


def glass_card(draw: ImageDraw.ImageDraw, rect: tuple[int,int,int,int],
               accent=False, radius=25) -> None:
    x1,y1,x2,y2=rect
    if x2 <= x1 or y2 <= y1: return
    draw.rounded_rectangle((x1+3,y1+9,x2+3,y2+9), radius=radius, fill=(2,5,19,36))
    draw.rounded_rectangle(rect, radius=radius,
                           fill=(39, 43, 72, 152) if accent else (30, 35, 59, 153),
                           outline=(200, 191, 255, 71), width=2)
    draw.rounded_rectangle((x1+12,y1+7,x2-12,y1+13), radius=3,fill=(248,240,255,13))


def _button(parent, label, callback, *, accent=False, size=11, width=None):
    return tk.Button(parent, text=label, command=callback, bg='#9678F6' if accent else '#2A304B',
        fg='#101126' if accent else LIGHT, activebackground='#BDAAFF' if accent else '#3A4365',
        activeforeground='#0B1020' if accent else LIGHT, font=('Segoe UI',size,'bold'),
        bd=0, relief='flat', cursor='hand2', padx=24, pady=12,
        highlightthickness=0, width=width)


class ConnectApp(tk.Tk):
    def __init__(self, *, minimized=False):
        super().__init__()
        self.settings = load_settings()
        self.title('VORQELI Connect')
        self.configure(bg=BG)
        self.geometry(self.settings.window_geometry if re.fullmatch(r'\d{3,4}x\d{3,4}(?:[+-]\d+[+-]\d+)?',self.settings.window_geometry) else '1120x720')
        self.minsize(980,650)
        self.events = queue.Queue()
        self.controller = UnifiedController(self.settings, emit=lambda typ, data:self.events.put((typ,data)))
        self.connected_text = 'Не подключено'
        self.detail = 'Готов к работе · одно нажатие для запуска'
        self.selected_page = 'Главная'
        self.running_job = False
        self._quitting = False
        self._tray = None
        self._tray_ready = False
        self._resize_job = None
        self._canvas_bg = None
        self._logo_tk = None
        self._widgets = []
        self._last_health = None
        self.last_results = []
        self.canvas = tk.Canvas(self, bg=BG, highlightthickness=0, bd=0)
        self.canvas.pack(fill='both', expand=True)
        self.bind('<Configure>', self._resize)
        self.protocol('WM_DELETE_WINDOW', self.hide_to_tray)
        self._launch_tray()
        self.after(220, self._poll)
        self.after(800, self._health_check)
        self.after(150, self._draw)
        if minimized:
            self.withdraw()
        if self.settings.desired_enabled:
            self.after(1300, self._start_connect)
        elif STATE_FILE.exists():
            self.detail = 'Найдены сохранённые настройки GeoHide · откройте настройки для восстановления'
            self.after(1200, self._draw)
        if self.settings.first_launch_notice and not minimized:
            self.after(1250, self._first_notice)

    def _first_notice(self):
        self.settings.first_launch_notice = False
        save_settings(self.settings)
        messagebox.showinfo('VORQELI Connect',
            'Первое подключение может загрузить официальный DPI-пакет Flowseal (проверяется SHA-256).\n\n'
            'Для WinDivert и системного DNS Windows потребуются права администратора (UAC).\n'
            'При включённом автозапуске программа создаст задачу Windows, чтобы затем работать из трея.\n\n'
            'GeoHide меняет DNS активных сетевых адаптеров. Отключение возвращает прежние настройки.',parent=self)

    def _launch_tray(self):
        try:
            import pystray
            image = Image.open(asset('VORQELI-logo.png')).convert('RGBA').resize((64,64))
            self._tray = pystray.Icon('VORQELI-Connect',image,'VORQELI Connect',
                menu=pystray.Menu(
                    pystray.MenuItem('Открыть VORQELI', lambda *x: self.events.put(('show',None)), default=True),
                    pystray.MenuItem('Подключиться',lambda *x:self.events.put(('connect',None))),
                    pystray.MenuItem('Отключиться',lambda *x:self.events.put(('disconnect',None))),
                    pystray.Menu.SEPARATOR,
                    pystray.MenuItem('Выход из приложения',lambda *x:self.events.put(('quit',None))),
                ))
            threading.Thread(target=self._run_tray,daemon=True,name='VorqeliTray').start()
        except Exception as exc:
            self.detail=f'Трей недоступен: {exc}'

    def _run_tray(self):
        try:
            self._tray_ready=True
            self._tray.run()
        except Exception as exc:
            self.events.put(('progress',f'Не удалось создать трей: {exc}'))
            self._tray_ready=False

    def _resize(self, event):
        if event.widget is not self: return
        if self._resize_job: self.after_cancel(self._resize_job)
        self._resize_job=self.after(170,self._draw)

    def _text(self,x,y,value,size=12,color=LIGHT,anchor='nw',weight='normal',width=0,**kwargs):
        return self.canvas.create_text(x,y,text=value,fill=color,anchor=anchor,
            font=('Segoe UI',size,weight),width=width,**kwargs)

    def _place_button(self,x,y,label,callback,*,accent=False,width=None,size=10):
        b=_button(self.canvas,label,callback,accent=accent,size=size,width=width)
        self._widgets.append(b)
        self.canvas.create_window(x,y,window=b,anchor='nw')
        return b

    def _nav(self,name,y,marker):
        active = name == self.selected_page
        b = tk.Button(self.canvas, text=f"  {marker}    {name}", command=lambda n=name:self._page(n),
            anchor='w', bg='#383454' if active else '#22253E',
            fg=LIGHT if active else MUTED, activebackground='#443D65',
            activeforeground=LIGHT, font=('Segoe UI',11,'bold' if active else 'normal'),
            relief='flat', bd=0, cursor='hand2', padx=9, pady=9)
        self._widgets.append(b)
        self.canvas.create_window(36,y-11,window=b,anchor='nw',width=190,height=46)

    def _page(self,name):
        self.selected_page=name
        self._draw()

    def _draw(self):
        if self._quitting or not self.winfo_exists():return
        w=max(980,self.winfo_width());h=max(650,self.winfo_height())
        for obj in self._widgets:
            try: obj.destroy()
            except tk.TclError: pass
        self._widgets=[]
        self.canvas.delete('all')
        backdrop=gradient_background(w,h)
        glass_layer=Image.new('RGBA',(w,h))
        d=ImageDraw.Draw(glass_layer)
        main_x=275; right=w-26; avail=right-main_x
        glass_card(d,(main_x,96,right,302),accent=True)
        if self.selected_page=='Главная':
            box_w=(avail-28)//3
            for j in range(3):
                left=main_x+j*(box_w+14)
                glass_card(d,(left,328,left+box_w,487),radius=20)
            glass_card(d,(main_x,505,right,h-28),radius=23)
        else:
            glass_card(d,(main_x,328,right,h-28),radius=23)
        backdrop=Image.alpha_composite(backdrop,glass_layer)
        self._canvas_bg=ImageTk.PhotoImage(backdrop.convert('RGB'))
        self.canvas.create_image(0,0,image=self._canvas_bg,anchor='nw')
        try:
            logo=Image.open(asset('VORQELI-logo.png')).convert('RGBA').resize((78,78),Image.Resampling.LANCZOS)
            self._logo_tk=ImageTk.PhotoImage(logo)
            self.canvas.create_image(53,34,image=self._logo_tk,anchor='nw')
        except Exception:
            self._text(57,46,'V',33,LAV,weight='bold')
        self._text(49,117,'VORQELI',18,LIGHT,weight='bold')
        self._text(49,148,'CONNECT  /  CONTROL',8,MUTED,weight='bold')
        for i,(name,sym) in enumerate([('Главная','◇'),('Диагностика','◎'),('История','◷'),('Настройки','⚙'),('О проекте','ⓘ')]):
            self._nav(name,230+i*60,sym)
        self._text(48,h-86,'●   Локальное приложение',10,MINT)
        self._text(48,h-58,'VERSION  0.12.0',9,MUTED)
        self._text(main_x,35,'NETWORK CONTROL CENTER',10,LAV,weight='bold')
        self._text(right,35,'●  WINDOWS 10 / 11',10,MUTED,anchor='ne')
        if self.selected_page=='Главная':self._draw_home(main_x,right,h)
        elif self.selected_page=='Диагностика':self._draw_diagnostics(main_x,right,h)
        elif self.selected_page=='История':self._draw_history(main_x,right,h)
        elif self.selected_page=='Настройки':self._draw_settings(main_x,right,h)
        else:self._draw_about(main_x,right,h)

    def _draw_header(self,x,right,title,subtitle):
        self._text(x+29,121,title,23,LIGHT,weight='bold')
        self._text(x+30,162,subtitle,11,MUTED,width=right-x-70)

    def _draw_home(self,x,right,h):
        report=self.controller.status()
        state=report.overall
        names={'connected':'Модули запущены','partial':'Частично подключено','error':'Ошибка подключения','off':'Не подключено'}
        accent={'connected':MINT,'partial':'#FFD09D','error':PINK,'off':CYAN}[state]
        self._text(x+31,119,'◆   СОСТОЯНИЕ ПОДКЛЮЧЕНИЯ',10,LAV,weight='bold')
        self._text(x+30,151,names[state],27,LIGHT,weight='bold')
        self._text(x+31,203,self.detail[:150],10,MUTED,width=max(180,right-x-360))
        active=self.settings.desired_enabled
        self._place_button(right-244,152, 'Отключить' if active else 'Подключиться →',
                           self._start_disconnect if active else self._start_connect,
                           accent=not active,width=15,size=12)
        self._text(x+31,270,'●  '+('ПОДКЛЮЧЕНИЕ ВКЛЮЧЕНО' if active else 'РЕЖИМ ОЖИДАНИЯ'),10,accent,weight='bold')
        cards=[('DPI · WINWS',self.settings.connect_dpi,'dpi', 'Управление трафиком','◈'),
               ('TELEGRAM',self.settings.connect_telegram,'telegram','Локальный MTProto','↗'),
               ('GEOHIDE DNS',self.settings.connect_dns,'dns','Географические сервисы','◉')]
        size=(right-x-28)//3
        for i,(title,enabled,key,description,symbol) in enumerate(cards):
            left=x+i*(size+14)
            val=getattr(report,key)
            color={'on':MINT,'error':PINK,'off':MUTED}.get(val,MUTED)
            self._text(left+19,346,symbol,20,LAV)
            self._text(left+57,352,title,11,LIGHT,weight='bold')
            self._text(left+19,398,description,10,MUTED)
            self._text(left+19,439,'● '+('Работает' if val=='on' else 'Ошибка' if val=='error' else 'Ожидает') if enabled else '○  Выключен в профиле',10,color)
        self._text(x+25,524,'ПРОСТО. СПОКОЙНО. ПОД КОНТРОЛЕМ.',10,LAV,weight='bold')
        self._text(x+25,553,'Закрой окно — VORQELI продолжит работу в системном трее.',11,LIGHT)
        self._text(x+25,581,'При запуске Windows восстановится последнее выбранное состояние.',10,MUTED)
        self._place_button(x+25,h-91,'Настройки модулей',lambda:self._page('Настройки'),size=10)
        self._place_button(x+244,h-91,'Диагностика',lambda:self._page('Диагностика'),size=10)

    def _draw_diagnostics(self,x,right,h):
        self._draw_header(x,right,'Проверка соединений','Диагностика HTTPS для Discord, YouTube, Telegram и GitHub')
        self._place_button(x+30,231,'Проверить сейчас →',self._diagnose,accent=True,size=11)
        self._text(x+30,349,'ПОСЛЕДНИЕ РЕЗУЛЬТАТЫ',11,LAV,weight='bold')
        results=self.last_results or [('Discord','Не проверено'),('YouTube','Не проверено'),('Telegram','Не проверено'),('GitHub','Не проверено')]
        for j,(name,status) in enumerate(results[:7]):
            y=395+j*39
            self._text(x+35,y,str(name),12,LIGHT,weight='bold')
            self._text(right-30,y,str(status),11,MINT if status=='Доступен' else MUTED,anchor='ne')

    def _draw_history(self,x,right,h):
        self._draw_header(x,right,'История и события','Последние проверки и действия остаются на этом компьютере')
        entries=recent_events()[-8:]
        self._text(x+30,353,'ЖУРНАЛ ДЕЙСТВИЙ',11,LAV,weight='bold')
        if not entries:self._text(x+30,391,'Записей ещё нет.',12,MUTED)
        for j,event in enumerate(reversed(entries)):
            y=385+j*37
            self._text(x+35,y,event.get('timestamp','')[:16].replace('T',' '),9,MUTED)
            self._text(x+193,y,str(event.get('message',''))[:85],10,LIGHT)

    def _toggle(self,x,y,label,value,callback):
        self._text(x,y+8,label,12,LIGHT)
        button=self._place_button(x+270,y,'ВКЛ' if value else 'ВЫКЛ',callback,
                                   accent=value,size=9,width=6)
        return button

    def _draw_settings(self,x,right,h):
        self._draw_header(x,right,'Настройки подключения','Одна кнопка запускает все выбранные компоненты')
        self._text(x+30,349,'КОМПОНЕНТЫ',10,LAV,weight='bold')
        controls=[('DPI · Flowseal', 'connect_dpi'),('Telegram MTProto','connect_telegram'),('GeoHide DNS','connect_dns')]
        for j,(label,key) in enumerate(controls):
            self._toggle(x+34,380+j*54,label,getattr(self.settings,key),lambda k=key:self._toggle_setting(k))
        self._text(x+34,552,'Автозапуск с Windows',12,LIGHT)
        self._place_button(x+304,540,'ВКЛ' if self.settings.launch_at_startup else 'ВЫКЛ',
                           lambda:self._toggle_setting('launch_at_startup'),
                           accent=self.settings.launch_at_startup,width=6,size=9)
        self._text(x+34,h-71,'GeoHide меняет системные DNS-адреса. Отключение восстанавливает их.',9,MUTED,
                   width=right-x-56)
        self._place_button(right-270,231,'Вернуть исходный DNS',self._restore_dns,size=10)
        self._place_button(x+470,536,'Открыть прокси в Telegram ↗',self._open_telegram_proxy,size=9)

    def _draw_about(self,x,right,h):
        self._draw_header(x,right,'О VORQELI Connect','Персональный центр управления сетевыми подключениями')
        self._text(x+30,353,'VORQELI  ·  VERSION '+VERSION,15,LIGHT,weight='bold')
        for i,line in enumerate([
            'Настоящий локальный клиент, без аккаунтов и телеметрии.',
            'WinWS: Flowseal / zapret-discord-youtube 1.10.3.',
            'Telegram: Flowseal / tg-ws-proxy 1.11.2.',
            'GeoHide: сторонний DNS-провайдер. Не является VPN.',
            'Статус: предварительная сборка — требуется тестирование в Windows.',
        ]):self._text(x+33,397+i*35,line,11,MUTED)
        self._place_button(x+30,h-98,'GitHub ↗',lambda:webbrowser.open('https://github.com/Zeihos/VORQELI'),size=11)
        self._place_button(x+170,h-98,'GeoHide ↗',lambda:webbrowser.open(INFO_PAGE),size=11)

    def _open_telegram_proxy(self):
        try:
            webbrowser.open(proxy_link(self.settings.telegram_port,self.settings.telegram_secret))
        except ValueError:
            messagebox.showwarning('Telegram','Сначала подключите Telegram-прокси',parent=self)

    def _toggle_setting(self,key):
        setattr(self.settings,key,not getattr(self.settings,key))
        try:
            save_settings(self.settings)
            if key=='launch_at_startup' and os.name=='nt':
                configure_startup(self.settings.launch_at_startup)
        except Exception as exc:
            self.detail=f'Ошибка настройки: {exc}'
        if self.settings.desired_enabled:
            self.detail='Настройка сохранена. Для применения отключите и снова подключитесь.'
        self._draw()

    def _start_connect(self):
        if self._quitting or self.running_job:return
        if os.name=='nt' and not is_admin() and (self.settings.connect_dpi or self.settings.connect_dns):
            self.settings.desired_enabled=True
            save_settings(self.settings)
            if relaunch_elevated():
                self._quit_now(skip_disconnect=True)
            else:
                self.settings.desired_enabled=False
                save_settings(self.settings)
                messagebox.showwarning('Права администратора',
                     'Windows не разрешила повышение прав. Отключите DPI/GeoHide или запустите приложение от администратора.',parent=self)
            return
        self.running_job=True
        self.detail='Подключение компонентов…'
        self._draw()
        threading.Thread(target=self._worker_connect,daemon=True,name='ConnectWorker').start()

    def _worker_connect(self):
        try:self.controller.connect()
        except Exception as exc:self.events.put(('error',str(exc)))
        finally:self.events.put(('idle',None))

    def _start_disconnect(self):
        if self._quitting:return
        self.controller.settings.desired_enabled=False
        save_settings(self.settings)
        self.detail='Отключение и восстановление сетевых настроек…'
        self._draw()
        threading.Thread(target=self._worker_disconnect,daemon=True,name='DisconnectWorker').start()

    def _worker_disconnect(self):
        try:self.controller.disconnect()
        except Exception as exc:self.events.put(('error',str(exc)))
        finally:self.events.put(('idle',None))

    def _restore_dns(self):
        if not STATE_FILE.exists():
            messagebox.showinfo('GeoHide','Сохранённых DNS-настроек нет.',parent=self)
            return
        threading.Thread(target=self._worker_restore_dns,daemon=True).start()

    def _worker_restore_dns(self):
        from .geohide import restore_dns
        try:
            restore_dns()
            self.events.put(('progress','Исходные DNS-настройки восстановлены.'))
        except Exception as exc:self.events.put(('error',f'Не удалось восстановить DNS: {exc}'))

    def _diagnose(self):
        if self.running_job:return
        self.running_job=True
        self.detail='Диагностика выполняется…'
        self._draw()
        threading.Thread(target=self._scan_worker,daemon=True).start()

    def _scan_worker(self):
        try:self.events.put(('diagnostics',check_all()))
        except Exception as exc:self.events.put(('error',str(exc)))
        finally:self.events.put(('idle',None))

    def _poll(self):
        if self._quitting:return
        redraw=False
        try:
            while True:
                typ,value=self.events.get_nowait()
                if typ=='progress':self.detail=str(value);redraw=True
                elif typ=='state':
                    self.detail= value.detail or ('Подключение активно' if value.overall=='connected' else 'Отключено')
                    if value.telegram == 'on' and not self.settings.telegram_link_opened and os.name == 'nt':
                        try:
                            webbrowser.open(proxy_link(self.settings.telegram_port,self.settings.telegram_secret))
                            self.settings.telegram_link_opened=True
                            save_settings(self.settings)
                        except (OSError,ValueError):
                            pass
                    try:record_event('connection',f'Состояние: {value.overall}; DPI={value.dpi}; TG={value.telegram}; DNS={value.dns}')
                    except Exception:pass
                    redraw=True
                elif typ=='idle':self.running_job=False;redraw=True
                elif typ=='error':self.detail='Ошибка: '+str(value);redraw=True
                elif typ=='show':self.deiconify();self.lift();self.focus_force();redraw=True
                elif typ=='connect':self._start_connect()
                elif typ=='disconnect':self._start_disconnect()
                elif typ=='quit':self.quit_app()
                elif typ=='diagnostics':
                    self.last_results=value
                    try:record_scan(value)
                    except OSError:pass
                    self.detail='Диагностика выполнена: '+datetime.now().strftime('%H:%M:%S')
                    redraw=True
        except queue.Empty:pass
        if redraw:self._draw()
        self.after(180,self._poll)

    def _health_check(self):
        if self._quitting:return
        state=self.controller.runtime_health()
        if state != self._last_health:
            self._last_health=state
            if state.overall=='partial':self.detail=state.detail
            self._draw()
        self.after(3500,self._health_check)

    def hide_to_tray(self):
        self.settings.window_geometry=self.geometry()
        save_settings(self.settings)
        if self._tray_ready:
            self.withdraw()
        else:
            self.iconify()  # Never silently kill a connection because tray failed.

    def quit_app(self):
        if self._quitting:return
        self._quitting=True
        self.settings.window_geometry=self.geometry()
        save_settings(self.settings)
        # A real application exit stops local processes and restores changed DNS,
        # but does NOT alter desired_enabled; explicit Disconnect alone does that.
        def stop():
            try:self.controller.disconnect(remember=False)
            except Exception:pass
            self.events.put(('exit_done',None))
        threading.Thread(target=stop,daemon=True).start()
        self.after(250,self._check_exit)

    def _check_exit(self):
        try:
            while True:
                name,_=self.events.get_nowait()
                if name=='exit_done':self._quit_now(skip_disconnect=True);return
        except queue.Empty:pass
        self.after(250,self._check_exit)

    def _quit_now(self,*,skip_disconnect=False):
        self._quitting=True
        if self._tray:
            try:self._tray.stop()
            except Exception:pass
        self.destroy()


def main():
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--tg-worker',action='store_true')
    parser.add_argument('--port',type=int,default=1443)
    parser.add_argument('--minimized',action='store_true')
    parser.add_argument('--self-test',action='store_true')
    parser.add_argument('--elevation-retry',action='store_true')
    parser.add_argument('--uninstall-cleanup',action='store_true')
    args=parser.parse_args()
    if args.uninstall_cleanup:
        # Called elevated by the uninstaller to remove per-user persistence.
        try: configure_startup(False)
        except Exception: pass
        try:
            from .geohide import restore_dns
            restore_dns()
        except Exception: pass
        return
    if args.self_test:
        if not asset('VORQELI-logo.png').is_file():
            raise RuntimeError('Logo asset missing')
        from .bundled_telegram import proxy_available
        if not proxy_available():
            raise RuntimeError('Bundled Telegram proxy is missing')
        import pystray._win32  # Windows tray backend must be included in the build.
        return
    if args.tg_worker:
        from .bundled_telegram import start_worker
        start_worker(args.port)
        return
    if os.name=='nt':
        # Single instance: opening a second copy cannot start duplicate drivers.
        import ctypes
        kernel=ctypes.windll.kernel32
        kernel.CreateMutexW.argtypes=(ctypes.c_void_p,ctypes.c_bool,ctypes.c_wchar_p)
        kernel.CreateMutexW.restype=ctypes.c_void_p
        kernel.ReleaseMutex.argtypes=(ctypes.c_void_p,)
        kernel.CloseHandle.argtypes=(ctypes.c_void_p,)
        kernel.WaitForSingleObject.argtypes=(ctypes.c_void_p,ctypes.c_uint)
        kernel.WaitForSingleObject.restype=ctypes.c_uint
        ctypes.windll.user32.FindWindowW.restype=ctypes.c_void_p
        mutex=kernel.CreateMutexW(None,True,'Local\\VORQELI-Connect-Instance')
        if kernel.GetLastError()==183:
            if args.elevation_retry:
                # Wait for the unelevated instance to release its mutex.
                # Without this the new elevated app can exit before UAC handoff completes.
                wait_result=kernel.WaitForSingleObject(mutex,15000)
                if wait_result not in (0, 0x80):
                    kernel.CloseHandle(mutex)
                    return
            else:
                hwnd=ctypes.windll.user32.FindWindowW(None,'VORQELI Connect')
                if hwnd:
                    ctypes.windll.user32.ShowWindow(hwnd,9)  # SW_RESTORE
                    ctypes.windll.user32.SetForegroundWindow(hwnd)
                kernel.CloseHandle(mutex)
                return
    app=ConnectApp(minimized=args.minimized)
    app.mainloop()
    if os.name=='nt':
        try:
            kernel.ReleaseMutex(mutex)
            kernel.CloseHandle(mutex)
        except Exception:pass

if __name__=='__main__':main()
