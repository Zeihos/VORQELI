"""Native Tk Canvas VORQELI application UI.

No screenshots, static mockup screens, click-through bitmap regions or fake
connectivity states. Every surface, label, button and focusable control is
constructed at runtime from trusted local application data. No OS/network
mutations occur in this renderer; existing ConnectApp callbacks own actions.
"""
from __future__ import annotations

import math
import sys
import webbrowser
from functools import lru_cache
from pathlib import Path
import tkinter as tk
from tkinter import messagebox
from PIL import Image, ImageTk
from typing import Callable

from . import __version__ as VERSION
from .diagnostics import SERVICES
from .event_log import recent_events
from .flowseal_alts import ALT_MODES
from .history import load_history

W, H = 1536, 1024
MIN_READABLE_SCALE = 0.80  # smaller screens scroll; never shrink the UI to illegibility
PAGES = ('Главная','Диагностика','История','О проекте','Настройки','Сеть и стратегии')
SERVICE_NAMES = tuple(SERVICES)
C = {
    'bg':'#020C21', 'sidebar':'#03132E', 'surface':'#061A39',
    'surface2':'#092347', 'edge':'#14549C', 'edgehi':'#168BFF',
    'text':'#EDF5FF','muted':'#94B4E2','dim':'#6A8BB7',
    'cyan':'#39CAFF','blue':'#116BEC','strong':'#1252D8',
    'green':'#2DE8AD','amber':'#FFD071','red':'#FF6E8C',
}


def classify_service(value: str) -> tuple[str,str]:
    """Never report 403/429 as a working service."""
    value=str(value)
    if value=='Доступен': return 'HTTPS OK',C['green']
    if value in ('Не проверено','Ожидание'): return value,C['dim']
    if value.startswith('HTTP '): return value+' · ограничение',C['amber']
    if 'Copilot:' in value:
        parts=[x.strip() for x in value.split('|')]
        count=sum(x.endswith(': OK') for x in parts)
        return f'{count}/3 HTTPS OK' if count else 'Нет полного ответа', C['green'] if count==3 else C['amber'] if count else C['red']
    if value=='Нет ответа': return value,C['red']
    return value[:54],C['amber']



def diagnostic_scope(app):
    """Keep the active job independent of progress text, which other modules may update.

    The text-only fallback is strictly for older standalone test harnesses.
    Production ConnectApp always provides _diagnostic_scope explicitly.
    """
    if not bool(getattr(app, 'running_job', False)):
        return None
    if hasattr(app, '_diagnostic_scope'):
        scope = app._diagnostic_scope
        return scope if scope == 'all' or scope in SERVICES else None
    detail = str(getattr(app, 'detail', ''))
    if detail.startswith('Диагностика выполняется'):
        return 'all'
    if detail.startswith('Проверяем сервис: '):
        target = detail[len('Проверяем сервис: '):].strip()
        return target if target in SERVICES else None
    return None


def diagnostic_result(name: str, value: str, fresh_names=None):
    """Do not present results restored from a previous app run as live checks."""
    label, color = classify_service(value)
    if fresh_names is not None and name not in fresh_names and value not in ('Не проверено', 'Ожидание'):
        return 'Ранее: ' + label, C['dim']
    return label, color

def history_events(app):
    all_items=recent_events(limit=100)
    current=getattr(app,'_native_history_filter','Все события')
    keys={
        'Подключение':('connection','connect','подключ','winws','telegram','dns'),
        'Настройки':('setting','настрой','стратег','профил','запуск'),
        'Ошибки':('error','failed','ошибка','сбой','отказ','не удалось'),
    }
    if current in keys:
        all_items=[e for e in all_items if any(k in (' '.join(str(e.get(z,'')) for z in ('action','kind','message'))).lower() for k in keys[current])]
    return all_items


@lru_cache(maxsize=80)
def _scaled_icon(file: Path, pixels: int):
    """Read only icon pixels (never entire-screen images), close handles immediately.

    Caches Pillow images across frequent status redraws. Tk PhotoImage instances
    remain per-window and are retained by app._native_images until next redraw.
    """
    with Image.open(file) as source:
        return source.convert('RGBA').resize((pixels,pixels),Image.Resampling.LANCZOS)


class Scene:
    def __init__(self,app):
        self.app=app;self.cv=app.canvas
        # A uniform scale preserves circles, the VORQELI logo and touch targets.
        # On small or high-DPI windows prefer scrollbars over tiny unreadable text.
        available_w=max(1,self.cv.winfo_width())
        available_h=max(1,self.cv.winfo_height())
        scale=max(MIN_READABLE_SCALE,min(available_w/W,available_h/H))
        self.sx=self.sy=self.sf=scale
        self.content_width=round(W*scale)
        self.content_height=round(H*scale)
        # ConnectApp._focus_control relies on this extent when a Canvas
        # control is clicked or focused with Tab.  Without it every click
        # raises AttributeError on a fresh native-UI application instance.
        self.app._logical_size=(self.content_width,self.content_height)
        self.count=0
        self.report=app.controller.status()
        self.settings=app.settings
        self.cv.delete('all')
        self.app._controls=[]
        self.app._widgets=[]
        self.app._button_images=[]
        self.app._native_images=[]
        self.cv.configure(background=C['bg'],cursor='')

    def xy(self,x,y):return round(x*self.sx),round(y*self.sy)
    def _rect_coords(self,rect):
        a,b,c,d=rect
        return (*self.xy(a,b),*self.xy(c,d))
    def rr(self,rect,fill='surface',outline='edge',radius=19,width=1,tags=()):
        x1,y1,x2,y2=self._rect_coords(rect)
        rad=max(0,min(round(radius*self.sf),(x2-x1)//2,(y2-y1)//2))
        color=C.get(fill,fill); edge=C.get(outline,outline) if outline else ''
        if rad<2:return self.cv.create_rectangle(x1,y1,x2,y2,fill=color,outline=edge,width=max(1,round(width*self.sf)),tags=tags)
        points=[x1+rad,y1,x2-rad,y1,x2,y1,x2,y1+rad,x2,y2-rad,
                x2,y2,x2-rad,y2,x1+rad,y2,x1,y2,x1,y2-rad,x1,y1+rad,x1,y1]
        return self.cv.create_polygon(points,smooth=True,splinesteps=14,fill=color,outline=edge,width=max(1,round(width*self.sf)),tags=tags)
    def line(self,x1,y1,x2,y2,color='edge',width=1):
        return self.cv.create_line(*self.xy(x1,y1),*self.xy(x2,y2),fill=C.get(color,color),width=max(1,round(width*self.sf)))
    def circle(self,x,y,r,color='cyan',outline='',tags=()):
        x1,y1=self.xy(x-r,y-r);x2,y2=self.xy(x+r,y+r)
        return self.cv.create_oval(x1,y1,x2,y2,fill=C.get(color,color),outline=C.get(outline,outline) if outline else '',tags=tags)
    def txt(self,x,y,s,size=18,color='text',bold=False,width=None,anchor='nw',tags=()):
        if s is None:s=''
        opts=dict(text=str(s),font=('Segoe UI',max(8,round(size*self.sf)),'bold' if bold else 'normal'),
                  fill=C.get(color,color),anchor=anchor,tags=tags)
        if width:opts['width']=round(width*self.sx)
        return self.cv.create_text(*self.xy(x,y),**opts)
    def header(self,index,title,description):
        self.txt(361,100,f'{index:02d}  /  {self.app.selected_page.upper()}',17,'cyan',True)
        self.txt(361,139,title,42,'text',True,width=1110)
        self.txt(361,195,description,19,'muted',width=845 if self.app.selected_page in ('Диагностика','История') else 1110)

    def button(self,rect,label,callback:Callable,*,kind='primary',size=18,enabled=True):
        self.count+=1
        name=f'control_{self.count}'
        fill='strong' if kind=='primary' else 'surface2' if kind=='secondary' else 'surface'
        hover='#247FFC' if kind=='primary' else '#103967'
        if not enabled:fill='#10213D'
        shape=self.rr(rect,fill, 'edgehi' if kind=='primary' and enabled else 'edge',radius=14,tags=(name,))
        x1,y1,x2,y2=rect
        self.txt((x1+x2)/2,(y1+y2)/2,label,size,'text' if enabled else 'dim',True,anchor='center',width=x2-x1-15,tags=(name,))
        if enabled:
            ix=self.app._register_control(self._rect_coords(rect),callback,str(label))
            self.cv.tag_bind(name,'<Button-1>',lambda e,n=ix:self.app._mouse_activate(n))
            self.cv.tag_bind(name,'<Enter>',lambda e,s=shape,h=hover:self._hover(s,h))
            self.cv.tag_bind(name,'<Leave>',lambda e,s=shape,c=fill:self._hover(s,C.get(c,c)))
        return shape
    def _hover(self,item,color):
        try:self.cv.itemconfigure(item,fill=color)
        except Exception:pass
    def card(self,rect,title,subtitle='',*,color='edge'):
        self.rr(rect,'surface',color,20)
        x1,y1,x2,y2=rect
        self.txt(x1+24,y1+22,title,21,'text',True,width=x2-x1-45)
        if subtitle:self.txt(x1+24,y1+59,subtitle,16,'muted',width=x2-x1-45)
    def pill(self,rect,text,foreground='muted'):
        self.rr(rect,'surface2','edge',11)
        x1,y1,x2,y2=rect
        self.txt((x1+x2)/2,(y1+y2)/2,text,16,foreground,True,anchor='center',width=x2-x1-12)
    def logo(self,x,y,side):
        """Show the real, unchanged bundled VORQELI logo. No drawn substitute."""
        try:
            from .app import asset
            file=asset('VORQELI-logo.png')
            pixels=max(12,round(side*self.sf))
            pic=_scaled_icon(file,pixels)
            photo=ImageTk.PhotoImage(pic,master=self.app)
            self.app._native_images.append(photo)
            self.cv.create_image(*self.xy(x,y),image=photo,anchor='nw')
            return True
        except (OSError,ValueError,ImportError,RuntimeError,tk.TclError):
            return False

    def brand_icon(self,stem,x,y,size=42):
        """Existing individual service pictogram, not an entire-screen mockup."""
        if stem not in ('discord','youtube','telegram','chatgpt','microsoft'):
            return False
        try:
            icon_file=Path(__file__).resolve().parent / 'ui_assets' / 'premium' / 'brand' / (stem+'.png')
            side=max(8,round(size*self.sf))
            pic=_scaled_icon(icon_file,side)
            photo=ImageTk.PhotoImage(pic,master=self.app)
            self.app._native_images.append(photo)
            self.cv.create_image(*self.xy(x,y),image=photo,anchor='nw')
            return True
        except (OSError,ValueError,ImportError,RuntimeError,tk.TclError):
            return False

    def section(self,title,subtitle=''):
        self.txt(365,248,title,24,'text',True)
        if subtitle:self.txt(365,285,subtitle,17,'muted')

    def chrome(self):
        self.cv.create_rectangle(0,0,*self.xy(W,H),fill=C['bg'],outline='')
        # Genuine scalable geometry and typography, not pre-rendered UI pictures.
        self.rr((18,19,1518,1005),'bg','edgehi',23)
        # Native layered neon strokes rather than a flattened screenshot.
        for j in range(14):
            blue=18+j*5
            color=f'#{8:02X}{max(27,min(150,blue)):02X}{max(66,min(244,blue+78)):02X}'
            coords=[*self.xy(1050,220+j*4),*self.xy(1230,156+j*3),
                    *self.xy(1360,150+j*2),*self.xy(1500,194+j*2)]
            self.cv.create_line(*coords,fill=color,width=max(1,round(self.sf)),smooth=True)
        self.rr((21,21,312,1002),'sidebar','edge',22)
        self.line(320,77,320,944,'edge')
        self.txt(356,48,'VORQELI  /  NETWORK CONTROL',17,'muted')
        self.txt(358,964,'VORQELI Connect  ·  Локальное приложение',15,'muted')
        self.txt(1493,963,'WINDOWS 10 / 11',14,'muted',anchor='ne')
        status=getattr(self.report,'overall','off')
        clr='green' if status=='connected' else 'amber' if status=='partial' else 'red' if status=='error' else 'dim'
        text='АКТИВНО' if status=='connected' else 'ЧАСТИЧНО' if status=='partial' else 'ОШИБКА' if status=='error' else 'ОЖИДАНИЕ'
        self.pill((1113,36,1320,74),text,clr)
        self.button((1346,29,1407,76),'—',lambda:self._minimize(),kind='secondary')
        self.button((1447,29,1506,76),'✕',self.app._window_close,kind='secondary')
        # The branding is the actual project logo asset, unchanged.
        if not self.logo(43,42,82):
            self.rr((45,44,123,122),'strong','cyan',13)
            self.txt(85,82,'V',52,'cyan',True,anchor='center')
        self.txt(138,50,'VORQELI',29,'text',True)
        self.txt(139,86,'C O N N E C T',16,'cyan',True)
        self.line(48,143,284,143,'edge')
        self.txt(48,168,'НАВИГАЦИЯ',15,'muted',True)
        nav=[('Главная','⌂'),('Диагностика','◇'),('История','◷'),('О проекте','ⓘ'),('Настройки','⚙')]
        for i,(page,symbol) in enumerate(nav):
            y=207+i*70
            selected=self.app.selected_page==page or (page=='Настройки' and self.app.selected_page=='Сеть и стратегии')
            name=f'nav_{i}'
            fill='#10417F' if selected else 'sidebar'
            shape=self.rr((33,y,299,y+61),fill,'edgehi' if selected else 'sidebar',13,tags=(name,))
            self.txt(61,y+30,symbol,27,'cyan',anchor='center',tags=(name,))
            self.txt(109,y+30,page,18,'text' if selected else 'muted',selected,anchor='w',tags=(name,))
            idx=self.app._register_control(self._rect_coords((33,y,299,y+61)),lambda p=page:self.app._page(p),'Раздел: '+page)
            self.cv.tag_bind(name,'<Button-1>',lambda e,n=idx:self.app._mouse_activate(n))
            self.cv.tag_bind(name,'<Enter>',lambda e,s=shape:self._hover(s,'#103463'))
            self.cv.tag_bind(name,'<Leave>',lambda e,s=shape,c=fill:self._hover(s,c))
        self.rr((35,822,298,979),'surface','edgehi',17)
        self.circle(62,859,10,clr)
        self.txt(85,842,'Соединение активно' if status=='connected' else 'Частичное соединение' if status=='partial' else 'Ошибка соединения' if status=='error' else 'Ожидание',17,'text',True,width=201)
        self.txt(53,901,'WinWS · Telegram · DNS',15,'muted')
        self.line(52,935,273,935,'edge')
        self.txt(54,947,'v'+VERSION+' · Windows 10/11',13,'dim')
        # Only the blank top title area can be used to drag the frameless window.
        from .frameless import begin_move,move,end_move
        def begin(e):
            xx=self.cv.canvasx(e.x)/self.sx; yy=self.cv.canvasy(e.y)/self.sy
            if 320<=xx<=1090 and yy<=85:begin_move(self.app,e.x_root,e.y_root)
        def drag(e):
            if getattr(self.app,'_frameless_mouse',None) is not None:move(self.app,e.x_root,e.y_root)
        self.cv.bind('<ButtonPress-1>',begin)
        self.cv.bind('<B1-Motion>',drag)
        self.cv.bind('<ButtonRelease-1>',lambda e:end_move(self.app))
    def _minimize(self):
        from .frameless import minimize
        minimize(self.app)

    def home(self):
        self.header(1,'Управление подключением','Сетевые инструменты и состояния — в одном окне')
        self.rr((344,238,1490,498),'surface2','edgehi',24)
        # Power ring changes color based on observed modules, not preference.
        status=getattr(self.report,'overall','off')
        clr='green' if status=='connected' else 'amber' if status=='partial' else 'red' if status=='error' else 'cyan'
        self.circle(500,367,111,'surface')
        self.circle(500,367,95,clr)
        self.circle(500,367,90,'surface')
        self.circle(500,367,76,'blue')
        self.circle(500,367,71,'surface')
        if not self.logo(433,300,134):
            self.txt(500,359,'V',85,'cyan',True,anchor='center')
        self.pill((651,273,1100,314),'МОДУЛИ ЗАПУЩЕНЫ' if status=='connected' else 'ЧАСТЬ МОДУЛЕЙ ЗАПУЩЕНА' if status=='partial' else 'ОШИБКА МОДУЛЕЙ' if status=='error' else 'ГОТОВО К ПОДКЛЮЧЕНИЮ','green' if status=='connected' else 'amber' if status=='partial' else 'red' if status=='error' else 'muted')
        active=status=='connected'
        label='Модули запущены' if active else 'Часть модулей запущена' if status=='partial' else 'Ошибка подключения' if status=='error' else 'Обход отключён'
        self.txt(652,333,label,36,'text',True,width=535)
        strategy=getattr(self.app.controller,'active_dpi_mode',None) or self.settings.dpi_mode
        self.txt(654,397,'WinWS · '+('AUTO 1–13' if strategy=='alt_auto' else strategy.upper()),20,'muted')
        selected=[name for name in ('dpi','telegram','dns') if getattr(self.settings,'connect_'+name,False)]
        on=sum(getattr(self.report,n,'off')=='on' for n in selected)
        self.txt(654,441,f'Модули: {on}/{len(selected)} · не проверка доступа к сайтам',16,'muted',width=520)
        desired=bool(getattr(self.settings,'desired_enabled',False))
        self.button((1189,398,1470,470),'ПОДКЛЮЧЕНИЕ...' if getattr(self.app,'running_job',False) else 'ОТКЛЮЧИТЬ' if desired else 'ПОДКЛЮЧИТЬ',self.app._start_disconnect if desired else self.app._start_connect,enabled=not getattr(self.app,'_disconnecting',False) and not getattr(self.app,'running_job',False),size=20)
        cards=[('DPI / WinWS','dpi','Сеть и стратегии'),('Telegram','telegram','Настройки'),('GeoHide DNS','dns','Сеть и стратегии')]
        for i,(title,key,target) in enumerate(cards):
            left=344+i*382
            self.card((left,520,left+364,690),title)
            stat=getattr(self.report,key,'off')
            color='green' if stat=='on' else 'amber' if stat=='error' else 'dim'
            self.circle(left+34,604,8,color)
            self.txt(left+54,592,'Запущен' if stat=='on' else 'Ошибка' if stat=='error' else 'Отключён',17,color,True)
            self.line(left+25,639,left+338,639,'edge')
            note=('Стратегия: '+self.settings.dpi_mode.upper()) if key=='dpi' else 'Локальный MTProto' if key=='telegram' else ('DoH / HTTPS' if self.settings.dns_mode=='doh' else 'IPv4 DNS')
            self.txt(left+27,652,note,16,'muted',width=315)
            self.button((left+295,551,left+345,603),'›',lambda p=target:self.app._page(p),kind='secondary',size=26)
        self.rr((344,711,1490,930),'surface','edge',23)
        self.txt(382,738,'Быстрые действия',29,'text',True)
        self.txt(382,782,'Диагностика соединения, события и параметры сети',18,'muted')
        for i,(s,page) in enumerate((('Диагностика','Диагностика'),('История событий','История'),('Настройки сети','Сеть и стратегии'))):
            left=368+i*373
            self.button((left,830,left+351,911),s+'   ›',lambda p=page:self.app._page(p),kind='secondary',size=20)

    def diagnostics(self):
        self.header(2,'Диагностика сервисов','HTTPS-проверки не подтверждают вход в учётную запись или обход блокировок')
        busy=bool(getattr(self.app,'running_job',False))
        scope=diagnostic_scope(self.app)
        all_pending=scope=='all'
        one_pending=scope if scope in SERVICES else None
        # None in old test harnesses retains their original semantics;
        # a production application always owns an explicit set of fresh names.
        fresh=getattr(self.app,'_diagnostic_fresh',None)
        self.button((1207,142,1487,214),'ВЫПОЛНЯЕТСЯ…' if all_pending else 'ЗАНЯТО' if busy else 'ПРОВЕРИТЬ ВСЁ',
                    self.app._diagnose,size=19,enabled=not busy)
        result=dict(getattr(self.app,'last_results',[]) or [])
        for i,name in enumerate(SERVICE_NAMES):
            y=254+i*103
            self.rr((344,y,1490,y+91),'surface','edge',17)
            symbol=('discord','youtube','telegram','chatgpt','microsoft')[i]
            if not self.brand_icon(symbol,356,y+25,42):
                self.circle(377,y+46,15,['cyan','red','cyan','green','blue'][i])
            self.txt(416,y+16,name,21,'text',True,width=540)
            self.txt(416,y+53,'Проверка HTTPS-ответа',15,'muted')
            pending=busy and (all_pending or one_pending==name)
            state,col=('Проверяется…','amber') if pending else diagnostic_result(name,result.get(name,'Не проверено'),fresh)
            self.txt(963,y+31,state,16,col,True,width=253)
            self.button((1269,y+20,1464,y+73),'ПРОВЕРЯЕТСЯ…' if pending else 'ЗАНЯТО' if busy else 'ПРОВЕРИТЬ',
                        lambda n=name:self.app._diagnose_service(n),kind='secondary',size=16,
                        enabled=not busy)
        if busy:
            # The app's existing worker updates detail; do not invent progress.
            caption=('Проверяем все сервисы…' if all_pending else
                     'Проверяем: '+one_pending if one_pending else
                     str(getattr(self.app,'detail','Выполняется другая операция…')))
            self.txt(360,777,caption,15,'amber',width=1070)
        else:
            self.txt(360,787,'Дополнительная проверка',20,'text',True)
        for i,(name,cb) in enumerate((('DNS / HOSTS',self.app._show_dns_audit),('ЖУРНАЛЫ',self.app._show_engine_logs),('TELEGRAM WEB',self.app._show_telegram_web_audit))):
            x=352+i*380
            self.button((x,836,x+364,914),name,cb,kind='secondary',size=18)

    def history(self):
        self.header(3,'История событий','Локальные действия и события приложения')
        from .history import load_history as _load_history
        from tkinter import filedialog
        import json
        def export():
            events=recent_events(limit=100)
            if not events:
                messagebox.showinfo('История','Сохранённых событий пока нет.',parent=self.app);return
            path=filedialog.asksaveasfilename(parent=self.app,defaultextension='.json',filetypes=[('JSON','*.json')],initialfile='VORQELI-history.json')
            if path:
                try:Path(path).write_text(json.dumps(events,ensure_ascii=False,indent=2),encoding='utf-8')
                except OSError as exc:messagebox.showerror('История',str(exc),parent=self.app)
        self.button((1251,140,1490,213),'ЭКСПОРТ JSON',export)
        current=getattr(self.app,'_native_history_filter','Все события')
        for i,name in enumerate(('Все события','Подключение','Настройки','Ошибки')):
            left=344+i*235
            self.button((left,247,left+218,296),name,lambda n=name:self._filter(n),kind='primary' if current==name else 'secondary',size=16)
        events=history_events(self.app)
        page_count=max(1,math.ceil(len(events)/10))
        page=min(max(0,int(getattr(self.app,'_native_history_page',0))),page_count-1)
        self.app._native_history_page=page
        self.rr((344,318,1490,922),'surface','edge',20)
        for x,s in ((377,'ВРЕМЯ'),(566,'СОБЫТИЕ'),(1200,'ТИП')):
            self.txt(x,337,s,15,'muted',True)
        self.line(370,375,1468,375,'edge')
        visible=events[page*10:(page+1)*10]
        if not visible:self.txt(560,630,'Нет сохранённых событий для выбранного фильтра',21,'muted')
        for i,event in enumerate(visible):
            y=385+i*48
            name=f'history_row_{i}'
            fill='surface2' if i%2==0 else 'surface'
            shape=self.rr((354,y,1480,y+46),fill,fill,8,tags=(name,))
            msg=str(event.get('message','')).replace('\n',' ')[:110]
            action=str(event.get('action',event.get('kind','событие')))
            timestamp=str(event.get('timestamp',''))
            col='red' if any(word in (action+' '+msg).lower() for word in ('error','failed','ошибка','сбой')) else 'green'
            self.circle(376,y+22,7,col,tags=(name,))
            self.txt(395,y+14,timestamp[11:19] or '--:--:--',14,'muted',tags=(name,))
            self.txt(563,y+12,msg[:67]+'…' if len(msg)>67 else msg,15,'text',width=601,tags=(name,))
            self.txt(1200,y+14,action[:23],15,col,width=240,tags=(name,))
            # Real row action: truncated text can always be opened in full.
            callback=lambda item=event:self._show_history_event(item)
            index=self.app._register_control(self._rect_coords((354,y,1480,y+46)),
                                             callback,'Событие: '+(msg[:50] or action))
            self.cv.tag_bind(name,'<Button-1>',lambda e,n=index:self.app._mouse_activate(n))
            self.cv.tag_bind(name,'<Enter>',lambda e,s=shape:self._hover(s,'#123765'))
            self.cv.tag_bind(name,'<Leave>',lambda e,s=shape,c=fill:self._hover(s,C[c]))
        self.txt(370,875,f'Событий: {len(events)} · Диагностик: {len(_load_history())}',14,'muted')
        self.txt(1280,875,f'{page+1} / {page_count}',15,'muted',True)
        self.button((1370,865,1414,902),'‹',lambda:self._turn(-1),kind='secondary',enabled=page>0)
        self.button((1424,865,1468,902),'›',lambda:self._turn(1),kind='secondary',enabled=page+1<page_count)

    def _show_history_event(self,item):
        timestamp=str(item.get('timestamp',''))[:80]
        action=str(item.get('action',item.get('kind','событие')))[:100]
        message=str(item.get('message',''))[:2000]
        messagebox.showinfo('VORQELI · событие',
            f'Время: {timestamp}\nТип: {action}\n\n{message}',parent=self.app)

    def _filter(self,name):
        self.app._native_history_filter=name
        self.app._native_history_page=0
        self.app._draw()
    def _turn(self,step):
        self.app._native_history_page=max(0,int(getattr(self.app,'_native_history_page',0))+step)
        self.app._draw()

    def about(self):
        self.header(4,'О проекте VORQELI','Локальное приложение для управления сетевыми компонентами Windows')
        self.rr((344,242,1490,489),'surface2','edgehi',22)
        self.txt(405,288,'VORQELI CONNECT',42,'text',True)
        self.txt(405,357,'Обход DPI · Telegram MTProto · GeoHide DNS',21,'muted')
        self.pill((1210,266,1450,313),'v'+VERSION,'cyan')
        self.txt(406,427,'Исходный код и информация о лицензиях доступны в GitHub',16,'muted')
        self.txt(364,510,'Сетевые компоненты',25,'text',True)
        for i,(title,key,details) in enumerate((('WinWS / DPI','dpi','Стратегии ALT1–ALT13'),('Telegram','telegram','MTProto локально'),('GeoHide DNS','dns','Системный DNS / HOSTS'))):
            left=344+i*382
            self.card((left,559,left+364,777),title,details)
            active=getattr(self.report,key,'off')=='on'
            self.circle(left+39,709,10,'green' if active else 'dim')
            self.txt(left+64,693,'Запущен' if active else 'Не запущен',17,'green' if active else 'muted',True)
        self.button((352,808,710,899),'GitHub · Исходный код',lambda:webbrowser.open('https://github.com/Zeihos/VORQELI'),kind='secondary',size=19)
        self.button((725,808,1081,899),'Проверить обновления',self.app._check_updates,kind='secondary',size=19)
        self.button((1095,808,1483,899),'Диагностика сети',lambda:self.app._page('Диагностика'),kind='secondary',size=19)

    def settings_page(self):
        self.header(5,'Настройки приложения','Поведение при запуске и включение сетевых компонентов')
        rows=[
            (('Автозапуск с Windows','Запускать при входе в систему','launch_at_startup'),
             ('DPI / WinWS','Сетевой модуль обхода','connect_dpi')),
            (('Восстановление режима','Включать ранее выбранный режим','restore_last_mode'),
             ('Telegram MTProto','Локальный прокси','connect_telegram')),
            (('Сворачивать в трей','Продолжать работу при закрытии окна','minimize_to_tray'),
             ('GeoHide DNS','Системный DNS-резолвер','connect_dns')),
            (('Запуск от администратора','Запрашивать UAC при запуске','admin_on_launch'),None)
        ]
        self.card((344,238,939,751),'ОБЩИЕ','Параметры поведения Windows')
        self.card((954,238,1490,751),'КОМПОНЕНТЫ','Управление сетевыми модулями')
        for i,(left,right) in enumerate(rows):
            y=348+i*94
            self._setting(363,y,920,left)
            if right:self._setting(974,y,1470,right)
        self.rr((344,772,1490,924),'surface2','edgehi',21)
        self.txt(378,799,'Сеть и стратегии DPI',28,'text',True)
        self.txt(379,847,'ALT1–ALT13 · GeoHide DNS · HOSTS · восстановление',18,'muted')
        self.button((1200,801,1464,890),'ОТКРЫТЬ  →',lambda:self.app._page('Сеть и стратегии'),size=20)

    def _setting(self,x,y,right,setting):
        name,desc,key=setting
        state=bool(getattr(self.settings,key,False))
        tag=f'opt_{key}'
        rect=(x,y,right,y+88)
        fill='surface2'
        shape=self.rr(rect,fill,'edge',14,tags=(tag,))
        self.txt(x+22,y+17,name,19,'text',True,width=right-x-153,tags=(tag,))
        self.txt(x+22,y+49,desc,15,'muted',width=right-x-153,tags=(tag,))
        cx=right-67;cy=y+44
        self.rr((cx-42,cy-20,cx+43,cy+20),'blue' if state else '#193456','cyan' if state else 'edge',18,tags=(tag,))
        self.circle(cx+19 if state else cx-20,cy,15,'text',tags=(tag,))
        idx=self.app._register_control(self._rect_coords(rect),lambda k=key:self.app._toggle_setting(k),'Переключить '+name)
        self.cv.tag_bind(tag,'<Button-1>',lambda e,n=idx:self.app._mouse_activate(n))
        self.cv.tag_bind(tag,'<Enter>',lambda e,s=shape:self._hover(s,'#123361'))
        self.cv.tag_bind(tag,'<Leave>',lambda e,s=shape,c=fill:self._hover(s,C[c]))

    def network(self):
        self.header(6,'Сеть и стратегии DPI','Настройка WinWS, GeoHide DNS, HOSTS и инструментов восстановления')
        self.card((344,242,995,717),'Стратегии DPI','Переключение требует переподключения')
        mode=str(self.settings.dpi_mode)
        self.button((780,314,966,368),'АВТО 1–13',lambda:self.app._set_dpi_mode('alt_auto'),kind='primary' if mode=='alt_auto' else 'secondary',size=16)
        self.txt(369,379,'РУЧНОЙ ВЫБОР',15,'muted',True)
        for i,m in enumerate(ALT_MODES):
            row,col=divmod(i,7)
            x=370+col*87; y=416+row*75
            self.button((x,y,x+79,y+58),m.upper(),lambda mm=m:self.app._set_dpi_mode(mm),kind='primary' if m==mode else 'secondary',size=15)
        self.txt(370,593,'Текущая стратегия: '+('АВТО 1–13' if mode=='alt_auto' else mode.upper()),17,'cyan',True)
        self.txt(369,641,'При смене режима во время работы переподключись.',16,'muted',width=584)
        self.card((1010,242,1490,717),'GeoHide DNS','Выбор транспорта без скрытых переключений')
        self.txt(1035,384,'ТРАНСПОРТ DNS',17,'muted',True)
        idle=not bool(getattr(self.settings,'desired_enabled',False))
        self.button((1035,431,1242,502),'IPv4 DNS',lambda:self.app._set_dns_mode('plain'),kind='primary' if self.settings.dns_mode=='plain' else 'secondary',enabled=idle,size=18)
        self.button((1253,431,1464,502),'DoH / HTTPS',lambda:self.app._set_dns_mode('doh'),kind='primary' if self.settings.dns_mode=='doh' else 'secondary',enabled=idle,size=18)
        self.txt(1035,546,'Смена транспорта доступна при отключении.',16,'muted',width=423)
        dns=getattr(self.report,'dns','off')
        self.txt(1035,617,'Модуль: '+('запущен' if dns=='on' else 'ошибка' if dns=='error' else 'не запущен'),18,'green' if dns=='on' else 'red' if dns=='error' else 'muted',True)
        self.txt(365,743,'Сетевые инструменты',24,'text',True)
        for i,(label,cb) in enumerate((('Проверка',lambda:self.app._page('Диагностика')),('DNS / HOSTS',self.app._show_dns_audit),('Правила HOSTS',self.app._show_hosts_manager),('Настройки',lambda:self.app._page('Настройки')))):
            x=345+i*287
            self.button((x,796,x+274,864),label,cb,kind='secondary',size=17)
        self.button((349,877,698,936),'ВОССТАНАВЛИВАЕМ…' if getattr(self.app,'_dns_restore_busy',False) else 'ВОССТАНОВИТЬ DNS',self.app._restore_dns,kind='secondary',size=17,enabled=not getattr(self.app,'_dns_restore_busy',False) and not getattr(self.app,'running_job',False) and not getattr(self.app,'_disconnecting',False))
        self.button((707,877,1071,936),'HOSTS / ПРАВИЛА',self.app._show_hosts_manager,kind='secondary',size=17)


def draw(app):
    """Render six real-time vector scenes from the current application state."""
    if getattr(app,'_quitting',False) or not app.winfo_exists():return
    cw=app.canvas.winfo_width();ch=app.canvas.winfo_height()
    if cw<10 or ch<10:
        app.after(100,app._draw);return
    painter=Scene(app)
    painter.chrome()
    current=app.selected_page
    targets={
        'Главная':painter.home,'Диагностика':painter.diagnostics,'История':painter.history,
        'О проекте':painter.about,'Настройки':painter.settings_page,'Сеть и стратегии':painter.network,
    }
    targets.get(current,painter.home)()
    app._sync_scrollbars(painter.content_width,painter.content_height)
    app._render_focus()
