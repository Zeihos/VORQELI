"""VORQELI Connect v0.39: clickable, state-driven rendering of approved artwork.

The six approved compositions are bundled locally. They are UI *artwork*, not
screenshots of actual status. Real network status, diagnostic results, settings,
version and history are repainted at every frame from the actual controller.
No networking, registry or file mutation happens in this module.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Callable
import webbrowser

from PIL import Image, ImageDraw, ImageFont, ImageTk

from . import __version__ as VERSION
from .event_log import recent_events
from .flowseal_alts import ALT_MODES
from .history import load_history

PAGES = ('Главная', 'Диагностика', 'История', 'О проекте', 'Настройки', 'Сеть и стратегии')
SERVICE_NAMES = ('Discord', 'YouTube', 'Telegram Web', 'ChatGPT', 'Microsoft (Copilot, Designer, Xbox)')
W, H = 1536, 1024
ASSET_DIR = Path(__file__).resolve().parent / 'ui_assets' / 'premium'
ART_FILES = {'Главная':'home.png','Диагностика':'diagnostics.png','История':'history.png',
             'О проекте':'about.png','Настройки':'settings.png','Сеть и стратегии':'network.png'}
COLORS = {'green':'#26E8B3','red':'#FF6687','amber':'#FAD56B','muted':'#8095B9',
          'text':'#F3F8FF','sub':'#9BB7E3','cyan':'#28CAFF','blue':'#4C96FF'}


def service_summary(value: str) -> tuple[str,str]:
    """HTTPS 403 indicates an answer with restrictions, NOT service availability."""
    value=str(value)
    if value == 'Доступен': return 'HTTPS OK', COLORS['green']
    if value in ('Не проверено','Ожидание'): return value, COLORS['muted']
    if 'Copilot:' in value:
        parts=[p.strip() for p in value.split('|')]
        ok=sum(p.endswith(': OK') for p in parts)
        if len(parts)==3 and ok==3:return '3/3 HTTPS OK', COLORS['green']
        if ok:return f'{ok}/3 HTTPS OK', COLORS['amber']
        return 'Нет полного ответа', COLORS['red']
    if value.startswith('HTTP '):return value[:16]+' · ограничение',COLORS['amber']
    if value=='Нет ответа':return 'Нет ответа',COLORS['red']
    return value[:28],COLORS['amber']


def _font(size:int,bold=False) -> ImageFont.FreeTypeFont:
    if bold:
        choices=('C:/Windows/Fonts/seguisb.ttf','C:/Windows/Fonts/segoeuib.ttf',
                 '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf')
    else:
        choices=('C:/Windows/Fonts/segoeui.ttf',
                 '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')
    for p in choices:
        try:return ImageFont.truetype(p,size)
        except OSError:pass
    return ImageFont.load_default(size=size)


def _text(d:ImageDraw.ImageDraw,x:int,y:int,message:object,size=17,color='#F3F8FF',bold=False,max_chars=None):
    val=' '.join(str(message).split())
    if max_chars is not None and len(val)>max_chars:val=val[:max_chars-1]+'…'
    d.text((x,y),val,font=_font(size,bold),fill=color,stroke_width=0)


def _panel(d:ImageDraw.ImageDraw,rect,fill='#081B39',outline='#1F69C3',radius=15):
    d.rounded_rectangle(rect,radius=radius,fill=fill,outline=outline,width=1)


def _erase(d,box,color='#071D3A',radius=6):
    d.rounded_rectangle(box,fill=color,radius=radius)


def _status(d,x,y,name,value):
    title,color=service_summary(value)
    _erase(d,(x,y,x+255,y+37),'#061A35',9)
    d.ellipse((x+1,y+12,x+18,y+29),fill=color)
    _text(d,x+31,y+6,title,16,color,True,max_chars=30)


def _switch(d,x,y,value,enabled=True):
    bg='#086EED' if value else '#14335B'
    if not enabled:bg='#162844'
    d.rounded_rectangle((x,y,x+78,y+38),radius=19,fill=bg,outline='#36CCFF' if value and enabled else '#3C5C8E',width=2)
    px=x+49 if value else x+8
    d.ellipse((px,y+7,px+25,y+32),fill='#F4F7FF')


def _module_status(d,x,y,label,on):
    _erase(d,(x,y,x+205,y+40),'#071B39',radius=6)
    color=COLORS['green'] if on else COLORS['muted']
    d.ellipse((x,y+11,x+14,y+25),fill=color)
    _text(d,x+22,y+4,'Запущен' if on else 'Отключён',16,color,True)


def _health(app):
    return app.controller.status()


@lru_cache(maxsize=12)
def artwork(page:str)->Image.Image:
    if page not in ART_FILES:raise ValueError('Недопустимая страница')
    img=Image.open(ASSET_DIR / ART_FILES[page]).convert('RGB')
    if img.size != (W,H):raise ValueError('Неверный размер темы '+page)
    return img


def build_frame(app,page=None) -> Image.Image:
    """Bake *current* values over decorative art; never display fictitious logs."""
    page=page or app.selected_page
    im=artwork(page).copy();d=ImageDraw.Draw(im)
    settings=app.settings
    report=_health(app)
    overall=getattr(report,'overall','off')
    is_on=bool(getattr(settings,'desired_enabled',False))
    # Desktop-level connectivity is not equivalent to web-service access.
    tone=COLORS['green'] if overall=='connected' else COLORS['amber'] if overall=='partial' else COLORS['muted']
    label='АКТИВЕН' if overall=='connected' else 'ЧАСТИЧНО' if overall=='partial' else 'ОЖИДАНИЕ'
    _erase(d,(1128,34,1297,66),'#061B3D',8)
    d.ellipse((1153,44,1169,60),fill=tone)
    _text(d,1181,41,label,16,'#B9CFFF',True)
    # Keep the page header/sidebar controlled by the live application; only
    # navigation highlight, headings and blue artwork are static decorations.
    _panel(d,(33,828,294,975),fill='#051B3D',outline='#067ADE',radius=17)
    d.ellipse((53,853,73,873),fill=tone)
    _text(d,91,846,'Соединение активно' if overall=='connected' else
          'Частичное соединение' if overall=='partial' else 'Ожидание',17,bold=True,max_chars=25)
    _text(d,55,894,'WinWS  ·  Telegram  ·  DNS',16,color=COLORS['sub'])
    d.line((55,925,270,925),fill='#235787',width=1)
    _text(d,55,938,'v'+VERSION+'  /  Windows 10 · 11',14,color=COLORS['sub'])

    if page=='Главная':
        count=sum(bool(getattr(settings,k,False)) for k in ('connect_dpi','connect_telegram','connect_dns'))
        on=sum(getattr(report,k,'off')=='on' for k in ('dpi','telegram','dns'))
        # Replace ALL demo connection information in the central hero.
        _panel(d,(649,270,1190,472),fill='#051C3C',outline='#104D98',radius=22)
        pill='ВСЕ МОДУЛИ ЗАПУЩЕНЫ' if count and on==count else 'ЧАСТЬ МОДУЛЕЙ НЕ РАБОТАЕТ' if is_on else 'ГОТОВО К ПОДКЛЮЧЕНИЮ'
        _panel(d,(650,269,1036,316),fill='#073D42' if count and on==count else '#132E55',outline='#0C796B',radius=18)
        d.ellipse((678,284,696,302),fill=tone)
        _text(d,710,280,pill,18,'#47F0C7' if count and on==count else '#BCD2F9',True,max_chars=31)
        _text(d,653,329,'Обход активен' if is_on else 'Обход отключён',38,bold=True)
        mode=str(getattr(app.controller,'active_dpi_mode',None) or getattr(settings,'dpi_mode','alt_auto'))
        _text(d,653,389,'WinWS · '+ ('AUTO 1–13' if mode=='alt_auto' else mode.upper()),23,COLORS['sub'])
        _text(d,653,431,f'Модули: {on}/{count}  ·  Локальный статус',17,COLORS['sub'])
        # Overlay action button so it always tells truth, retaining visual style.
        _panel(d,(1200,402,1465,464),fill='#1458DB',outline='#4EE0FF',radius=13)
        _text(d,1235,418,'⏻  '+('ОТКЛЮЧИТЬ' if is_on else 'ПОДКЛЮЧИТЬ'),20,bold=True)
        for x,name,enabled in [(464,'dpi',settings.connect_dpi),(828,'telegram',settings.connect_telegram),(1205,'dns',settings.connect_dns)]:
            _module_status(d,x,580,'',enabled and getattr(report,name,'off')=='on')
        # Remove the baked ALT11 detail if current differs.
        _erase(d,(361,644,698,678),'#061A37')
        _text(d,369,647,'Стратегия: '+mode.upper().replace('ALT_AUTO','AUTO 1–13'),16,COLORS['sub'])
        _erase(d,(1123,644,1480,678),'#061A37')
        _text(d,1133,647,('DoH / HTTPS' if settings.dns_mode=='doh' else 'IPv4 DNS')+' · Windows',16,COLORS['sub'])
    elif page=='Диагностика':
        results=dict(getattr(app,'last_results',[]) or [])
        for i,service in enumerate(SERVICE_NAMES):
            _status(d,994,331+i*88,service,results.get(service,'Не проверено'))
    elif page=='История':
        current=getattr(app,'_visual_history_filter','Все события')
        events=recent_events(limit=120)
        patterns={'Подключение':('connection','подключ','winws','telegram','dns','обход'),
                  'Настройки':('setting','настрой','стратег','профил','запуск'),
                  'Ошибки':('error','ошибка','сбой','отказ','не удалось')}
        if current in patterns:
            events=[e for e in events if any(q in (str(e.get('kind',''))+' '+str(e.get('message',''))).lower() for q in patterns[current])]
        # The approved art's sample history is replaced, not shown as user's data.
        _panel(d,(348,343,1486,943),fill='#071B3A',outline='#1665B2',radius=17)
        for i,ev in enumerate(events[:10]):
            y=350+i*56
            if i%2==0:d.rounded_rectangle((358,y,1476,y+53),radius=11,fill='#112D56')
            msg=' '.join(str(ev.get('message','')).split())
            kind=str(ev.get('kind','событие'))
            timestamp=str(ev.get('timestamp',''))
            danger=any(x in (kind+' '+msg).lower() for x in ('ошибка','error','сбой','отказ'))
            clr=COLORS['red'] if danger else COLORS['cyan'] if 'настрой' in msg.lower() else COLORS['green']
            d.ellipse((374,y+18,390,y+34),fill=clr)
            _text(d,413,y+14,timestamp[11:19] or '--:--:--',16,COLORS['sub'])
            _text(d,551,y+10,msg,17,bold=True,max_chars=54)
            _text(d,1133,y+12,'Ошибка' if danger else kind[:24],16,clr,True,max_chars=25)
        if not events:_text(d,617,597,'Событий для этого фильтра пока нет',23,COLORS['sub'])
        _erase(d,(345,942,1460,987),'#06182F')
        _text(d,354,951,f'Запусков сетевой диагностики: {len(load_history())}   |   Показано: {min(len(events),10)} из {len(events)}',15,COLORS['sub'])
        # The segmented control cannot have a baked-in wrong selection.
        filt=[('Все события',352,581),('Подключение',590,844),('Настройки',850,1070),('Ошибки',1080,1290)]
        for name,l,r in filt:
            _panel(d,(l,235,r,286),fill='#1254D4' if name==current else '#061C3C',outline='#1689FF',radius=12)
            _text(d,l+20,249,name,17,bold=name==current)
    elif page=='О проекте':
        _panel(d,(1365,242,1473,282),fill='#073069',outline='#1674C8')
        _text(d,1380,247,'v'+VERSION,17,COLORS['sub'])
        # Component version tags in mockup are illustrative; no claim of v1.0.0 for dependencies.
        for x in (640,1000,1403):
            _erase(d,(x,713,x+75,754),'#09254C',radius=10)
        # The reference's green "installed" labels were illustrative.
        for x,key in ((543,'dpi'),(878,'telegram'),(1230,'dns')):
            _erase(d,(x,787,x+145,819),'#082951',radius=7)
            is_running=getattr(report,key,'off')=='on'
            color=COLORS['green'] if is_running else COLORS['muted']
            _text(d,x+4,792,'Запущен' if is_running else 'Не запущен',13,color,True)
    elif page=='Настройки':
        for y,key in [(381,'launch_at_startup'),(476,'restore_last_mode'),(574,'minimize_to_tray'),(670,'admin_on_launch')]:
            _erase(d,(816,y-7,916,y+48),'#061B3C')
            _switch(d,820,y,bool(getattr(settings,key,False)))
        for y,key in [(381,'connect_dpi'),(487,'connect_telegram'),(594,'connect_dns')]:
            _erase(d,(1376,y-8,1484,y+47),'#061B3C')
            _switch(d,1382,y,bool(getattr(settings,key,False)))
    elif page=='Сеть и стратегии':
        mode=str(settings.dpi_mode)
        # Remove the mock's pre-selected ALT11, repaint every active choice.
        for i,m in enumerate(ALT_MODES):
            row,col=divmod(i,7);x=340+col*92;y=434+row*63
            chosen=m==mode
            _panel(d,(x,y,x+82,y+53),fill='#104FB2' if chosen else '#071C3D',
                   outline='#35D9FF' if chosen else '#2B5EAC',radius=11)
            _text(d,x+18,y+14,m.upper(),16,bold=chosen)
        _panel(d,(790,315,972,367),fill='#1459D4' if mode=='alt_auto' else '#0B2B56',outline='#228BFF',radius=10)
        _text(d,807,329,'АВТО 1–13' if mode=='alt_auto' else mode.upper(),17,bold=True)
        # Correct state of demo auto checkbox.
        _erase(d,(880,596,973,643),'#043C38',radius=7)
        _switch(d,891,599,mode=='alt_auto')
        # Correct selected DNS transport and actual state.
        for x,kind,label,selected in [(1036,'plain','IPv4 DNS',settings.dns_mode=='plain'),
                                      (1265,'doh','DoH / HTTPS',settings.dns_mode=='doh')]:
            _panel(d,(x,431,x+215,497),fill='#124B9A' if selected else '#071C3D',outline='#29B4FF' if selected else '#295788',radius=11)
            _text(d,x+44,451,label,17,bold=selected)
            d.ellipse((x+185,452,x+203,470),fill='#34D2FF' if selected else '#112B54',outline='#54CFFF')
        _erase(d,(1342,325,1491,374),'#08254D')
        _text(d,1361,335,'Активен' if report.dns=='on' else 'Отключён',16,COLORS['green'] if report.dns=='on' else COLORS['muted'],True)
    return im


class HitRegistry:
    """Pointer + keyboard activations go through one ConnectApp registry."""
    def __init__(self,app,scale_x,scale_y):
        self.app=app;self.canvas=app.canvas;self.sx=scale_x;self.sy=scale_y
        self.n=0

    def target(self,rect,callback:Callable,label:str,enabled=True):
        if not enabled:return
        x1,y1,x2,y2=rect
        bounds=(int(x1*self.sx),int(y1*self.sy),int(x2*self.sx),int(y2*self.sy))
        idx=self.app._register_control(bounds,callback,label)
        tag=f'premium_hit_{self.n}';self.n+=1
        # Transparent outlines are Tk hit-tested if the fill is nonempty. Using
        # stipple avoids obscuring raster artwork while creating a reliable hit.
        item=self.canvas.create_rectangle(*bounds,fill='#000001',stipple='gray12',outline='',tags=(tag,))
        self.canvas.tag_bind(tag,'<Button-1>',lambda _e,i=idx:self.app._mouse_activate(i))
        self.canvas.tag_bind(tag,'<Enter>',lambda _e:self.canvas.configure(cursor='hand2'))
        self.canvas.tag_bind(tag,'<Leave>',lambda _e:self.canvas.configure(cursor=''))


def _event_popup(app,index):
    from tkinter import messagebox
    events=recent_events(limit=120)
    current=getattr(app,'_visual_history_filter','Все события')
    filters={'Подключение':('connection','подключ','winws','telegram','dns','обход'),
            'Настройки':('setting','настрой','стратег','профил','запуск'),
            'Ошибки':('error','ошибка','сбой','отказ','не удалось')}
    if current in filters:
        events=[e for e in events if any(t in (str(e.get('kind',''))+' '+str(e.get('message',''))).lower() for t in filters[current])]
    if 0<=index<len(events):
        e=events[index]
        messagebox.showinfo('VORQELI · событие',f"Время: {e.get('timestamp','')}\nТип: {e.get('kind','')}\n\n{e.get('message','')}",parent=app)


def _filter(app,name):
    app._visual_history_filter=name
    app._draw()


def _open_project_link(url):
    # Only existing verified public URLs. No invented Telegram/VK handles.
    webbrowser.open(url)


def draw(app):
    if app._quitting or not app.winfo_exists():return
    canvas=app.canvas
    cw=max(1,canvas.winfo_width());ch=max(1,canvas.winfo_height())
    if cw==1 or ch==1:
        app.after(100,app._draw)
        return
    frame=build_frame(app)
    # The themed scene and hitboxes have the same scale and cannot drift.
    frame=frame.resize((cw,ch),Image.Resampling.LANCZOS)
    app._canvas_bg=ImageTk.PhotoImage(frame)
    canvas.delete('all')
    canvas.configure(cursor='')
    app._controls=[];app._button_images=[];app._widgets=[]
    app._focused_control_index=None
    canvas.create_image(0,0,image=app._canvas_bg,anchor='nw')
    h=HitRegistry(app,cw/W,ch/H)
    # Custom native-feeling titlebar; fixed-size window has no maximize action.
    from .frameless import minimize, begin_move, move, end_move
    h.target((1350,20,1406,77),lambda:minimize(app),'Свернуть')
    drag_box=(int(324*cw/W),int(8*ch/H),int(1120*cw/W),int(76*ch/H))
    drag_tag='premium_window_drag'
    canvas.create_rectangle(*drag_box,fill='#000001',stipple='gray12',outline='',tags=(drag_tag,))
    canvas.tag_bind(drag_tag,'<ButtonPress-1>',lambda e:begin_move(app,e.x_root,e.y_root))
    canvas.tag_bind(drag_tag,'<B1-Motion>',lambda e:move(app,e.x_root,e.y_root))
    canvas.tag_bind(drag_tag,'<ButtonRelease-1>',lambda e:end_move(app))
    h.target((1460,20,1514,77),app._window_close,'Закрыть')
    pages=[('Главная',205,272),('Диагностика',274,341),('История',345,415),('О проекте',418,487),('Настройки',489,559)]
    for page,top,bottom in pages:
        h.target((30,top,298,bottom),lambda p=page:app._page(p),'Раздел: '+page)
    page=app.selected_page
    if page=='Главная':
        on=bool(app.settings.desired_enabled)
        h.target((1198,397,1474,472),app._start_disconnect if on else app._start_connect,
                 'Отключить' if on else 'Подключить',enabled=not getattr(app,'_disconnecting',False))
        h.target((350,521,712,697),lambda:app._page('Сеть и стратегии'),'Настройки WinWS')
        h.target((730,521,1085,697),lambda:app._page('Настройки'),'Настройки Telegram')
        h.target((1106,521,1490,697),lambda:app._page('Сеть и стратегии'),'Настройки GeoHide DNS')
        for rect,callback,label in [((365,811,714,912),lambda:app._page('Диагностика'),'Диагностика'),
                                     ((729,811,1096,912),lambda:app._page('История'),'История событий'),
                                     ((1114,811,1477,912),lambda:app._page('Сеть и стратегии'),'Настройки сети')]:
            h.target(rect,callback,label)
    elif page=='Диагностика':
        h.target((1217,140,1500,217),app._diagnose,'ПРОВЕРИТЬ ВСЁ')
        for i,name in enumerate(SERVICE_NAMES):
            y=315+i*88
            h.target((1271,y,1473,y+76),lambda n=name:app._diagnose_service(n),'ПРОВЕРИТЬ')
        for box,callback,label in [((358,840,728,929),app._show_dns_audit,'DNS / HOSTS'),
                                   ((742,840,1089,929),app._show_engine_logs,'ЖУРНАЛЫ'),
                                   ((1100,840,1475,929),app._show_telegram_web_audit,'TELEGRAM WEB')]:
            h.target(box,callback,label)
    elif page=='История':
        h.target((1260,122,1500,194),app._export_diagnostics,'ЭКСПОРТ JSON')
        for name,left,right in [('Все события',348,581),('Подключение',587,849),
                                ('Настройки',852,1073),('Ошибки',1078,1297)]:
            h.target((left,226,right,294),lambda n=name:_filter(app,n),'Фильтр: '+name)
        shown=recent_events(limit=120)
        filt=getattr(app,'_visual_history_filter','Все события')
        keys={'Подключение':('connection','подключ','winws','telegram','dns','обход'),
              'Настройки':('setting','настрой','стратег','профил','запуск'),
              'Ошибки':('error','ошибка','сбой','отказ','не удалось')}
        if filt in keys:
            shown=[v for v in shown if any(t in (str(v.get('kind',''))+' '+str(v.get('message',''))).lower() for t in keys[filt])]
        for i in range(min(10,len(shown))):
            h.target((350,347+i*56,1484,399+i*56),lambda j=i:_event_popup(app,j),f'Событие {i+1}')
    elif page=='О проекте':
        from tkinter import messagebox
        def unavailable():
            messagebox.showinfo('VORQELI · ссылка',
                'Адрес официального сообщества пока не задан. Добавим его после подтверждения ссылки проекта.',parent=app)
        h.target((340,512,715,608),unavailable,'Канал Telegram')
        h.target((725,512,1090,608),unavailable,'Сообщество VK')
        h.target((1098,512,1483,608),lambda:_open_project_link('https://github.com/Zeihos/VORQELI'),'Исходный код GitHub')
        # Telegram/VK sample graphics remain decorative until official URLs
        # are configured; do not invent project channels.
        h.target((1360,239,1478,290),app._check_updates,'Проверить обновления')
    elif page=='Настройки':
        for y,key in [(373,'launch_at_startup'),(470,'restore_last_mode'),(565,'minimize_to_tray'),(662,'admin_on_launch')]:
            h.target((363,y-24,918,y+69),lambda k=key:app._toggle_setting(k),'Переключить '+key)
        for y,key in [(374,'connect_dpi'),(481,'connect_telegram'),(588,'connect_dns')]:
            h.target((974,y-20,1489,y+83),lambda k=key:app._toggle_setting(k),'Переключить '+key)
        h.target((1189,798,1471,889),lambda:app._page('Сеть и стратегии'),'Открыть настройки сети')
    else:
        h.target((775,300,974,390),lambda:app._set_dpi_mode('alt_auto'),'Автоматическая стратегия DPI')
        for i,mode in enumerate(ALT_MODES):
            row,col=divmod(i,7)
            x=340+col*92;y=434+row*63
            h.target((x,y,x+82,y+53),lambda m=mode:app._set_dpi_mode(m),mode.upper())
        h.target((330,570,976,656),lambda:app._set_dpi_mode('alt_auto'),'Автоматический режим DPI')
        idle=not app.settings.desired_enabled
        h.target((1037,421,1250,508),lambda:app._set_dns_mode('plain'),'IPv4 DNS',enabled=idle)
        h.target((1265,421,1480,508),lambda:app._set_dns_mode('doh'),'DoH HTTPS',enabled=idle)
        h.target((335,757,613,852),lambda:app._page('Диагностика'),'Проверка соединения')
        h.target((620,757,896,852),app._show_dns_audit,'Просмотр текущих параметров')
        h.target((898,757,1170,852),app._show_hosts_manager,'Редактирование HOSTS')
        h.target((1178,757,1480,852),lambda:app._page('Настройки'),'Дополнительные настройки')
        h.target((333,868,698,943),app._restore_dns,'ВОССТАНОВИТЬ DNS')
        h.target((707,868,1080,943),app._show_hosts_manager,'HOSTS / ПРАВИЛА')
        h.target((1091,868,1492,943),lambda:app._page('Настройки'),'К НАСТРОЙКАМ')
    app._sync_scrollbars(cw,ch)
    app._render_focus()
