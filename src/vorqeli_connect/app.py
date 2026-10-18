"""VORQELI Connect: single-button desktop window, polished glass-like UI and tray.

The application intentionally keeps the main process alive while hidden in tray.
Only user-initiated Disconnect clears the persisted desired connection state.
"""
from __future__ import annotations
import json
import os
import queue
import sys
import threading
import time
import tkinter as tk
import webbrowser
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, filedialog
from PIL import Image, ImageTk

from .config import APP_DIR, load_settings, save_settings
from .diagnostics import check_all
from .network_audit import run_dns_audit, format_dns_audit
from .event_log import record_event, recent_events
from .geohide import INFO_PAGE, STATE_FILE
from .geohide_doh import DOH_STATE_FILE, restore_geo_dns
from .history import record_scan, load_history
from .log_tools import tail_log, redact_secrets
from .startup import is_admin, relaunch_elevated, configure_startup
from .unified import UnifiedController, ConnectionReport
from .recovery import RecoveryPolicy
from .engine_adapters import proxy_link
from .tray_assets import tray_icon
from .support_report import build_report
from .ui_copy import main_status, module_caption, connection_disclaimer
from .ui_navigation import cycle_focus, reveal_target
from .windows_chrome import apply_windows_chrome
from .update_checker import check_for_update, download_verified, UpdateError, Release

from .visual_design import (INK as BG, FG as LIGHT, SECONDARY as MUTED,
                            VIOLET as LAV, BLUE as CYAN, AQUA as MINT,
                            ROSE as PINK, FG, SECONDARY, DIM, VIOLET, AQUA,
                            tint_status, fit_line, button_skin)

from . import __version__ as VERSION



def asset(name: str) -> Path:
    """Resolve bundled images or source-tree assets after pip installation."""
    frozen_root = getattr(sys, '_MEIPASS', None)
    if frozen_root is not None:
        return Path(frozen_root) / 'assets' / name
    source_root = Path(__file__).resolve().parents[2]
    # CI and developer installs import from site-packages while the current
    # directory remains the VORQELI checkout. A PyInstaller build uses MEIPASS.
    for root in (source_root, Path.cwd()):
        candidate = root / 'assets' / name
        if candidate.is_file():
            return candidate
    return source_root / 'assets' / name


class ConnectApp(tk.Tk):
    def __init__(self, *, minimized=False):
        super().__init__()
        self.settings = load_settings()
        self.title('VORQELI Connect')
        self.configure(bg=BG)
        from .window_state import safe_geometry
        self.geometry(safe_geometry(self.settings.window_geometry,
                                    self.winfo_screenwidth(),self.winfo_screenheight()))
        from .window_state import minimum_window_size
        self.minsize(*minimum_window_size(self.winfo_screenwidth(),self.winfo_screenheight()))
        self.events = queue.Queue()
        self.controller = UnifiedController(self.settings, emit=lambda typ, data:self.events.put((typ,data)))
        self.connected_text = 'Не подключено'
        self.detail = (self.settings.telegram_secret_error or 'Готов к работе · одно нажатие для запуска')
        self.selected_page = 'Главная'
        self.running_job = False
        self._jobs = 0
        self._disconnecting = False
        self.recovery = RecoveryPolicy()
        self._startup_request_id=0
        self._startup_sync_lock=threading.Lock()
        self._quitting = False
        self._tray = None
        self._tray_ready = False
        self._start_minimized = bool(minimized)
        self._resize_job = None
        self._canvas_bg = None
        self._logo_tk = None
        self._widgets = []
        self._button_images = []
        self._controls = []
        self._focused_control_index = None
        self._last_health = None
        self._update_busy = False
        self._dns_audit_window = None
        self._dns_audit_text = None
        self._dns_audit_busy = False
        previous = load_history()
        self.last_results = list(previous[-1]['results'].items()) if previous else []
        # A compact/150%-scaled display exposes scrollbars rather than
        # cutting off the settings, sidebar, or connect action.
        self.viewport = tk.Frame(self, bg=BG, bd=0, highlightthickness=0)
        self.viewport.pack(fill='both', expand=True)
        self.viewport.rowconfigure(0, weight=1)
        self.viewport.columnconfigure(0, weight=1)
        self.canvas = tk.Canvas(self.viewport, bg=BG, highlightthickness=0, bd=0,
                                takefocus=1)
        self.canvas.grid(row=0, column=0, sticky='nsew')
        self.vscroll = tk.Scrollbar(self.viewport, orient='vertical', command=self.canvas.yview,
                                    bg='#343252', activebackground='#7563A9',
                                    troughcolor='#111527', relief='flat', bd=0, width=12)
        self.hscroll = tk.Scrollbar(self.viewport, orient='horizontal', command=self.canvas.xview,
                                    bg='#343252', activebackground='#7563A9',
                                    troughcolor='#111527', relief='flat', bd=0, width=12)
        self.canvas.configure(xscrollcommand=self.hscroll.set, yscrollcommand=self.vscroll.set)
        self._scrollbars_visible = (False, False)
        self.canvas.bind('<Configure>', self._resize)
        self.canvas.bind('<MouseWheel>', self._scroll_wheel)
        self.canvas.bind('<Shift-MouseWheel>', self._scroll_wheel)
        self.canvas.bind('<Button-4>', self._scroll_wheel)
        self.canvas.bind('<Button-5>', self._scroll_wheel)
        self.bind('<Tab>', self._keyboard_tab)
        self.bind('<Shift-Tab>', self._keyboard_shift_tab)
        self.bind('<ISO_Left_Tab>', self._keyboard_shift_tab)
        self.bind('<Return>', self._keyboard_activate)
        self.bind('<space>', self._keyboard_activate)
        self.bind('<Right>', self._keyboard_right)
        self.bind('<Left>', self._keyboard_left)
        self.bind('<Escape>', lambda e:self.hide_to_tray())
        self.bind('<Control-comma>',lambda e:self._page('Настройки'))
        self.bind('<Control-d>',lambda e:self._page('Диагностика'))
        for ix, page in enumerate(('Главная','Диагностика','История','Настройки','О проекте'),start=1):
            self.bind(f'<Alt-Key-{ix}>',lambda e,p=page:self._page(p))
        self.bind('<F5>',lambda e:self._diagnose())
        self.bind('<Control-Return>',lambda e:self._start_disconnect() if self.settings.desired_enabled else self._start_connect())
        self.protocol('WM_DELETE_WINDOW', self.hide_to_tray)
        self._launch_tray()
        self.after(220, self._poll)
        self.after(800, self._health_check)
        self.after(1000, self._register_autostart)
        self.after(150, self._draw)
        self.after(350, lambda: apply_windows_chrome(self))
        if minimized:
            # Do not hide completely until the tray backend confirms readiness.
            # If tray startup fails, keep a visible taskbar icon instead.
            self.after(950, self._minimize_after_startup)
        if self.settings.desired_enabled:
            self.after(1300, self._start_connect)
        elif STATE_FILE.exists() or DOH_STATE_FILE.exists():
            self.detail = 'Найдены сохранённые настройки GeoHide · откройте настройки для восстановления'
            self.after(1200, self._draw)
        if self.settings.first_launch_notice and not minimized:
            self.after(1250, self._first_notice)

    def _register_autostart(self):
        """Register even when user deliberately left the connection OFF.

        Uses a per-user registry fallback where elevated task is not permitted.
        Task creation/registry I/O never blocks the Tk UI thread.
        """
        if self._quitting or os.name != 'nt' or not self.settings.launch_at_startup:
            return
        def configure():
            try:
                mode = configure_startup(True)
                if mode == 'registry' and (self.settings.connect_dpi or self.settings.connect_dns):
                    self.events.put(('progress',
                        'Автозапуск включён. Для DPI/GeoHide при следующем входе могут понадобиться права администратора.'))
            except Exception as exc:
                self.events.put(('progress',f'Не удалось настроить автозапуск: {exc}'))
        threading.Thread(target=configure,daemon=True,name='StartupRegistration').start()

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
            image = tray_icon(Image.open(asset('VORQELI-logo.png')).convert('RGBA'), 'off')
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
            if os.name == 'nt':
                self.detail=f'Трей недоступен: {exc}'

    def _run_tray(self):
        try:
            # pystray's setup callback runs only after the icon is registered.
            # Never claim the tray exists before the platform backend is ready.
            self._tray.run(setup=lambda icon: self.events.put(('tray_ready', None)))
        except Exception as exc:
            self.events.put(('progress',f'Не удалось создать трей: {exc}'))
        finally:
            self.events.put(('tray_stopped', None))

    def _minimize_after_startup(self):
        if not self._start_minimized or self._quitting:
            return
        if self._tray_ready:
            self.withdraw()
            self._start_minimized = False
        else:
            # Still accessible through Windows taskbar if tray is unavailable.
            self.iconify()

    def _resize(self, event):
        if event.widget is not self: return
        if self._resize_job: self.after_cancel(self._resize_job)
        self._resize_job=self.after(170,self._draw)

    def _scroll_wheel(self, event):
        if getattr(event, 'num', 0) == 4:
            direction = -1
        elif getattr(event, 'num', 0) == 5:
            direction = 1
        else:
            delta = getattr(event, 'delta', 0)
            direction = -1 if delta > 0 else 1 if delta < 0 else 0
        if event.state & 0x0001:
            self.canvas.xview_scroll(direction * 3, 'units')
        else:
            self.canvas.yview_scroll(direction * 3, 'units')
        return 'break'

    def _sync_scrollbars(self, logical_width: int, logical_height: int):
        """Only show scroll chrome when a compact window needs it."""
        viewport_width = max(1, self.canvas.winfo_width())
        viewport_height = max(1, self.canvas.winfo_height())
        wanted_vertical = logical_height > viewport_height + 3
        wanted_horizontal = logical_width > viewport_width + 3
        if (wanted_vertical, wanted_horizontal) != self._scrollbars_visible:
            if wanted_vertical:
                self.vscroll.grid(row=0, column=1, sticky='ns')
            else:
                self.vscroll.grid_remove()
            if wanted_horizontal:
                self.hscroll.grid(row=1, column=0, sticky='ew')
            else:
                self.hscroll.grid_remove()
            self._scrollbars_visible = (wanted_vertical, wanted_horizontal)
        self.canvas.configure(scrollregion=(0, 0, logical_width, logical_height))

    def _register_control(self, bounds, callback, label):
        """Only enabled controls are in the keyboard tab cycle."""
        index = len(self._controls)
        self._controls.append((tuple(bounds), callback, label))
        return index

    def _render_focus(self):
        self.canvas.delete('keyboard_focus_ring')
        index = self._focused_control_index
        if index is None or not 0 <= index < len(self._controls):
            return
        bounds, _, _ = self._controls[index]
        x1, y1, x2, y2 = bounds
        self.canvas.create_polygon(self._rounded_coords(x1-3,y1-3,x2+3,y2+3,15),
                                   smooth=True, splinesteps=12, fill='',
                                   outline='#E8D9FF', width=3,
                                   tags=('keyboard_focus_ring',))

    def _focus_control(self, index: int):
        if not 0 <= index < len(self._controls):
            return
        self._focused_control_index = index
        self.canvas.focus_set()
        bounds = self._controls[index][0]
        full_w, full_h = self._logical_size
        vw, vh = self.canvas.winfo_width(), self.canvas.winfo_height()
        ox = self.canvas.canvasx(0)
        oy = self.canvas.canvasy(0)
        nx, ny = reveal_target(bounds, (vw,vh), (full_w,full_h),
                               (int(ox),int(oy)))
        if full_w > vw:
            self.canvas.xview_moveto(nx / full_w)
        if full_h > vh:
            self.canvas.yview_moveto(ny / full_h)
        self._render_focus()

    def _keyboard_tab(self, event):
        index = cycle_focus(self._focused_control_index, len(self._controls),
                            backward=bool(event.state & 0x0001))
        if index is not None:
            self._focus_control(index)
        return 'break'

    def _keyboard_shift_tab(self, event):
        index = cycle_focus(self._focused_control_index, len(self._controls), backward=True)
        if index is not None:
            self._focus_control(index)
        return 'break'

    def _keyboard_right(self, event):
        return self._keyboard_tab(event)

    def _keyboard_left(self, event):
        return self._keyboard_shift_tab(event)

    def _keyboard_activate(self, event):
        index = self._focused_control_index
        if index is not None and 0 <= index < len(self._controls):
            self._controls[index][1]()
            self._render_focus()
            return 'break'

    def _mouse_activate(self, index: int):
        if 0 <= index < len(self._controls):
            self._focus_control(index)
            self._controls[index][1]()
            self._render_focus()

    def _text(self,x,y,value,size=12,color=LIGHT,anchor='nw',weight='normal',width=0,**kwargs):
        return self.canvas.create_text(x,y,text=value,fill=color,anchor=anchor,
            font=('Segoe UI',size,weight),width=width,**kwargs)

    def _pill(self, x, y, label, *, foreground=FG, background='#29314D',
              fontsize=9, height=26, width=None):
        if width is None:
            width=max(74,min(272,round(18+len(label)*fontsize*.66)))
        self.canvas.create_oval(x,y,x+height,y+height,fill=background,outline='')
        self.canvas.create_oval(x+width-height,y,x+width,y+height,fill=background,outline='')
        self.canvas.create_rectangle(x+height//2,y,x+width-height//2,y+height,
                                     fill=background,outline='')
        self._text(x+width/2,y+height/2,label,fontsize,foreground,anchor='center',weight='bold')
        return width

    def _place_button(self,x,y,label,callback,*,accent=False,width=None,size=10,
                      height=45,fill=None,disabled=False):
        """Accessible-looking canvas-native rounded button, without square Tk chrome.

        All button items share a tag for hit testing, including label and border.
        Disabled buttons have no click binding.
        """
        if width is None:
            width=max(120,min(264,int(len(label)*size*.7+46)))
        elif width < 40:  # compatibility with previous Tk character widths
            width=max(110,int(width*11+30))
        foreground='#0B0921' if accent else FG
        if disabled:
            foreground=DIM
        tag=f'ctl_{getattr(self,"_control_serial",0)}'
        self._control_serial=getattr(self,'_control_serial',0)+1
        normal=ImageTk.PhotoImage(button_skin(width,height,accent=accent,disabled=disabled))
        hot=ImageTk.PhotoImage(button_skin(width,height,accent=accent,hover=True))
        self._button_images.extend((normal,hot))
        body=self.canvas.create_image(x,y,image=normal,anchor='nw',tags=(tag,))
        self._text(x+width/2,y+height/2,label,size,foreground,anchor='center',
                   weight='bold',tags=(tag,))
        if not disabled:
            index = self._register_control((x,y,x+width,y+height),callback,label)
            self.canvas.tag_bind(tag,'<Enter>',lambda e,i=body,v=hot:(self.canvas.itemconfigure(i,image=v),self.canvas.configure(cursor='hand2')))
            self.canvas.tag_bind(tag,'<Leave>',lambda e,i=body,v=normal:(self.canvas.itemconfigure(i,image=v),self.canvas.configure(cursor='')))
            self.canvas.tag_bind(tag,'<Button-1>',lambda e,n=index:self._mouse_activate(n))
        return body

    @staticmethod
    def _rounded_coords(x1,y1,x2,y2,r):
        """Polygon with enough repeated corners for stable Tk smoothing."""
        return [x1+r,y1,x2-r,y1,x2,y1,x2,y1+r,x2,y2-r,x2,y2,
                x2-r,y2,x1+r,y2,x1,y2,x1,y2-r,x1,y1+r,x1,y1]

    def _nav(self,name,y,marker):
        active=name==self.selected_page
        x=33
        color='#343253' if active else '#1B2239'
        tag=f'nav_{name}'
        shape=self.canvas.create_polygon(self._rounded_coords(x,y,x+196,y+46,12),
                                         smooth=True,splinesteps=12,fill=color,
                                         outline='#5C518E' if active else '',width=1,tags=(tag,))
        self._text(x+16,y+23,marker,15,VIOLET if active else DIM,anchor='w',tags=(tag,))
        self._text(x+48,y+23,name,11,FG if active else SECONDARY,anchor='w',
                   weight='bold' if active else 'normal',tags=(tag,))
        self.canvas.tag_bind(tag,'<Enter>',lambda e,i=shape,a=active:self.canvas.itemconfigure(i,fill=color if a else '#2A324C'))
        self.canvas.tag_bind(tag,'<Leave>',lambda e,i=shape,c=color:self.canvas.itemconfigure(i,fill=c))
        index = self._register_control((x,y,x+196,y+46),lambda n=name:self._page(n),name)
        self.canvas.tag_bind(tag,'<Button-1>',lambda e,n=index:self._mouse_activate(n))

    def _page(self,name):
        if name not in ('Главная','Диагностика','История','Настройки','О проекте'):
            return
        if name != self.selected_page:
            self._focused_control_index = None
        self.selected_page=name
        self._draw()

    def _draw(self):
        if self._quitting or not self.winfo_exists():return
        from .visual_design import scene,layout
        w=max(1060,self.canvas.winfo_width());h=max(710,self.canvas.winfo_height())
        self._logical_size = (w, h)
        self._widgets=[]
        self._button_images=[]
        self._controls=[]
        self._control_serial=0
        self.canvas.delete('all')
        self.canvas.configure(cursor='')
        geo=layout(w,h)
        x,right=geo['left'],geo['right']
        self._canvas_bg=ImageTk.PhotoImage(scene(w,h,self.selected_page).convert('RGB'))
        self.canvas.create_image(0,0,image=self._canvas_bg,anchor='nw')
        # Sidebar identity.
        try:
            logo=Image.open(asset('VORQELI-logo.png')).convert('RGBA').resize((78,78),Image.Resampling.LANCZOS)
            self._logo_tk=ImageTk.PhotoImage(logo)
            self.canvas.create_image(40,34,image=self._logo_tk,anchor='nw')
        except Exception:
            self._text(51,44,'V',34,VIOLET,weight='bold')
        self._text(45,120,'VORQELI',20,FG,weight='bold')
        self._text(46,151,'C O N N E C T',9,SECONDARY,weight='bold')
        self.canvas.create_line(35,188,229,188,fill='#3D425F',width=1)
        self._text(46,204,'РАЗДЕЛЫ',9,DIM,weight='bold')
        for j,(name,glyph) in enumerate([
            ('Главная','⌂'),('Диагностика','◎'),('История','◷'),
            ('Настройки','⚙'),('О проекте','ⓘ'),
        ]):
            self._nav(name,230+j*55,glyph)
        self.canvas.create_line(35,h-123,229,h-123,fill='#3D425F')
        self.canvas.create_oval(46,h-97,54,h-89,fill=AQUA,outline='')
        self._text(65,h-103,'Локальное приложение',10,SECONDARY)
        self._text(46,h-68,'VORQELI  /  '+VERSION,9,DIM,weight='bold')
        # Compact global chrome (not intrusive fullscreen toolbar).
        self._text(x,43,'VORQELI   /   NETWORK CONTROL',10,VIOLET,weight='bold')
        self._pill(right-176,37,'●  WINDOWS',foreground=SECONDARY,background='#242944',width=134)
        if self.selected_page=='Главная':self._draw_home(x,right,h)
        elif self.selected_page=='Диагностика':self._draw_diagnostics(x,right,h)
        elif self.selected_page=='История':self._draw_history(x,right,h)
        elif self.selected_page=='Настройки':self._draw_settings(x,right,h)
        else:self._draw_about(x,right,h)
        self._sync_scrollbars(w,h)
        self._render_focus()

    def _draw_header(self,x,right,title,subtitle,*,eyebrow='VORQELI / CONTROL'):
        self._text(x+30,137,eyebrow,10,VIOLET,weight='bold')
        self._text(x+29,170,title,27,FG,weight='bold')
        self._text(x+31,222,subtitle,11,SECONDARY,width=right-x-85)

    def _draw_home(self,x,right,h):
        report=self.controller.status()
        active=self.settings.desired_enabled
        state=report.overall
        busy=self.running_job or self._disconnecting
        headline=main_status(state,busy,self._disconnecting)
        accent=tint_status(state)
        self.canvas.create_oval(x+34,141,x+46,153,fill=accent,outline='')
        self._text(x+58,139,'СТАТУС ПОДКЛЮЧЕНИЯ',10,VIOLET,weight='bold')
        self._text(x+31,174,headline,26,FG,weight='bold')
        self._text(x+31,225,fit_line(self.detail or connection_disclaimer(state),count=110),10,SECONDARY,width=right-x-360)
        self._pill(x+31,286,
            ('●  ВЫПОЛНЯЕТСЯ' if busy else '●  АВТОВОССТАНОВЛЕНИЕ ВКЛ.' if active else '●  ОЖИДАНИЕ'),
            foreground=accent,background='#252C47',width=238)
        # Allow cancellation while a pending connect or download runs.
        # Disconnect persists OFF intent immediately and then stops engines.
        self._place_button(right-267,172,
                           ('ОТКЛЮЧЕНИЕ…' if self._disconnecting else
                            'ОТМЕНИТЬ  ×' if active and busy else
                            'ОТКЛЮЧИТЬ' if active else
                            'ПОДКЛЮЧИТЬ  →'),
                           self._start_disconnect if active else self._start_connect,
                           accent=not active,width=236,height=59,size=12,
                           disabled=self._disconnecting or (busy and not active))
        self._text(right-149,257,
                   'Включены: '+str(sum((self.settings.connect_dpi,self.settings.connect_telegram,self.settings.connect_dns)))+'/3',
                   10,SECONDARY,anchor='center')
        dpi_caption = ('Smart DPI · ' + self.controller.active_dpi_mode.upper() + ' (HTTPS-проба)'
                       if self.settings.dpi_mode == 'auto' and self.controller.active_dpi_mode
                       else 'Обход сетевых ограничений')
        cards=[('DPI / WINWS','01','dpi',self.settings.connect_dpi,dpi_caption),
               ('TELEGRAM','02','telegram',self.settings.connect_telegram,'Локальный MTProto-прокси'),
               ('GEOHIDE DNS','03','dns',self.settings.connect_dns,'Профиль системного DNS')]
        cw=(right-x-28)//3
        for i,(title,num,key,enabled,description) in enumerate(cards):
            sx=x+i*(cw+14)
            actual=getattr(report,key)
            color=tint_status(actual) if enabled else DIM
            self._text(sx+22,388,num,10,VIOLET,weight='bold')
            self._text(sx+22,418,title,13,FG,weight='bold')
            self._text(sx+22,453,description,10,SECONDARY,width=cw-38)
            status=('●  ' if enabled and actual=='on' else '○  ') + module_caption(actual,enabled)
            self._text(sx+22,504,status,9,color,weight='bold')
        y=589
        self._text(x+26,y,'ПОДКЛЮЧЕНИЕ В ОДНО КАСАНИЕ',11,VIOLET,weight='bold')
        self._text(x+26,y+31,'Крестик свернёт окно в трей. Работа модулей продолжится.',11,FG,
                   width=max(300,right-x-260))
        retry=self.recovery.status(time.monotonic())
        if active and retry.exhausted:
            caption='Автовосстановление приостановлено: исчерпаны 3 попытки.'
        elif active and retry.next_in_seconds is not None and report.overall in ('partial','error'):
            caption=f'Повтор подключения через {int(retry.next_in_seconds+.99)} с  ·  {retry.attempts}/{retry.max_attempts}'
        else:
            caption='При следующем запуске Windows восстановится выбранный режим.'
        self._text(x+26,y+62,caption,9,SECONDARY,width=max(320,right-x-250))
        self._place_button(right-380,h-87,'Диагностика',lambda:self._page('Диагностика'),width=166,height=42,size=10)
        self._place_button(right-198,h-87,'Настройки  →',lambda:self._page('Настройки'),width=167,height=42,size=10)

    def _draw_diagnostics(self,x,right,h):
        self._draw_header(x,right,'Диагностика сети',
                          'Проверка доступности сервисов по HTTPS. Не подтверждает работу обхода.',
                          eyebrow='ИНСТРУМЕНТЫ  /  ДИАГНОСТИКА')
        # Five controls fit even at the minimum logical width (1060 px).
        self._place_button(x+30,268,'ПРОВЕРИТЬ  →',self._diagnose,
                           accent=True,width=165,height=51,size=10,disabled=self.running_job)
        self._place_button(x+204,268,'ЖУРНАЛЫ',self._show_engine_logs,
                           width=118,height=51,size=10)
        self._place_button(x+331,268,'ЭКСПОРТ JSON',self._export_diagnostics,
                           width=145,height=51,size=10,disabled=not bool(self.last_results))
        self._place_button(x+485,268,'ОТЧЁТ',self._export_support,
                           width=98,height=51,size=9)
        self._place_button(x+592,268,'DNS / HOSTS',self._show_dns_audit,
                           width=133,height=51,size=10)
        self._text(x+29,385,'ПОСЛЕДНИЕ ПРОВЕРКИ',11,VIOLET,weight='bold')
        results=self.last_results or [('Discord','Не проверено'),('YouTube','Не проверено'),
                                      ('Telegram','Не проверено'),('GitHub','Не проверено')]
        for j,(name,status) in enumerate(results[:5]):
            y=427+j*49
            self._text(x+36,y,str(name),12,FG,weight='bold')
            c=AQUA if status=='Доступен' else ROSE if status=='Нет ответа' else SECONDARY
            self._text(right-49,y,fit_line(status,count=44),11,c,anchor='ne')
            if j<len(results)-1:self.canvas.create_line(x+30,y+35,right-30,y+35,fill='#343B56')
        self._text(x+33,h-61,'Подробности проверок сохраняются локально в истории.',10,SECONDARY)

    def _draw_history(self,x,right,h):
        self._draw_header(x,right,'История действий',
                          'Диагностика и последние события хранятся только на вашем устройстве.',
                          eyebrow='ИНСТРУМЕНТЫ  /  ЖУРНАЛ')
        self._text(x+31,387,'ПОСЛЕДНИЕ СОБЫТИЯ',11,VIOLET,weight='bold')
        entries=recent_events(limit=10)[:7]  # recent_events already returns newest first.
        if not entries:
            self._text(x+34,439,'Здесь появятся подключения, проверки и действия.',11,SECONDARY)
        for j,event in enumerate(entries):
            y=428+j*35
            t=str(event.get('timestamp',''))[:16].replace('T',' ')
            label=fit_line(event.get('message',''),count=78)
            self._text(x+33,y,t,9,DIM)
            self._text(x+178,y,label,10,FG,width=max(150,right-x-240))
        self._text(x+32,h-57,f'Диагностических проверок: {len(load_history())}',10,SECONDARY)

    def _toggle(self,x,y,label,value,callback,*,info='',width=244):
        self._text(x,y,label,12,FG,weight='bold')
        if info:self._text(x,y+25,info,9,SECONDARY,width=width)
        self._place_button(x+width+22,y-4,'ВКЛ' if value else 'ВЫКЛ',callback,
                           accent=value,size=9,width=83,height=40)

    def _draw_settings(self,x,right,h):
        self._draw_header(x,right,'Настройки приложения',
                          'Один переключатель управляет выбранными компонентами.',
                          eyebrow='VORQELI  /  ПАРАМЕТРЫ')
        span=right-x
        split=x+int(span*.56)
        self._text(x+30,272,'СТРАТЕГИЯ DPI',10,VIOLET,weight='bold')
        self._text(x+30,297,'АВТО проверяет HTTPS; это не гарантия обхода.',10,SECONDARY)
        for i,(mode,label) in enumerate((('auto','АВТО'),('fake','FAKE'),('multisplit','MULTISPLIT'))):
            self._place_button(right-459+i*148,268,label,
                               lambda m=mode:self._set_dpi_mode(m),
                               accent=self.settings.dpi_mode==mode,width=136,height=44,size=10,
                               disabled=self.running_job)
        self._text(x+28,390,'КОМПОНЕНТЫ',10,VIOLET,weight='bold')
        self._text(split,390,'ПОВЕДЕНИЕ',10,VIOLET,weight='bold')
        for j,(title,key,subtitle) in enumerate([
            ('DPI / Flowseal','connect_dpi','WinWS · обход DPI'),
            ('Telegram MTProto','connect_telegram','Локальный прокси Telegram Desktop'),
            ('GeoHide DNS','connect_dns',
             'Зашифрованный DoH' if self.settings.dns_mode=='doh' else 'Системный IPv4 DNS'),
        ]):
            self._toggle(x+31,421+j*66,title,getattr(self.settings,key),
                         lambda k=key:self._toggle_setting(k),info=subtitle,
                         width=int(span*.55)-145)
        # GeoHide transport belongs to the left component panel, not to the
        # header: keep glass-card borders unobstructed at common window sizes.
        self._text(x+31,602,'GEOHIDE · ТРАНСПОРТ DNS',10,VIOLET,weight='bold')
        self._text(x+31,622,'DoH требует поддержки Windows, без UDP fallback.',9,SECONDARY)
        for j,(mode,label) in enumerate((('plain','IPv4 DNS'),('doh','DoH · HTTPS'))):
            self._place_button(x+31+j*151,640,label,
                               lambda m=mode:self._set_dns_mode(m),
                               accent=self.settings.dns_mode==mode,width=139,height=37,size=9,
                               disabled=self.running_job or self.settings.desired_enabled)
        self._toggle(split,421,'Автозапуск Windows',self.settings.launch_at_startup,
                     lambda:self._toggle_setting('launch_at_startup'),
                     info='При входе восстановить выбранный режим',width=int(span*.44)-141)
        self._place_button(split,515,'ВОССТАНОВИТЬ DNS',self._restore_dns,
                           width=int(span*.39),height=43,size=9)
        self._place_button(split,575,'ОТКРЫТЬ В TELEGRAM  ↗',self._open_telegram_proxy,
                           width=int(span*.39),height=43,size=9)
        # No overlapping footer: the GeoHide transport controls must remain
        # unobstructed at the supported 710px logical minimum height.

    def _draw_about(self,x,right,h):
        self._draw_header(x,right,'О приложении',
                          'Простой центр управления подключениями, без регистрации и телеметрии.',
                          eyebrow='VORQELI  /  INFORMATION')
        self._text(x+32,390,'VORQELI CONNECT',16,FG,weight='bold')
        self._pill(right-150,383,'v'+VERSION,width=113,foreground=VIOLET,background='#292846')
        for j,(label,value) in enumerate([
            ('Платформа','Windows 10 / 11'),
            ('DPI','Flowseal / zapret-discord-youtube'),
            ('Telegram','Flowseal / tg-ws-proxy'),
            ('DNS','GeoHide · сторонний DNS-провайдер'),
            ('Релиз','Preview · совместная работа требует проверки'),
        ]):
            y=445+j*38
            self._text(x+33,y,label,10,SECONDARY)
            self._text(x+165,y,value,11,FG,width=max(120,right-x-218))
        self._place_button(x+30,h-81,'ИСХОДНЫЙ КОД  ↗',
                           lambda:webbrowser.open('https://github.com/Zeihos/VORQELI'),
                           width=202,height=43,size=10)
        self._place_button(x+248,h-81,'GEOHIDE  ↗',lambda:webbrowser.open(INFO_PAGE),
                           width=143,height=43,size=10)
        self._place_button(x+408,h-81,'ПРОВЕРИТЬ ОБНОВЛЕНИЯ',self._check_updates,
                           width=228,height=43,size=9,disabled=self._update_busy)

    def _check_updates(self):
        """Explicit user action: check Releases without blocking Tk's UI."""
        if self._update_busy:
            return
        self._update_busy = True
        self.detail = 'Проверка официального GitHub Release…'
        self._draw()
        def worker():
            try:
                release = check_for_update(VERSION)
                self.events.put(('update_checked', release))
            except (UpdateError, OSError, ValueError) as exc:
                self.events.put(('update_error', str(exc)))
        threading.Thread(target=worker, daemon=True, name='UpdateCheck').start()

    def _download_update(self, release: Release):
        """Never execute or elevate a downloaded installer automatically."""
        self._update_busy = True
        self.detail = 'Скачивание установщика и проверка SHA-256…'
        self._draw()
        def worker():
            try:
                path = download_verified(release, APP_DIR / 'updates')
                self.events.put(('update_downloaded', path))
            except (UpdateError, OSError, ValueError) as exc:
                self.events.put(('update_error', str(exc)))
        threading.Thread(target=worker, daemon=True, name='UpdateDownload').start()

    def _export_support(self):
        """Generate a minimal report with no secrets, logs, paths, user IDs or IPs."""
        path=filedialog.asksaveasfilename(parent=self,defaultextension='.json',
                 filetypes=[('JSON','*.json')],initialfile='VORQELI-support.json')
        if not path:
            return
        try:
            payload=build_report(self.settings,self.controller.runtime_health(),self.last_results,VERSION)
            Path(path).write_text(json.dumps(payload,indent=2,ensure_ascii=False),encoding='utf-8')
            self.detail='Безопасный технический отчёт сохранён: '+Path(path).name
            self._draw()
        except OSError as exc:
            messagebox.showerror('Технический отчёт',str(exc),parent=self)

    def _set_dpi_mode(self, mode: str):
        if self.running_job or mode not in ('fake','multisplit','auto') or self.settings.dpi_mode==mode:
            return
        previous=self.settings.dpi_mode
        self.settings.dpi_mode=mode
        try:
            save_settings(self.settings)
        except OSError as exc:
            self.settings.dpi_mode=previous
            self.detail=f'Не удалось сохранить DPI-стратегию: {exc}'
        else:
            self.detail=('Стратегия '+mode.upper()+' сохранена. Переподключитесь, чтобы применить.'
                         if self.settings.desired_enabled else 'DPI-стратегия: '+mode.upper())
        self._draw()

    def _set_dns_mode(self, mode: str):
        if self.settings.desired_enabled:
            self.detail = 'Для смены транспорта DNS сначала нажмите «Отключиться». '
            self._draw()
            return
        if self.running_job or mode not in ('plain', 'doh') or self.settings.dns_mode == mode:
            return
        previous = self.settings.dns_mode
        self.settings.dns_mode = mode
        try:
            save_settings(self.settings)
        except OSError as exc:
            self.settings.dns_mode = previous
            self.detail = f'Не удалось сохранить режим GeoHide: {exc}'
        else:
            name = 'ЗАШИФРОВАННЫЙ DoH' if mode == 'doh' else 'IPv4 DNS'
            self.detail = ('Режим GeoHide: ' + name + '. Переподключитесь для применения.'
                           if self.settings.desired_enabled else 'GeoHide: ' + name)
        self._draw()

    def _export_diagnostics(self):
        """Export only scan results selected by the user; no settings/secrets."""
        if not self.last_results:
            return
        path=filedialog.asksaveasfilename(parent=self,defaultextension='.json',
                filetypes=[('JSON','*.json')],initialfile='VORQELI-diagnostics.json')
        if not path:
            return
        try:
            payload={'version': VERSION,'timestamp': datetime.now().astimezone().isoformat(),
                     'results': dict(self.last_results)}
            Path(path).write_text(json.dumps(payload,indent=2,ensure_ascii=False),encoding='utf-8')
            self.detail='Результаты сохранены: '+Path(path).name
            self._draw()
        except OSError as exc:
            messagebox.showerror('Экспорт диагностики',str(exc),parent=self)

    def _show_dns_audit(self):
        """Display DNS + hosts status within the application, never alter OS DNS."""
        if self._dns_audit_window is not None:
            try:
                if self._dns_audit_window.winfo_exists():
                    self._dns_audit_window.lift()
                    return
            except tk.TclError:
                pass
        dlg = tk.Toplevel(self)
        dlg.title('VORQELI · Проверка GeoHide и hosts')
        dlg.configure(bg='#111629')
        dlg.geometry('860x610')
        dlg.minsize(640, 430)
        dlg.transient(self)
        self._dns_audit_window = dlg
        header = tk.Frame(dlg, bg='#111629', padx=18, pady=15)
        header.pack(fill='x')
        tk.Label(header, text='GEOHIDE  /  DNS И HOSTS', bg='#111629', fg=VIOLET,
                 font=('Segoe UI', 12, 'bold')).pack(side='left')
        tk.Button(header, text='ПОВТОРИТЬ', command=self._start_dns_audit,
                  bg='#33395C', fg=FG, activebackground='#7965B6',
                  activeforeground=FG, bd=0, padx=16, pady=9,
                  font=('Segoe UI', 10, 'bold')).pack(side='right')
        body = tk.Frame(dlg, bg='#111629', padx=18, pady=10)
        body.pack(fill='both', expand=True)
        text = tk.Text(body, bg='#1B2238', fg=FG, insertbackground=FG,
                       selectbackground='#65569A', font=('Consolas', 11), wrap='word',
                       bd=0, padx=18, pady=16, state='disabled')
        text.pack(side='left', fill='both', expand=True)
        scrollbar = tk.Scrollbar(body, command=text.yview)
        scrollbar.pack(side='right', fill='y')
        text.configure(yscrollcommand=scrollbar.set)
        self._dns_audit_text = text
        self._set_dns_audit_text('Готовим проверку DNS и hosts…\nЭто не меняет настройки сети.')
        self._start_dns_audit()

    def _set_dns_audit_text(self, value: str) -> None:
        widget = self._dns_audit_text
        if widget is None:
            return
        try:
            if not widget.winfo_exists():
                return
            widget.configure(state='normal')
            widget.delete('1.0', 'end')
            widget.insert('1.0', value)
            widget.configure(state='disabled')
        except tk.TclError:
            pass

    def _start_dns_audit(self) -> None:
        if self._dns_audit_busy:
            return
        self._dns_audit_busy = True
        self._set_dns_audit_text('Проверяем системный DNS, hosts и ответы серверов GeoHide…\n'
                                 'Проверка может занять до 30 секунд.')
        def worker():
            try:
                result = format_dns_audit(run_dns_audit())
            except Exception as exc:
                result = 'Проверка прервана: ' + str(exc)
            self.events.put(('dns_audit', result))
        threading.Thread(target=worker, daemon=True, name='GeoHideAudit').start()

    def _show_engine_logs(self):
        """Read a bounded, redacted log; never copy Telegram secrets into the window."""
        dlg=tk.Toplevel(self)
        dlg.title('VORQELI · Журналы компонентов')
        dlg.configure(bg='#111629')
        dlg.geometry('880x550')
        dlg.minsize(640,400)
        dlg.transient(self)
        bar=tk.Frame(dlg,bg='#111629',pady=12,padx=18)
        bar.pack(fill='x')
        panel=tk.Frame(dlg,bg='#111629',padx=18,pady=10)
        panel.pack(fill='both',expand=True)
        text=tk.Text(panel,bg='#1B2238',fg=FG,insertbackground=FG,
                     selectbackground='#65569A',font=('Consolas',10),wrap='word',
                     bd=0,relief='flat',padx=18,pady=16,state='disabled')
        text.pack(side='left',fill='both',expand=True)
        scroll=tk.Scrollbar(panel,command=text.yview)
        scroll.pack(side='right',fill='y')
        text.configure(yscrollcommand=scroll.set)
        def view(name):
            logs={'DPI':APP_DIR/'dpi-engine.log','Telegram':APP_DIR/'telegram-engine.log'}
            path=logs[name]
            try:
                content=redact_secrets(tail_log(path,max_bytes=65536),self.settings.telegram_secret)
            except (ValueError,OSError) as exc:
                content='Не удалось прочитать журнал: '+str(exc)
            text.configure(state='normal')
            text.delete('1.0','end')
            text.insert('1.0',f'{name} / {path.name}\n'+'─'*60+'\n\n'+content)
            text.configure(state='disabled')
        for name in ('DPI','Telegram'):
            tk.Button(bar,text=name,command=lambda n=name:view(n),
                      bg='#33395C',fg=FG,activebackground='#7965B6',
                      activeforeground=FG,bd=0,relief='flat',padx=18,pady=9,
                      font=('Segoe UI',10,'bold'),cursor='hand2').pack(side='left',padx=(0,9))
        tk.Label(bar,text='Последние 64 КБ · секреты скрыты',bg='#111629',
                 fg=SECONDARY,font=('Segoe UI',10)).pack(side='right')
        view('DPI')

    def _open_telegram_proxy(self):
        try:
            webbrowser.open(proxy_link(self.settings.telegram_port,self.settings.telegram_secret))
        except ValueError:
            messagebox.showwarning('Telegram','Сначала подключите Telegram-прокси',parent=self)

    def _toggle_setting(self,key):
        previous=getattr(self.settings,key)
        target=not previous
        setattr(self.settings,key,target)
        try:
            save_settings(self.settings)
        except OSError as exc:
            setattr(self.settings,key,previous)
            self.detail=f'Настройка не сохранена: {exc}'
            self._draw()
            return
        if key=='launch_at_startup' and os.name=='nt':
            # Windows Task Scheduler can block for seconds: never call it on the Tk thread.
            self._startup_request_id+=1
            request=self._startup_request_id
            def apply():
                with self._startup_sync_lock:
                    if request != self._startup_request_id:
                        return
                    try:
                        configure_startup(target)
                        self.events.put(('progress','Автозапуск Windows обновлён.'))
                    except Exception as exc:
                        self.events.put(('startup_error',(request,target,str(exc))))
            threading.Thread(target=apply,daemon=True,name='StartupSettings').start()
            self.detail='Сохраняем настройки автозапуска Windows…'
        elif self.settings.desired_enabled:
            self.detail='Настройка сохранена. Для применения переподключитесь.'
        else:
            self.detail='Настройка сохранена.'
        self._draw()

    def _begin_job(self) -> None:
        self._jobs += 1
        self.running_job = True

    def _start_connect(self, *, automatic: bool = False):
        if self._quitting or self.running_job or self._disconnecting:
            return
        if self.settings.connect_telegram and self.settings.telegram_secret_error and not automatic:
            choice=messagebox.askyesno('Telegram · защищённый ключ',
                       'Не удалось прочитать ключ прокси из профиля Windows.\n'
                       'Создать новый ключ? После этого потребуется заново подключить Telegram Desktop.',
                       parent=self)
            if choice:
                self.settings.telegram_secret_error=''
                self.settings.telegram_secret_dpapi_blob=''
                self.settings.telegram_secret=''
                try:
                    save_settings(self.settings)
                except OSError as exc:
                    self.detail=f'Не удалось сохранить сброс Telegram: {exc}'
                    self._draw()
                    return
            else:
                return
        if not (self.settings.connect_dpi or self.settings.connect_telegram or self.settings.connect_dns):
            self.detail = 'Выберите хотя бы один компонент в настройках.'
            if not automatic:
                messagebox.showwarning('Нет компонентов', self.detail, parent=self)
            self._draw()
            return
        if os.name == 'nt' and not is_admin() and (self.settings.connect_dpi or self.settings.connect_dns):
            if automatic:
                self.detail = 'Автовосстановление требует прав администратора. Откройте программу от имени администратора.'
                self._draw()
                return
            previous = self.settings.desired_enabled
            self.settings.desired_enabled = True
            save_settings(self.settings)
            if relaunch_elevated():
                self._quit_now(skip_disconnect=True)
            else:
                self.settings.desired_enabled = previous
                save_settings(self.settings)
                messagebox.showwarning('Права администратора',
                     'Windows не разрешила повышение прав. Отключите DPI/GeoHide или запустите приложение от администратора.', parent=self)
            return
        if not automatic:
            self.recovery.reset()
            try:
                self.controller.request_connect()
            except Exception as exc:
                self.detail=f'Не удалось сохранить состояние: {exc}'
                self._draw()
                return
        self._begin_job()
        self.detail = ('Восстановление соединения…' if automatic else 'Подключение компонентов…')
        self._draw()
        threading.Thread(target=self._worker_connect,daemon=True,name='ConnectWorker').start()

    def _worker_connect(self):
        try:
            self.controller.connect(requested=False)
        except Exception as exc:
            self.events.put(('error',str(exc)))
        finally:
            self.events.put(('idle','connect'))

    def _start_disconnect(self):
        if self._quitting or self._disconnecting:
            return
        self._disconnecting = True
        self.recovery.reset()
        # Persist the explicit OFF decision immediately, even during long downloads.
        persistence_error = None
        try:
            self.controller.request_disconnect()
        except Exception as exc:
            # Fail-safe: stop engines even when OFF could not be persisted.
            # Reboot may restore an old ON value; give the user an explicit warning.
            persistence_error = str(exc)
        self._begin_job()
        self.detail = ('Не удалось сохранить ВЫКЛ. на диск — после перезагрузки возможен автозапуск. '
                       + persistence_error if persistence_error else
                       'Отключение и восстановление сетевых настроек…')
        if persistence_error:
            self.events.put(('persistence_warning', persistence_error))
        self._draw()
        threading.Thread(target=self._worker_disconnect,daemon=True,name='DisconnectWorker').start()

    def _worker_disconnect(self):
        try:
            self.controller.disconnect(remember=False)
        except Exception as exc:
            self.events.put(('error',str(exc)))
        finally:
            self.events.put(('idle','disconnect'))

    def _restore_dns(self):
        if self.settings.desired_enabled:
            messagebox.showwarning('GeoHide', 'Сначала отключите VORQELI, чтобы восстановить DNS.', parent=self)
            return
        if not (STATE_FILE.exists() or DOH_STATE_FILE.exists()):
            messagebox.showinfo('GeoHide','Сохранённых DNS-настроек нет.',parent=self)
            return
        threading.Thread(target=self._worker_restore_dns,daemon=True).start()

    def _worker_restore_dns(self):
        try:
            restore_geo_dns()
            self.events.put(('progress','Исходные DNS-настройки восстановлены.'))
        except Exception as exc:self.events.put(('error',f'Не удалось восстановить DNS: {exc}'))

    def _diagnose(self):
        if self.running_job:return
        self._begin_job()
        self.detail='Диагностика выполняется…'
        self._draw()
        threading.Thread(target=self._scan_worker,daemon=True).start()

    def _scan_worker(self):
        try:self.events.put(('diagnostics',check_all()))
        except Exception as exc:self.events.put(('error',str(exc)))
        finally:self.events.put(('idle','diagnostics'))

    def _poll(self):
        if self._quitting:return
        redraw=False
        try:
            while True:
                typ,value=self.events.get_nowait()
                if typ=='progress':self.detail=str(value);redraw=True
                elif typ=='state':
                    self.detail= value.detail or ('Модули запущены; доступность сайтов не подтверждена' if value.overall=='connected' else 'Отключено')
                    if self.settings.desired_enabled and value.telegram == 'on' and not self.settings.telegram_link_opened and os.name == 'nt':
                        try:
                            webbrowser.open(proxy_link(self.settings.telegram_port,self.settings.telegram_secret))
                            self.settings.telegram_link_opened=True
                            save_settings(self.settings)
                        except (OSError,ValueError):
                            pass
                    try:record_event('connection',f'Состояние: {value.overall}; DPI={value.dpi}; TG={value.telegram}; DNS={value.dns}')
                    except Exception:pass
                    self._update_tray_status(value)
                    redraw=True
                elif typ=='idle':
                    self._jobs=max(0,self._jobs-1)
                    self.running_job=self._jobs > 0
                    if value=='disconnect':self._disconnecting=False
                    redraw=True
                elif typ=='startup_error':
                    request,enabled,msg=value
                    if request==self._startup_request_id and self.settings.launch_at_startup==enabled:
                        self.settings.launch_at_startup=not enabled
                        try:save_settings(self.settings)
                        except OSError:pass
                        self.detail='Не удалось изменить автозапуск: '+msg
                        redraw=True
                elif typ=='update_checked':
                    self._update_busy = False
                    if value is None:
                        self.detail = 'Новых опубликованных версий нет.'
                        messagebox.showinfo('VORQELI · обновления',
                                            'Установлена актуальная опубликованная версия.', parent=self)
                    else:
                        self.detail = 'Доступна версия v' + value.version
                        agreed = messagebox.askyesno('VORQELI · обновление',
                            f'Доступна версия v{value.version}.\n\n'
                            'Установщик будет скачан только с GitHub Release и проверен по SHA-256.\n'
                            'Он НЕ будет запущен автоматически.\n\n'
                            'SHA-256 сам по себе не является цифровой подписью разработчика.\n\n'
                            'Скачать проверенный файл?',parent=self)
                        if agreed:
                            self._download_update(value)
                    redraw=True
                elif typ=='update_downloaded':
                    self._update_busy = False
                    self.detail = 'Установщик скачан и проверен по SHA-256; не запущен.'
                    messagebox.showinfo('VORQELI · обновление',
                        'Установщик проверен и сохранён в папке:\n' + str(value.parent) +
                        '\n\nПеред установкой полностью закройте приложение через трей. '
                        'Цифровая подпись издателя пока не предусмотрена.', parent=self)
                    redraw=True
                elif typ=='update_error':
                    self._update_busy = False
                    self.detail = 'Обновление недоступно: ' + str(value)
                    messagebox.showwarning('VORQELI · обновления',str(value),parent=self)
                    redraw=True
                elif typ=='persistence_warning':
                    messagebox.showwarning('VORQELI · сохранение настроек',
                        'Подключение сейчас будет остановлено, но Windows не смогла сохранить '
                        'выключенное состояние. После перезагрузки возможен повторный автозапуск.\n\n'
                        'Причина: ' + str(value), parent=self)
                    redraw=True
                elif typ=='error':self.detail='Ошибка: '+str(value);redraw=True
                elif typ=='show':self.deiconify();self.lift();self.focus_force();redraw=True
                elif typ=='tray_ready':
                    self._tray_ready=True
                    if self._start_minimized and self.state() == 'iconic':
                        self.withdraw()
                        self._start_minimized=False
                    redraw=True
                elif typ=='tray_stopped':
                    self._tray_ready=False
                    if self.state() == 'withdrawn' and not self._quitting:
                        # Recovery from a tray backend crash: never strand the GUI.
                        self.deiconify()
                    redraw=True
                elif typ=='connect':self._start_connect()
                elif typ=='disconnect':self._start_disconnect()
                elif typ=='quit':self.quit_app()
                elif typ=='dns_audit':
                    self._dns_audit_busy = False
                    self._set_dns_audit_text(str(value))
                elif typ=='diagnostics':
                    self.last_results=value
                    try:record_scan(value)
                    except OSError:pass
                    self.detail='Диагностика выполнена: '+datetime.now().strftime('%H:%M:%S')
                    redraw=True
        except queue.Empty:pass
        if redraw:self._draw()
        self.after(180,self._poll)

    def _update_tray_status(self, state: ConnectionReport) -> None:
        if not self._tray:
            return
        readable = {'connected':'Модули запущены', 'partial':'Частичное подключение',
                    'error':'Ошибка', 'off':'Выключено'}.get(state.overall,'Проверка')
        try:
            self._tray.title = f'VORQELI Connect · {readable}'
            self._tray.icon = tray_icon(Image.open(asset('VORQELI-logo.png')).convert('RGBA'),state.overall)
            self._tray.update_menu()
        except Exception:
            pass

    def _health_check(self):
        if self._quitting:
            return
        state = self.controller.runtime_health()
        if state != self._last_health:
            self._last_health = state
            if state.overall == 'partial':
                self.detail = state.detail
            self._update_tray_status(state)
            self._draw()
        now = time.monotonic()
        should_retry = self.recovery.observe(
            wanted=self.settings.desired_enabled,
            unhealthy=state.overall in ('error','partial'),
            busy=self.running_job or self._disconnecting,
            now=now,
        )
        if should_retry:
            state_info = self.recovery.status(now)
            self.detail = f'Автовосстановление, попытка {state_info.attempts}/{state_info.max_attempts}…'
            self._start_connect(automatic=True)
        self.after(3500,self._health_check)

    def hide_to_tray(self):
        if self.state() == 'normal':
            self.settings.window_geometry=self.geometry()
            try:
                save_settings(self.settings)
            except OSError as exc:
                # Closing the window must not kill or block a connection.
                self.detail=f'Положение окна не сохранено: {exc}'
        if self._tray_ready:
            self.withdraw()
        else:
            self.iconify()  # Never silently kill a connection because tray failed.

    def quit_app(self):
        if self._quitting:return
        self._quitting=True
        self.settings.window_geometry=self.geometry()
        try:
            save_settings(self.settings)
        except OSError as exc:
            # Still shut down owned processes and restore DNS even with no disk space.
            self.detail=f'Положение окна не сохранено: {exc}'
        # A real application exit stops local processes and restores changed DNS,
        # but does NOT alter desired_enabled; explicit Disconnect alone does that.
        def stop():
            try:
                result=self.controller.disconnect(remember=False)
                self.events.put(('exit_done',result))
            except Exception as exc:
                self.events.put(('exit_error',str(exc)))
        threading.Thread(target=stop,daemon=True).start()
        self.after(250,self._check_exit)

    def _check_exit(self):
        try:
            while True:
                name,result=self.events.get_nowait()
                if name=='exit_done':
                    if result.overall=='error':
                        messagebox.showwarning('Остановлено не полностью',
                            'При выходе возникла ошибка: '+result.detail+'\nПроверьте DNS-настройки Windows.',parent=self)
                    self._quit_now(skip_disconnect=True);return
                if name=='exit_error':
                    messagebox.showwarning('Не удалось остановить компоненты',str(result),parent=self)
                    self._quit_now(skip_disconnect=True);return
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
    parser.add_argument('--doctor',action='store_true',help='JSON-отчёт о локальной установке (без сетевых изменений)')
    parser.add_argument('--doctor-output',type=str,default='',help='Сохранить отчёт JSON в файл')
    parser.add_argument('--elevation-retry',action='store_true')
    parser.add_argument('--uninstall-cleanup',action='store_true')
    from . import __version__
    parser.add_argument('--version', action='version', version=f'VORQELI Connect {__version__}')
    args=parser.parse_args()
    if args.uninstall_cleanup:
        # Inno Setup checks the exit code *before deleting any installed files*.
        from .uninstall_safety import cleanup_for_uninstall
        result = cleanup_for_uninstall()
        if not result.success:
            raise SystemExit(8)
        return
    if args.doctor:
        from .doctor import print_diagnostic
        print_diagnostic(args.doctor_output or None)
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
