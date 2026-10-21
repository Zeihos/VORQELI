"""VORQELI Connect v0.39: clickable, state-driven rendering of approved artwork.

The six approved compositions are bundled locally. They are UI *artwork*, not
screenshots of actual status. Real network status, diagnostic results, settings,
version and history are repainted at every frame from the actual controller.
No networking, registry or file mutation happens in this module.
"""
from __future__ import annotations

from functools import lru_cache
from datetime import datetime
import json
from pathlib import Path
from typing import Callable
import webbrowser

from PIL import Image, ImageDraw, ImageFont, ImageTk, ImageFilter

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


def _text(d:ImageDraw.ImageDraw,x:int,y:int,message:object,size=17,color='#F3F8FF',bold=False,max_chars=None,max_width=None):
    val=' '.join(str(message).split())
    font=_font(size,bold)
    if max_chars is not None and len(val)>max_chars:val=val[:max_chars-1]+'…'
    if max_width is not None and d.textbbox((0,0),val,font=font)[2]>max_width:
        while val and d.textbbox((0,0),val+'…',font=font)[2]>max_width:
            val=val[:-1]
        val=val.rstrip()+'…' if val else '…'
    d.text((x,y),val,font=font,fill=color,stroke_width=0)


def _panel(d:ImageDraw.ImageDraw,rect,fill='#081B39',outline='#1F69C3',radius=15):
    d.rounded_rectangle(rect,radius=radius,fill=fill,outline=outline,width=1)


def _erase(d,box,color='#071D3A',radius=6):
    d.rounded_rectangle(box,fill=color,radius=radius)


def _status(d,x,y,name,value):
    """Paint a consistent, compact service badge without a black masking slab."""
    title,color=service_summary(value)
    d.rounded_rectangle((x-3,y+1,x+258,y+39),radius=14,
                        fill='#0A284B',outline='#1D507E',width=1)
    d.ellipse((x+10,y+15,x+24,y+29),fill=color)
    _text(d,x+36,y+9,title,15,color,True,max_width=208)


def _switch(d,x,y,value,enabled=True):
    bg='#086EED' if value else '#14335B'
    if not enabled:bg='#162844'
    d.rounded_rectangle((x,y,x+78,y+38),radius=19,fill=bg,outline='#36CCFF' if value and enabled else '#3C5C8E',width=2)
    px=x+49 if value else x+8
    d.ellipse((px,y+7,px+25,y+32),fill='#F4F7FF')


def _module_status(d,x,y,on):
    color=COLORS['green'] if on else COLORS['muted']
    d.rounded_rectangle((x-4,y-3,x+173,y+35),radius=12,
                        fill='#0A2748',outline='#23517E',width=1)
    d.ellipse((x+8,y+9,x+22,y+23),fill=color)
    _text(d,x+32,y+5,'Запущен' if on else 'Отключён',16,color,True,max_width=135)


def _health(app):
    return app.controller.status()


@lru_cache(maxsize=12)
def artwork(page:str)->Image.Image:
    if page not in ART_FILES:raise ValueError('Недопустимая страница')
    img=Image.open(ASSET_DIR / ART_FILES[page]).convert('RGB')
    if img.size != (W,H):raise ValueError('Неверный размер темы '+page)
    return img


@lru_cache(maxsize=4)
def _live_hero(health:str)->Image.Image:
    """Rebuild the complete hero background and status ring for OFF/PARTIAL/ON.

    The previously approved illustration stays behind the other screens;
    the live hero has no baked green ON ring when the connection is OFF.
    """
    width,height=1147,260
    base=Image.new('RGBA',(width,height),(0,0,0,0))
    mask=Image.new('L',(width,height),0)
    md=ImageDraw.Draw(mask)
    md.rounded_rectangle((0,0,width-1,height-1),radius=27,fill=255)
    fill=Image.new('RGBA',(width,height))
    fd=ImageDraw.Draw(fill)
    for y in range(height):
        # Layered midnight blue with subtle glow around the live emblem.
        for_x=(13+int(9*y/height),35+int(18*y/height),77+int(21*y/height))
        fd.line((0,y,width,y),fill=(*for_x,255))
    background=Image.new('RGBA',(width,height))
    background.paste(fill,(0,0),mask)
    d=ImageDraw.Draw(background,'RGBA')
    d.rounded_rectangle((1,1,width-2,height-2),radius=27,outline='#2787E3',width=2)
    # Soft electric wave strokes remain behind real text.
    for idx in range(14):
        shade=16+(idx%4)*7
        pts=[]
        for x in range(745,width+4,9):
            y=130 + int((idx-7)*7 + 26*__import__('math').sin((x-520)/112 + idx*.19))
            pts.append((x,y))
        d.line(pts,fill=(24,113+shade,231,21+idx%3*11),width=2)
    # Glow is applied only around the new live central emblem.
    aura=Image.new('RGBA',(width,height),(0,0,0,0))
    ad=ImageDraw.Draw(aura)
    tint=(39,231,182) if health=='connected' else (241,178,86) if health=='partial' else (65,135,239)
    for r in (108,83,54):
        ad.ellipse((155-r,130-r,155+r,130+r),outline=(*tint,170),width=7)
    aura=aura.filter(ImageFilter.GaussianBlur(15))
    background=Image.alpha_composite(background,aura)
    d=ImageDraw.Draw(background,'RGBA')
    for r,alpha,thick in ((108,85,1),(91,200,3),(72,250,4)):
        d.ellipse((155-r,130-r,155+r,130+r),outline=(*tint,alpha),width=thick)
    d.ellipse((100,75,210,185),fill=(11,45,109,250),outline=(62,164,252,255),width=3)
    f=_font(78,True)
    bbox=d.textbbox((0,0),'V',font=f)
    d.text((155-(bbox[2]-bbox[0])/2,118-(bbox[3]-bbox[1])/2-bbox[1]),
           'V',font=f,fill='#C0E9FF',stroke_width=1,stroke_fill='#20A5FE')
    return background


def _history_events(app)->list[dict]:
    """Read the actual event schema: event_log uses `action`, not `kind`."""
    events=recent_events(limit=100)
    current=getattr(app,'_visual_history_filter','Все события')
    filters={'Подключение':('connection','подключ','winws','telegram','dns','обход','disconnect'),
             'Настройки':('setting','настрой','стратег','профил','запуск','option'),
             'Ошибки':('error','ошибка','сбой','отказ','не удалось','failed')}
    if current in filters:
        events=[e for e in events if any(t in
                (str(e.get('action',e.get('kind','')))+' '+str(e.get('message',''))).lower()
                for t in filters[current])]
    return events


def export_history(app):
    """Export the history actually on this page, not a diagnostic scan."""
    from tkinter import filedialog, messagebox
    from .log_tools import redact_secrets
    import os
    events=recent_events(limit=100)
    cleaned=[]
    for event in events:
        if isinstance(event,dict):
            cleaned.append({key:redact_secrets(str(value),getattr(app.settings,'telegram_secret',''))
                            for key,value in event.items() if key in ('action','timestamp','message','kind')})
    target=filedialog.asksaveasfilename(parent=app,defaultextension='.json',
        filetypes=[('JSON','*.json')],initialfile='VORQELI-history.json')
    if not target:return
    payload={'version':VERSION,'exported_at':datetime.now().astimezone().isoformat(),
             'limit':100,'events':cleaned}
    path=Path(target)
    temp=path.with_name(path.name+'.v39-export-tmp')
    try:
        temp.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
        temp.replace(path)
    except OSError as exc:
        temp.unlink(missing_ok=True)
        messagebox.showerror('Экспорт истории',str(exc),parent=app)


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
    _panel(d,(33,807,294,975),fill='#051B3D',outline='#067ADE',radius=17)
    d.ellipse((53,853,73,873),fill=tone)
    _text(d,91,846,'Соединение активно' if overall=='connected' else
          'Частичное соединение' if overall=='partial' else 'Ожидание',15,bold=True,max_width=175)
    _text(d,55,894,'WinWS  ·  Telegram  ·  DNS',16,color=COLORS['sub'])
    d.line((55,925,270,925),fill='#235787',width=1)
    _text(d,55,938,'v'+VERSION+'  /  Windows 10 · 11',14,color=COLORS['sub'])

    if page=='Главная':
        count=sum(bool(getattr(settings,k,False)) for k in ('connect_dpi','connect_telegram','connect_dns'))
        on=sum(bool(getattr(settings,'connect_'+key,False)) and getattr(report,key,'off')=='on'
               for key in ('dpi','telegram','dns'))
        status='connected' if count and on==count and overall=='connected' else 'partial' if on else 'off'
        hero=_live_hero(status)
        im.paste(hero,(344,238),hero)
        d=ImageDraw.Draw(im)
        pill='ВСЕ МОДУЛИ ЗАПУЩЕНЫ' if status=='connected' else 'ЧАСТЬ МОДУЛЕЙ АКТИВНА' if status=='partial' else 'ГОТОВО К ПОДКЛЮЧЕНИЮ'
        pill_color=COLORS['green'] if status=='connected' else COLORS['amber'] if status=='partial' else COLORS['sub']
        _panel(d,(647,266,1054,314),fill='#073C41' if status=='connected' else '#122A4B',outline='#178C9D',radius=18)
        d.ellipse((667,284,681,298),fill=pill_color)
        _text(d,696,277,pill,17,pill_color,True,max_width=344)
        _text(d,651,327,'Обход активен' if overall=='connected' else 'Обход частично активен' if overall=='partial' else
              'Обход отключён',36,bold=True,max_width=545)
        mode=str(getattr(app.controller,'active_dpi_mode',None) or getattr(settings,'dpi_mode','alt_auto'))
        mode_label='AUTO 1–13' if mode=='alt_auto' else mode.upper()
        _text(d,653,391,'WinWS · '+mode_label,22,COLORS['sub'],max_width=510)
        _text(d,653,430,f'Модули: {on}/{count}  ·  Локальный статус',16,COLORS['sub'],max_width=505)
        d.rounded_rectangle((1201,400,1464,467),radius=13,fill='#175CE4',outline='#52CBFF',width=2)
        # Draw a universal power glyph, avoiding tofu squares from missing fonts.
        d.arc((1226,417,1253,445),27,332,fill='#FFFFFF',width=3)
        d.line((1240,410,1240,431),fill='#FFFFFF',width=3)
        _text(d,1261,420,'ОТКЛЮЧИТЬ' if is_on else 'ПОДКЛЮЧИТЬ',18,bold=True,max_width=185)
        for x,key in ((464,'dpi'),(828,'telegram'),(1205,'dns')):
            _module_status(d,x,580,getattr(settings,'connect_'+key,False) and getattr(report,key,'off')=='on')
        # Transparent glass footers hide demo ALT11/DoH without black stripes.
        for x,txt,maxw in ((368,'Стратегия: '+mode_label,318),
                            (1132,('DoH / HTTPS' if settings.dns_mode=='doh' else 'IPv4 DNS')+' · Windows',320)):
            d.rounded_rectangle((x-5,644,x+maxw,681),radius=8,fill='#0B264B',outline='#163D68',width=1)
            _text(d,x,651,txt,15,COLORS['sub'],max_width=maxw-16)
    elif page=='Диагностика':
        results=dict(getattr(app,'last_results',[]) or [])
        for i,service in enumerate(SERVICE_NAMES):
            _status(d,994,331+i*88,service,results.get(service,'Не проверено'))
    elif page=='История':
        current=getattr(app,'_visual_history_filter','Все события')
        events=_history_events(app)
        page_number=max(0,int(getattr(app,'_visual_history_page',0)))
        pages=max(1,(len(events)+9)//10)
        page_number=min(page_number,pages-1)
        visible=events[page_number*10:page_number*10+10]
        _panel(d,(348,300,1486,943),fill='#071B3A',outline='#1665B2',radius=17)
        _text(d,374,318,'ВРЕМЯ',15,COLORS['sub'],True)
        _text(d,554,318,'СОБЫТИЕ',15,COLORS['sub'],True)
        _text(d,1135,318,'ТИП СОБЫТИЯ',15,COLORS['sub'],True)
        d.line((365,352,1474,352),fill='#2B5E8A',width=1)
        for i,ev in enumerate(visible):
            y=363+i*54
            if i%2==0:d.rounded_rectangle((358,y,1476,y+52),radius=10,fill='#112B51')
            msg=' '.join(str(ev.get('message','')).split())
            action=str(ev.get('action',ev.get('kind','событие')))
            timestamp=str(ev.get('timestamp',''))
            danger=any(x in (action+' '+msg).lower() for x in ('ошибка','error','сбой','отказ','failed'))
            clr=COLORS['red'] if danger else COLORS['cyan'] if 'настрой' in msg.lower() else COLORS['green']
            d.ellipse((372,y+18,388,y+34),fill=clr)
            _text(d,410,y+14,timestamp[11:19] or '--:--:--',16,COLORS['sub'],max_width=120)
            _text(d,551,y+13,msg or '(пустое событие)',15,bold=True,max_width=552)
            _text(d,1135,y+14,action,15,clr,True,max_width=285)
        if not events:_text(d,570,611,'Пока нет сохранённых событий',22,COLORS['sub'])
        _erase(d,(348,944,1482,988),'#06182F',radius=9)
        _text(d,365,957,f'Сетевых проверок: {len(load_history())}  ·  Событий: {len(events)}',14,COLORS['sub'])
        _text(d,1230,955,f'{page_number+1} / {pages}',15,COLORS['sub'],True)
        for label,l,r in [('‹',1320,1385),('›',1395,1460)]:
            d.rounded_rectangle((l,945,r,981),radius=9,fill='#10305C',outline='#246CAC')
            _text(d,l+22,950,label,17,COLORS['text'],True)
        filt=[('Все события',352,581),('Подключение',590,844),('Настройки',850,1070),('Ошибки',1080,1290)]
        for name,l,r in filt:
            _panel(d,(l,235,r,286),fill='#1254D4' if name==current else '#061C3C',outline='#1689FF',radius=12)
            _text(d,l+20,249,name,17,bold=name==current,max_width=r-l-33)
    elif page=='О проекте':
        _panel(d,(1365,242,1473,282),fill='#073069',outline='#1674C8')
        _text(d,1380,247,'v'+VERSION,17,COLORS['sub'])
        # No invented versions of third-party components. The small badge
        # states the component name; the entire footer is repainted so no
        # baked green "Installed" fragment remains when it is switched OFF.
        for x,label in ((630,'WinWS'),(997,'MTProto'),(1400,'DNS')):
            d.rounded_rectangle((x,708,x+81,758),radius=10,fill='#09264F')
            _text(d,x+9,722,label,14,COLORS['sub'],True,max_width=65)
        for left,right,key in ((340,715,'dpi'),(725,1090,'telegram'),(1106,1480,'dns')):
            d.rounded_rectangle((left+6,781,right-6,819),radius=9,fill='#09264F')
            active=getattr(report,key,'off')=='on'
            color=COLORS['green'] if active else COLORS['muted']
            d.ellipse((left+190,793,left+204,807),fill=color)
            _text(d,left+216,788,'Запущен' if active else 'Не запущен',15,color,True,max_width=130)
        # Do not imply Telegram/VK cards lead to an official account.
        for left,right in ((438,695),(828,1075)):
            d.rounded_rectangle((left,558,right,596),radius=7,fill='#09254B')
            _text(d,left+5,565,'Ссылка ещё не указана',14,COLORS['muted'],max_width=right-left-16)
    elif page=='Настройки':
        for y,key in [(381,'launch_at_startup'),(476,'restore_last_mode'),(574,'minimize_to_tray'),(670,'admin_on_launch')]:
            _erase(d,(805,y-27,925,y+58),'#081D3C',radius=13)
            _switch(d,820,y,bool(getattr(settings,key,False)))
        for y,key in [(381,'connect_dpi'),(487,'connect_telegram'),(594,'connect_dns')]:
            _erase(d,(1365,y-26,1487,y+59),'#081D3C',radius=13)
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
    """Zero-overdraw pointer hitboxes + existing accessible keyboard registry.

    A previous version used black stippled rectangles over every button,
    visibly darkening the approved design and changing its contrast.
    """
    def __init__(self,app,scale_x,scale_y):
        self.app=app;self.canvas=app.canvas;self.sx=scale_x;self.sy=scale_y
        self.targets=[]

    def target(self,rect,callback:Callable,label:str,enabled=True):
        if not enabled:return
        x1,y1,x2,y2=rect
        bounds=(int(x1*self.sx),int(y1*self.sy),int(x2*self.sx),int(y2*self.sy))
        idx=self.app._register_control(bounds,callback,label)
        self.targets.append((bounds,idx))

    def _hit(self,event):
        x=int(self.canvas.canvasx(event.x));y=int(self.canvas.canvasy(event.y))
        for (x1,y1,x2,y2),idx in reversed(self.targets):
            if x1<=x<=x2 and y1<=y<=y2:
                return idx
        return None

    def install(self):
        def click(event):
            idx=self._hit(event)
            if idx is not None:
                self.app._mouse_activate(idx)
                return 'break'
        def motion(event):
            self.canvas.configure(cursor='hand2' if self._hit(event) is not None else '')
        self.canvas.bind('<Button-1>',click,add='+')
        self.canvas.bind('<Motion>',motion)


def _event_popup(app,index):
    from tkinter import messagebox
    events=_history_events(app)
    offset=max(0,int(getattr(app,'_visual_history_page',0)))*10
    if 0<=offset+index<len(events):
        e=events[offset+index]
        messagebox.showinfo('VORQELI · событие',
            f"Время: {e.get('timestamp','')}\nТип: {e.get('action',e.get('kind',''))}\n\n{e.get('message','')}",parent=app)


def _history_turn(app,step):
    count=len(_history_events(app))
    pages=max(1,(count+9)//10)
    current=max(0,int(getattr(app,'_visual_history_page',0)))
    app._visual_history_page=min(pages-1,max(0,current+step))
    app._draw()


def _filter(app,name):
    app._visual_history_filter=name
    app._visual_history_page=0
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
    canvas.create_image(0,0,image=app._canvas_bg,anchor='nw')
    h=HitRegistry(app,cw/W,ch/H)
    # Custom native-feeling titlebar; fixed-size window has no maximize action.
    from .frameless import minimize, begin_move, move, end_move
    h.target((1350,20,1406,77),lambda:minimize(app),'Свернуть')
    drag_box=(int(324*cw/W),int(8*ch/H),int(1120*cw/W),int(76*ch/H))
    drag_tag='premium_window_drag'
    # Bind drag to the actual canvas: no translucent rectangle over the header.
    def topbar(event):
        x,y=int(canvas.canvasx(event.x)),int(canvas.canvasy(event.y))
        return drag_box[0]<=x<=drag_box[2] and drag_box[1]<=y<=drag_box[3]
    def start_drag(event):
        if topbar(event):begin_move(app,event.x_root,event.y_root)
    def step_drag(event):
        if getattr(app,'_frameless_mouse',None) is not None:
            move(app,event.x_root,event.y_root)
    canvas.bind('<ButtonPress-1>',start_drag)
    canvas.bind('<B1-Motion>',step_drag)
    canvas.bind('<ButtonRelease-1>',lambda event:end_move(app))
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
        h.target((1260,122,1500,194),lambda:export_history(app),'ЭКСПОРТ ИСТОРИИ JSON')
        for name,left,right in [('Все события',348,581),('Подключение',587,849),
                                ('Настройки',852,1073),('Ошибки',1078,1297)]:
            h.target((left,226,right,294),lambda n=name:_filter(app,n),'Фильтр: '+name)
        shown=_history_events(app)
        page_number=min(max(0,int(getattr(app,'_visual_history_page',0))),max(0,(len(shown)-1)//10))
        for i in range(min(10,len(shown[page_number*10:page_number*10+10]))):
            h.target((350,363+i*54,1484,415+i*54),lambda j=i:_event_popup(app,j),f'Событие {i+1}')
        if page_number>0:h.target((1320,945,1385,981),lambda:_history_turn(app,-1),'Предыдущая страница истории')
        if (page_number+1)*10<len(shown):h.target((1395,945,1460,981),lambda:_history_turn(app,1),'Следующая страница истории')
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
    h.install()
    app._sync_scrollbars(cw,ch)
    app._render_focus()
