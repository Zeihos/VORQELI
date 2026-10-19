"""VORQELI Windows dashboard redesign, Canvas-only and network-side-effect free.

The renderer operates through the existing ConnectApp controller and Tk canvas.
No DNS/HOSTS/process mutation happens here; controls delegate to app methods.
"""
from __future__ import annotations

from functools import lru_cache
import webbrowser
from PIL import Image, ImageDraw, ImageFilter, ImageTk

from . import __version__ as VERSION
from .event_log import recent_events
from .history import load_history
from .flowseal_alts import ALT_MODES

BG = '#0A1223'
TEXT = '#E9F1FF'
MUTED = '#91A5C3'
DIM = '#69809F'
ACCENT = '#7394FF'
GREEN = '#42D9AD'
AMBER = '#F8BD78'
RED = '#FF8296'
CARD = '#12213A'
STROKE = '#294263'
PAGES = ('Главная', 'Диагностика', 'История', 'О проекте', 'Настройки', 'Сеть и стратегии')
SERVICE_NAMES = ('Discord', 'YouTube', 'Telegram Web', 'ChatGPT', 'Microsoft (Copilot, Designer, Xbox)')


def status_tone(state: str) -> str:
    return {'on': GREEN, 'connected': GREEN, 'partial': AMBER,
            'error': RED, 'off': DIM}.get(state, MUTED)


def service_summary(value: str) -> tuple[str, str]:
    """A DNS success or 403 never pretends full functionality of a service."""
    if value == 'Доступен':
        return ('HTTPS OK', GREEN)
    if value == 'Не проверено':
        return ('Не проверено', DIM)
    if 'Copilot:' in value:
        parts = [p.strip() for p in value.split('|')]
        if len(parts) == 3 and all(p.endswith(': OK') for p in parts):
            return ('3/3 HTTPS OK', GREEN)
        return ('Частичный ответ' if any(': OK' in p for p in parts) else 'Нет полного ответа', AMBER)
    if value.startswith('HTTP '):
        return (value + ' · ограничение', AMBER)
    if value == 'Нет ответа':
        return ('Нет ответа', RED)
    return (str(value)[:42], AMBER)


def _rounded(draw: ImageDraw.ImageDraw, coords: tuple[int,int,int,int], *,
             fill: str = CARD, border: str = STROKE, radius: int = 17) -> None:
    draw.rounded_rectangle(coords, radius=radius, fill=fill, outline=border, width=1)


@lru_cache(maxsize=20)
def background(width: int, height: int, page: str) -> Image.Image:
    """Baked opaque background, avoiding Tk transparency limitations."""
    w, h = max(1060, width), max(710, height)
    image = Image.new('RGB', (w, h), BG)
    pix = ImageDraw.Draw(image)
    for y in range(h):
        t = y/max(1,h-1)
        pix.line((0,y,w,y),fill=(10+int(1*t),17+int(5*t),32+int(12*t)))
    glow = Image.new('RGBA',(w,h),(0,0,0,0))
    g = ImageDraw.Draw(glow,'RGBA')
    g.ellipse((w-600,-470,w+240,365),fill=(43,92,232,55))
    g.ellipse((140,h-160,690,h+380),fill=(25,109,230,32))
    glow = glow.filter(ImageFilter.GaussianBlur(95))
    image = Image.alpha_composite(image.convert('RGBA'),glow)
    d = ImageDraw.Draw(image)
    d.rectangle((0,0,239,h),fill='#0D192E')
    d.line((239,0,239,h), fill='#28405F',width=1)
    d.rectangle((239,0,w,75), fill='#0D172B')
    d.line((239,75,w,75), fill='#203653')
    d.line((263,h-36,w-23,h-36),fill='#24405E',width=1)
    x, r = 271, w-28
    if page=='Главная':
        _rounded(d,(x,216,r,380),fill='#142C51',border='#355DA6',radius=20)
        col = (r-x-24)//3
        for i in range(3):
            left=x+i*(col+12)
            _rounded(d,(left,394,left+col,514),radius=16)
        _rounded(d,(x,527,r,h-54),radius=18)
    elif page=='Диагностика':
        for i in range(5):
            y=219+i*69
            _rounded(d,(x,y,r,y+61),fill='#13223B',radius=12)
        _rounded(d,(x,577,r,h-54),radius=14)
    elif page=='История':
        _rounded(d,(x,210,r,h-55),radius=17)
        for i in range(6):
            y=290+i*55
            if y+47<h-67:
                _rounded(d,(x+18,y,r-18,y+47),fill='#172B4A' if i%2==0 else '#132239',border='#1C3250',radius=10)
    elif page=='О проекте':
        _rounded(d,(x,216,r,330),radius=18)
        _rounded(d,(x,344,r,505),radius=18)
        _rounded(d,(x,516,r,h-54),radius=18)
    elif page=='Настройки':
        width_left=int((r-x-12)*.53)
        _rounded(d,(x,213,x+width_left,575),radius=17)
        _rounded(d,(x+width_left+12,213,r,575),radius=17)
        _rounded(d,(x,588,r,h-54),fill='#172B4A',radius=17)
    else:
        left=int((r-x-15)*.64)
        _rounded(d,(x,213,x+left,515),radius=18)
        _rounded(d,(x+left+15,213,r,515),radius=18)
        _rounded(d,(x,530,r,h-54),radius=18)
    return image.convert('RGB')


class Painter:
    def __init__(self, app):
        self.app=app
        self.canvas=app.canvas
        self.w,self.h=app._logical_size
        self.x,self.r=271,self.w-28

    def text(self,x,y,s,size=11,color=TEXT,*,bold=False,width=0,anchor='nw'):
        return self.app._text(x,y,str(s),size,color,anchor=anchor,weight='bold' if bold else 'normal',width=width)

    def line(self,x1,y1,x2,y2,color='#2B405E'):
        self.canvas.create_line(x1,y1,x2,y2,fill=color)

    def dot(self,x,y,color=GREEN,r=4):
        self.canvas.create_oval(x-r,y-r,x+r,y+r,fill=color,outline='')

    def button(self,x,y,w,h,label,callback,*,primary=False,disabled=False,small=False):
        tag=f'neo_ctl_{self.app._control_serial}'
        self.app._control_serial+=1
        bounds=(x,y,x+w,y+h)
        fg='#09152D' if primary else (DIM if disabled else TEXT)
        outline='#85A2FF' if primary else '#2D4C75'
        fill='#7696FF' if primary else '#1A3152'
        shape=self.canvas.create_polygon(self.app._rounded_coords(*bounds,min(13,h//3)),
                                          smooth=True,splinesteps=12,fill=fill,outline=outline,width=1,tags=(tag,))
        self.canvas.create_text(x+w/2,y+h/2,text=label,anchor='center',
             fill=fg,font=('Segoe UI',9 if small else 10,'bold'),tags=(tag,))
        if not disabled:
            index=self.app._register_control(bounds,callback,label)
            self.canvas.tag_bind(tag,'<Button-1>',lambda _e,n=index:self.app._mouse_activate(n))
            self.canvas.tag_bind(tag,'<Enter>',lambda _e,k=shape:self._hover(k,True,primary))
            self.canvas.tag_bind(tag,'<Leave>',lambda _e,k=shape:self._hover(k,False,primary))
        return shape

    def _hover(self,item,hovered,primary):
        self.canvas.itemconfig(item,fill=('#A0B7FF' if hovered else '#7696FF') if primary else ('#294A76' if hovered else '#1A3152'))
        self.canvas.configure(cursor='hand2' if hovered else '')

    def toggle(self,x,y,w,name,detail,value,handler):
        self.text(x,y,name,11,bold=True)
        self.text(x,y+22,detail,9,MUTED,width=w-102)
        self.button(x+w-95,y,85,34,'ВКЛ' if value else 'ВЫКЛ',handler,primary=value,small=True)
        self.line(x,y+55,x+w-8,y+55)

    def title(self,headline,description):
        self.text(self.x,112,headline,25,bold=True)
        self.text(self.x,158,description,11,MUTED,width=self.r-self.x-15)

    def chrome(self):
        a=self.app
        self.text(30,26,'V',23,ACCENT,bold=True)
        self.text(67,19,'VORQELI',19,bold=True)
        self.text(68,46,'CONNECT',10,MUTED,bold=True)
        self.line(18,83,219,83)
        self.text(32,105,'НАВИГАЦИЯ',9,DIM,bold=True)
        items=[('Главная','⌂'),('Диагностика','◈'),('История','◷'),('О проекте','?'),('Настройки','⚙')]
        for i,(page,symbol) in enumerate(items):
            y=145+i*54
            active=(page==a.selected_page or page=='Настройки' and a.selected_page=='Сеть и стратегии')
            if active:
                self.canvas.create_rectangle(22,y,26,y+40,fill=ACCENT,outline='')
            self.button(30,y,197,40,f'{symbol}    {page}',lambda p=page:a._page(p),primary=active)
        self.dot(34,self.h-107, GREEN if a.settings.desired_enabled else DIM)
        self.text(48,self.h-116,'Режим подключения' if a.settings.desired_enabled else 'Режим ожидания',10,bold=True)
        self.text(30,self.h-89,'WinWS · Telegram · GeoHide',9,MUTED)
        self.text(30,self.h-58,'VORQELI · v'+VERSION,9,DIM)
        self.text(self.x,29,'VORQELI / WINDOWS',10,MUTED,bold=True)
        self.dot(self.r-132,40, GREEN if a.settings.desired_enabled else DIM)
        self.text(self.r-120,33,'АКТИВЕН' if a.settings.desired_enabled else 'ОЖИДАНИЕ',9,MUTED,bold=True)
        self.text(self.x,self.h-28,'VORQELI Connect  ·  Все данные хранятся локально',9,DIM)
        self.text(self.r,self.h-28,'WINDOWS 10 / 11',9,DIM,anchor='ne')

    def home(self):
        a=self.app
        report=a.controller.status()
        enabled=a.settings.desired_enabled
        busy=a.running_job or a._disconnecting
        self.title('Управление подключением','Управляйте обходом ограничений и сетевыми компонентами в одном окне')
        color=status_tone(report.overall if enabled else 'off')
        self.dot(self.x+29,242,color,6)
        self.text(self.x+44,232,'СИСТЕМА РАБОТАЕТ' if report.overall=='connected' else
                  'ТРЕБУЕТ ВНИМАНИЯ' if enabled else 'ГОТОВО К ПОДКЛЮЧЕНИЮ',10,color,bold=True)
        self.text(self.x+30,268,'Обход активен' if enabled else 'Обход отключён',22,bold=True)
        self.text(self.x+31,307,'WinWS / '+str(a.controller.active_dpi_mode or a.settings.dpi_mode).upper(),10,MUTED)
        self.text(self.x+31,331,str(a.detail).replace('\n',' ')[:88],9,MUTED,width=self.r-self.x-260)
        self.button(self.r-198,273,169,53, 'ОТКЛЮЧИТЬ' if enabled else 'ПОДКЛЮЧИТЬ',
                    a._start_disconnect if enabled else a._start_connect,primary=not enabled,
                    disabled=a._disconnecting or (busy and not enabled))
        items=[('DPI / WinWS','dpi',a.settings.connect_dpi,'DPI · Flowseal'),
               ('Telegram','telegram',a.settings.connect_telegram,'MTProto-прокси'),
               ('GeoHide DNS','dns',a.settings.connect_dns,a.settings.dns_mode.upper()+' · Windows')]
        cw=(self.r-self.x-24)//3
        for i,(label,key,selected,desc) in enumerate(items):
            x=self.x+i*(cw+12)
            state=getattr(report,key)
            tone=status_tone(state if selected else 'off')
            self.dot(x+27,422,tone)
            self.text(x+41,414,label,13,bold=True)
            self.text(x+20,447,'Запущен' if state=='on' and selected else
                    'Выключен' if not selected or state=='off' else 'Требует внимания',11,tone,bold=True)
            self.text(x+20,475,desc,9,MUTED,width=cw-40)
        self.text(self.x+24,549,'Быстрые действия',14,bold=True)
        self.text(self.x+24,579,'Управляйте соединением без перехода в настройки',9,MUTED)
        span=self.r-self.x-48
        button_width=(span-20)//3
        for i,(label,call) in enumerate([
          ('Диагностика',lambda:a._page('Диагностика')),
          ('История',lambda:a._page('История')),
          ('Параметры DNS',lambda:a._page('Сеть и стратегии'))]):
            self.button(self.x+24+i*(button_width+10),612,button_width,42,label,call)

    def diagnostics(self):
        a=self.app
        self.title('Диагностика сети','HTTPS-ответы популярных сервисов; не проверяет авторизацию и функции аккаунта')
        self.button(self.r-159,116,148,41,'ПРОВЕРИТЬ ВСЁ',a._diagnose,primary=True,disabled=a.running_job)
        results=dict(a.last_results or [])
        labels=[('Discord','Discord'),('YouTube','YouTube'),('Telegram','Telegram Web'),
                ('ChatGPT','ChatGPT'),('Microsoft','Microsoft (Copilot, Designer, Xbox)')]
        for i,(title,key) in enumerate(labels):
            y=219+i*69
            outcome=results.get(key,'Не проверено')
            short,tone=service_summary(outcome)
            self.dot(self.x+24,y+31,tone,5)
            self.text(self.x+39,y+11,title,12,bold=True)
            meta=('Copilot · Designer · Xbox' if title=='Microsoft' else
                  'Проверка HTTPS-ответа' if title!='Telegram' else 'Telegram Web · HTTPS')
            self.text(self.x+39,y+34,meta,9,MUTED)
            self.text(self.r-166,y+20,short,9,tone,bold=True,anchor='ne')
            self.button(self.r-143,y+13,127,35,'ПРОВЕРИТЬ',lambda name=key:a._diagnose_service(name),small=True,disabled=a.running_job)
        self.text(self.x+22,594,'Инструменты проверки',11,bold=True)
        span=self.r-self.x-44
        bw=(span-22)//3
        for i,(title,fn) in enumerate([
           ('DNS / HOSTS',a._show_dns_audit),('ЖУРНАЛЫ',a._show_engine_logs),
           ('TELEGRAM WEB',a._show_telegram_web_audit)]):
            self.button(self.x+22+(bw+11)*i,618,bw,39,title,fn,small=True)

    def history(self):
        a=self.app
        self.title('История действий','События приложения и проверки сохраняются локально')
        self.button(self.r-165,116,155,40,'ЭКСПОРТ JSON',a._export_diagnostics,
                    disabled=not bool(a.last_results),small=True)
        self.text(self.x+26,231,'Последние события',13,bold=True)
        self.text(self.x+30,268,'ВРЕМЯ',9,DIM,bold=True)
        self.text(self.x+162,268,'СОБЫТИЕ',9,DIM,bold=True)
        entries=recent_events(limit=16)
        if not entries:self.text(self.x+29,306,'Здесь появятся подключения, проверки и изменения настроек.',11,MUTED)
        for i,item in enumerate(entries[:min(6,max(0,(self.h-350)//55))]):
            y=290+i*55
            label=str(item.get('message',''))
            self.text(self.x+29,y+15,str(item.get('timestamp',''))[11:19],10,MUTED)
            self.text(self.x+162,y+15,label[:95],10,TEXT,width=self.r-self.x-205)
        self.text(self.x+23,self.h-87,'Диагностических запусков: '+str(len(load_history())),9,MUTED)

    def about(self):
        a=self.app
        self.title('Поддержка и о проекте','Информация о приложении, компонентах и доступных материалах')
        self.text(self.x+30,241,'VORQELI CONNECT',19,bold=True)
        self.text(self.x+30,279,'Управление WinWS, Telegram MTProto и GeoHide DNS',10,MUTED)
        self.text(self.r-38,245,'v'+VERSION,13,ACCENT,bold=True,anchor='ne')
        self.text(self.x+24,363,'Документация и ссылки',13,bold=True)
        links=[('Исходный код','https://github.com/Zeihos/VORQELI'),
               ('GeoHide','https://geohide.ru/'),
               ('Проверить обновления',None)]
        span=self.r-self.x-48
        bw=(span-20)//3
        for i,(label,url) in enumerate(links):
            callback=(lambda u=url:webbrowser.open(u)) if url else a._check_updates
            self.button(self.x+24+i*(bw+10),419,bw,50,label,callback)
        self.text(self.x+24,534,'Компоненты соединения',12,bold=True)
        self.text(self.x+27,568,'WinWS / Flowseal      ·      Telegram MTProto      ·      GeoHide DNS',10,MUTED)
        self.text(self.x+27,592,'DNS и HOSTS изменяются только по явному действию пользователя.',9,MUTED)

    def settings(self):
        a=self.app
        self.title('Настройки приложения','Параметры Windows, поведения окна и основных компонентов')
        span=self.r-self.x-12
        left_w=int(span*.53)
        x1=self.x+22
        x2=self.x+left_w+32
        w1=left_w-43
        w2=self.r-x2-20
        self.text(x1,232,'ОБЩИЕ',10,ACCENT,bold=True)
        general=[
            ('Автозапуск Windows','Запускать при входе в систему','launch_at_startup'),
            ('Восстановление режима','Включать последний выбранный режим','restore_last_mode'),
            ('Сворачивать в трей','Продолжать работу после закрытия окна','minimize_to_tray'),
            ('Права администратора','Запрашивать UAC при старте','admin_on_launch'),
        ]
        for i,(name,detail,key) in enumerate(general):
            self.toggle(x1,263+i*73,w1,name,detail,getattr(a.settings,key),lambda k=key:a._toggle_setting(k))
        self.text(x2,232,'КОМПОНЕНТЫ',10,ACCENT,bold=True)
        components=[('Обход DPI / WinWS','Пакет Flowseal','connect_dpi'),
                    ('Telegram MTProto','Локальный прокси','connect_telegram'),
                    ('GeoHide DNS','Провайдер системного DNS','connect_dns')]
        for i,(name,detail,key) in enumerate(components):
            self.toggle(x2,267+i*84,w2,name,detail,getattr(a.settings,key),lambda k=key:a._toggle_setting(k))
        self.text(self.x+25,607,'Сеть и стратегии DPI',14,bold=True)
        self.text(self.x+25,632,'13 стратегий ALT · GeoHide DNS · HOSTS',9,MUTED)
        self.button(self.r-199,606,178,45,'ОТКРЫТЬ  →',lambda:a._page('Сеть и стратегии'),primary=True)

    def advanced(self):
        a=self.app
        self.title('Сеть и стратегии DPI','Подробная конфигурация обхода и системного DNS')
        span=self.r-self.x-15
        left=int(span*.64)
        lx=self.x+22
        rx=self.x+left+36
        rw=self.r-rx-15
        self.text(lx,237,'СТРАТЕГИЯ DPI',10,ACCENT,bold=True)
        chosen=a.settings.dpi_mode
        self.text(lx,269,'Профиль подключения',11,bold=True)
        self.button(self.x+left-173,258,159,42,'АВТО · ALT1–13',lambda:a._set_dpi_mode('alt_auto'),primary=chosen=='alt_auto',small=True)
        self.text(lx,324,'Ручной выбор стратегии',10,MUTED)
        cols=7
        chip_w=max(43,min(59,(left-50-6*(cols-1))//cols))
        for i,mode in enumerate(ALT_MODES):
            if mode=='alt_auto': continue
            idx=int(mode[3:])-1 if mode.startswith('alt') and mode[3:].isdigit() else i
            col,row=idx%cols,idx//cols
            self.button(lx+col*(chip_w+6),355+row*48,chip_w,39,mode.upper(),lambda m=mode:a._set_dpi_mode(m),primary=chosen==mode,small=True)
        self.text(rx,237,'DNS И ТРАНСПОРТ',10,ACCENT,bold=True)
        self.text(rx,272,'GeoHide DNS',13,bold=True)
        self.text(rx,311,'Режим разрешения имён',9,MUTED)
        gap=8
        half=(rw-gap)//2
        self.button(rx,341,half,39,'IPv4 DNS',lambda:a._set_dns_mode('plain'),primary=a.settings.dns_mode=='plain',disabled=a.settings.desired_enabled,small=True)
        self.button(rx+half+gap,341,half,39,'DoH / HTTPS',lambda:a._set_dns_mode('doh'),primary=a.settings.dns_mode=='doh',disabled=a.settings.desired_enabled,small=True)
        self.text(rx,402,'DoH требует поддержки Windows.',9,MUTED,width=rw)
        self.text(rx,426,'Смена режима — после отключения.',9,MUTED,width=rw)
        self.text(self.x+23,550,'ДОПОЛНИТЕЛЬНЫЕ ПАРАМЕТРЫ',10,ACCENT,bold=True)
        self.text(self.x+23,582,'Сетевые фильтры задаются активной стратегией Flowseal.',10,MUTED)
        width=(self.r-self.x-60)//3
        for i,(name,fn) in enumerate([
            ('ВОССТАНОВИТЬ DNS',a._restore_dns),
            ('HOSTS / ДОПОЛНИТЕЛЬНО',a._show_hosts_manager),
            ('НАЗАД К НАСТРОЙКАМ',lambda:a._page('Настройки'))]):
            self.button(self.x+20+i*(width+10),616,width,40,name,fn,primary=i==2,small=True)


def draw(app) -> None:
    """Render the current page using existing controller/actions and keyboard map."""
    if app._quitting or not app.winfo_exists():
        return
    app._logical_size=(max(1060,app.canvas.winfo_width()),max(710,app.canvas.winfo_height()))
    w,h=app._logical_size
    app._widgets=[]
    app._button_images=[]
    app._controls=[]
    app._control_serial=0
    app.canvas.delete('all')
    app.canvas.configure(cursor='')
    app._canvas_bg=ImageTk.PhotoImage(background(w,h,app.selected_page))
    app.canvas.create_image(0,0,image=app._canvas_bg,anchor='nw')
    p=Painter(app)
    p.chrome()
    pages={'Главная':p.home,'Диагностика':p.diagnostics,'История':p.history,
           'О проекте':p.about,'Настройки':p.settings,'Сеть и стратегии':p.advanced}
    pages.get(app.selected_page,p.home)()
    app._sync_scrollbars(w,h)
    app._render_focus()
