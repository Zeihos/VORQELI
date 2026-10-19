"""VORQELI Connect — polished Windows Canvas visual system.

Visual-only module: invokes existing ConnectApp actions and reads their state.
Never mutates network, DNS, HOSTS, startup, privileges, or Windows registry.
Image resources stay in memory and all hit targets enter the existing
keyboard/accessibility registry. No fake settings or fabricated health checks.
"""
from __future__ import annotations

import math
import webbrowser
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFilter, ImageTk

from . import __version__ as VERSION
from .event_log import recent_events
from .flowseal_alts import ALT_MODES
from .history import load_history

PAGES = ('Главная', 'Диагностика', 'История', 'О проекте', 'Настройки', 'Сеть и стратегии')
SERVICE_NAMES = ('Discord', 'YouTube', 'Telegram Web', 'ChatGPT', 'Microsoft (Copilot, Designer, Xbox)')

# Palette deliberately desaturated away from the previous flat violet theme.
BG = '#070E1C'
RAIL = '#0B1830'
CARD = '#101F38'
CARD_HOVER = '#1A3155'
STROKE = '#2B4264'
TEXT = '#F3F7FF'
MUTED = '#9BAECC'
DIM = '#6D83A6'
BLUE = '#7093FF'
BLUE_BRIGHT = '#9CB5FF'
GREEN = '#43E4B4'
AMBER = '#F9C377'
RED = '#FF8C9D'
CYAN = '#59C7EF'

# Renderer stays useful on old 1060x710 minimum windows. On smaller physical
# screens app._sync_scrollbars provides safe, explicit scrolling.
MIN_WIDTH, MIN_HEIGHT = 1060, 710
LEFT, HEADER = 236, 79
PAD = 30


def status_tone(state: str) -> str:
    return {'on': GREEN, 'connected': GREEN, 'partial': AMBER,
            'error': RED, 'off': DIM}.get(state, MUTED)


def service_summary(value: str) -> tuple[str, str]:
    """2xx/3xx probe success is HTTPS only, not usable account access."""
    if value == 'Доступен':
        return ('HTTPS OK', GREEN)
    if value == 'Не проверено':
        return ('Не проверено', DIM)
    if 'Copilot:' in value:
        parts = [p.strip() for p in value.split('|')]
        oks = sum(p.endswith(': OK') for p in parts)
        if len(parts) == 3 and oks == 3:
            return ('3/3 HTTPS OK', GREEN)
        if oks:
            return ('Частичный ответ', AMBER)
        return ('Нет полного ответа', RED)
    if value.startswith('HTTP '):
        return (value + ' · ограничение', AMBER)
    if value == 'Нет ответа':
        return ('Нет ответа', RED)
    return (str(value)[:32], AMBER)


def _rgb(color: str) -> tuple[int, int, int]:
    return tuple(int(color[k:k+2], 16) for k in (1,3,5))


def _blend(c1: str, c2: str, t: float) -> tuple[int, int, int]:
    a, b = _rgb(c1), _rgb(c2)
    return tuple(round(x*(1-t)+y*t) for x,y in zip(a,b))


def _gradient(canvas: Image.Image, rectangle: tuple[int,int,int,int],
              top: str, bottom: str, radius: int = 18, outline: str | None = STROKE):
    """Antialiased rounded gradient, not flat Tk rectangle approximations."""
    x1,y1,x2,y2 = map(int, rectangle)
    if x2 <= x1 or y2 <= y1:
        return
    ww, hh = x2-x1, y2-y1
    field = Image.new('RGBA',(ww,hh))
    ink = ImageDraw.Draw(field)
    for y in range(hh):
        t = y/max(1,hh-1)
        ink.line((0,y,ww,y),fill=(*_blend(top,bottom,t),255))
    mask = Image.new('L',(ww,hh),0)
    ImageDraw.Draw(mask).rounded_rectangle((0,0,ww-1,hh-1),radius=max(0,min(radius,ww//2,hh//2)),fill=255)
    canvas.paste(field,(x1,y1),mask)
    if outline:
        ImageDraw.Draw(canvas).rounded_rectangle((x1,y1,x2-1,y2-1),radius=radius,
                outline=outline,width=1)


def _glows(canvas: Image.Image, circles: tuple[tuple[float,float,float,str,int],...], blur=55):
    # Quarter-sized blur: fast even on 4K logical scaling. Composite once.
    w,h = canvas.size
    scale=4
    glow=Image.new('RGBA',(w//scale+2,h//scale+2),(0,0,0,0))
    draw=ImageDraw.Draw(glow,'RGBA')
    for cx,cy,r,color,alpha in circles:
        c=_rgb(color)
        x,y,s=cx/scale,cy/scale,r/scale
        draw.ellipse((x-s,y-s,x+s,y+s),fill=(*c,alpha))
    glow=glow.filter(ImageFilter.GaussianBlur(max(1,blur/scale))).resize((w,h),Image.Resampling.BILINEAR)
    canvas.alpha_composite(glow)


def _hero_decoration(canvas: Image.Image, x1: int,y1:int,x2:int,y2:int):
    """Subtle cropped accent waves (never bleed outside cards or over labels)."""
    w=x2-x1
    layer=Image.new('RGBA',(w,y2-y1),(0,0,0,0))
    d=ImageDraw.Draw(layer,'RGBA')
    for i in range(5):
        coords=[]
        for step in range(64):
            t=step/63
            px=round(w*t)
            py=layer.height-18-i*7-round(math.sin(t*math.pi*2.1+i*.23)*3)
            coords.append((px,py))
        d.line(coords,fill=(105,158,255,15+i*8),width=2)
    # Halo under the V emblem, blurred before compositing the crisp ring in Tk.
    halo=Image.new('RGBA',layer.size,(0,0,0,0))
    hd=ImageDraw.Draw(halo,'RGBA')
    hd.ellipse((13,17,158,162),fill=(*_rgb(GREEN),88))
    halo=halo.filter(ImageFilter.GaussianBlur(26))
    layer=Image.alpha_composite(halo,layer)
    mask=Image.new('L',layer.size,0)
    ImageDraw.Draw(mask).rounded_rectangle((0,0,layer.width-1,layer.height-1),radius=22,fill=255)
    effective=Image.new('L',layer.size,0)
    from PIL import ImageChops
    effective=ImageChops.multiply(mask,layer.getchannel('A'))
    canvas.paste(layer,(x1,y1),effective)


def _section_card(canvas: Image.Image, rect, *, kind='regular', radius=18):
    themes={'regular':('#13243F','#0F1D33','#273F60'),
            'highlight':('#173564','#101F3F','#4775CC'),
            'rail':('#162946','#101D33','#2A4369'),
            'active':('#1E3F72','#14284A','#4F7BD8'),
            'soft':('#152845','#10213A','#294566')}
    top,bottom,stroke=themes.get(kind,themes['regular'])
    _gradient(canvas,rect,top,bottom,radius,stroke)


def _pill_background(canvas:Image.Image,rect,kind='quiet'):
    top,bottom={'quiet':('#1C3558','#182B48'),
                'active':('#244C88','#1D3767'),
                'positive':('#15493E','#123D35'),
                'warning':('#594328','#403624')}.get(kind,('#1C3558','#182B48'))
    _gradient(canvas,rect,top,bottom,13,None)


@lru_cache(maxsize=14)
def background(width:int,height:int,page:str) -> Image.Image:
    """Image-backed, scene-cached art direction for all six pages."""
    w,h=max(MIN_WIDTH,width),max(MIN_HEIGHT,height)
    image=Image.new('RGBA',(w,h),BG)
    painter=ImageDraw.Draw(image)
    for y in range(h):
        t=y/max(h-1,1)
        painter.line((0,y,w,y),fill=(*_blend('#070E1D','#0D1D34',t),255),width=1)
    _glows(image, ((w*.78,65,245,BLUE,80),(w*.55,h*.83,230,CYAN,25),
                   (w*.12,h*.22,195,'#2B71DE',15)),blur=85)
    painter=ImageDraw.Draw(image,'RGBA')
    painter.rectangle((0,0,LEFT,h),fill=(8,20,40,249))
    painter.line((LEFT,0,LEFT,h),fill=(78,113,168,82))
    painter.rectangle((LEFT,0,w,HEADER),fill=(10,20,38,216))
    painter.line((LEFT,HEADER,w,HEADER),fill=(85,120,180,70))
    painter.line((LEFT+25,h-39,w-26,h-39),fill=(83,124,178,68))
    x,r=LEFT+PAD,w-PAD
    if page=='Главная':
        # Hero receives its own glow/wave for an unmistakable premium focal area.
        _section_card(image,(x,193,r,378),kind='highlight',radius=22)
        _hero_decoration(image,x+1,194,r-1,377)
        cw=(r-x-24)//3
        for j in range(3):
            sx=x+j*(cw+12)
            _section_card(image,(sx,391,sx+cw,506),kind='regular',radius=17)
        _section_card(image,(x,520,r,h-59),kind='regular',radius=19)
    elif page=='Диагностика':
        _section_card(image,(x,185,r,h-58),kind='regular',radius=19)
        for i in range(5):
            py=239+i*61
            _section_card(image,(x+20,py,r-20,py+54),kind='soft',radius=12)
        _section_card(image,(x+20,566,r-20,h-76),kind='rail',radius=13)
    elif page=='История':
        _section_card(image,(x,185,r,h-58),kind='regular',radius=19)
        _section_card(image,(x+20,254,r-20,h-83),kind='soft',radius=14)
        for i in range(8):
            py=319+i*45
            if py+38 < h-88 and i%2==0:
                _pill_background(image,(x+28,py,r-28,py+38),'quiet')
    elif page=='О проекте':
        _section_card(image,(x,193,r,337),kind='highlight',radius=20)
        _section_card(image,(x,350,r,525),kind='regular',radius=17)
        _section_card(image,(x,538,r,h-58),kind='regular',radius=17)
    elif page=='Настройки':
        total=r-x
        l=int(total*.54)
        _section_card(image,(x,192,x+l-7,h-177),kind='regular',radius=19)
        _section_card(image,(x+l+7,192,r,h-177),kind='regular',radius=19)
        _section_card(image,(x,h-164,r,h-58),kind='highlight',radius=19)
    else:
        total=r-x
        l=int(total*.636)
        _section_card(image,(x,192,x+l-7,519),kind='regular',radius=19)
        _section_card(image,(x+l+7,192,r,519),kind='regular',radius=19)
        _section_card(image,(x,533,r,h-58),kind='regular',radius=19)
    return image.convert('RGB')


def _label_for_module(actual:str,selected:bool)->str:
    if not selected:return 'Отключён в настройках'
    return {'on':'Запущен','off':'Не запущен','error':'Требует внимания'}.get(actual,'Ожидание')


@lru_cache(maxsize=32)
def _service_icon(kind:str,size:int=42)->Image.Image:
    """Original vector pictograms, no external icon fonts or network requests."""
    s=size*3
    image=Image.new('RGBA',(s,s),(0,0,0,0))
    d=ImageDraw.Draw(image)
    c={'discord':'#657DFF','youtube':'#FF435A','telegram':'#25A8E8',
       'chatgpt':'#20BFA2','microsoft':'#6387EB','dpi':'#13BDA7','dns':'#648AFF',
       'github':'#8BA7DC','info':'#6999EC','settings':'#7B91FF','history':'#5E96E9'}.get(kind,'#5C81D7')
    d.rounded_rectangle((0,0,s-1,s-1),radius=s//4,fill=c)
    white=(248,251,255,255)
    def xy(a):return tuple(int(v*s/100) for v in a)
    if kind=='youtube':
        d.rounded_rectangle(xy((15,28,85,72)),radius=s//9,fill=white)
        d.polygon([xy((44,36)),xy((44,65)),xy((66,50))],fill=c)
    elif kind=='telegram':
        d.polygon([xy((18,50)),xy((82,19)),xy((65,82)),xy((47,62))],fill=white)
        d.line((xy((47,62)),xy((76,28))),fill=c,width=max(2,s//24))
    elif kind=='discord':
        d.rounded_rectangle(xy((20,34,80,68)),radius=s//8,fill=white)
        d.polygon([xy((29,64)),xy((20,79)),xy((41,66))],fill=white)
        for xx in (42,62):d.ellipse(xy((xx-5,47,xx+5,57)),fill=c)
    elif kind=='microsoft':
        for xx,yy in ((22,22),(53,22),(22,53),(53,53)):
            d.rectangle(xy((xx,yy,xx+23,yy+23)),fill=white)
    elif kind=='chatgpt':
        # Interlocking rounded geometric symbol rather than copying a logo asset.
        d.ellipse(xy((22,21,78,79)),outline=white,width=max(3,s//12))
        d.arc(xy((31,31,69,69)),30,295,fill=c,width=max(3,s//12))
    elif kind=='dpi':
        d.polygon([xy((52,16)),xy((29,55)),xy((48,55)),xy((39,85)),xy((76,43)),xy((55,43))],fill=white)
    elif kind=='dns':
        d.ellipse(xy((18,18,82,82)),outline=white,width=max(3,s//17))
        d.arc(xy((38,19,62,82)),95,275,fill=white,width=max(3,s//18))
        d.line((xy((20,50)),xy((80,50))),fill=white,width=max(3,s//19))
    elif kind=='settings':
        d.ellipse(xy((26,26,74,74)),outline=white,width=max(3,s//10))
        d.ellipse(xy((42,42,58,58)),fill=white)
    elif kind=='history':
        d.ellipse(xy((22,22,78,78)),outline=white,width=max(3,s//12))
        d.line([xy((49,33)),xy((49,52)),xy((66,60))],fill=white,width=max(3,s//14))
    else:
        d.ellipse(xy((29,29,71,71)),outline=white,width=max(3,s//12))
        d.line((xy((50,43)),xy((50,68))),fill=white,width=max(3,s//10))
    return image.resize((size,size),Image.Resampling.LANCZOS)


class Painter:
    """Semantic controls, pixel-aligned canvas labels, and keyboard navigation."""
    def __init__(self,app):
        self.app=app
        self.canvas=app.canvas
        self.w,self.h=app._logical_size
        self.x,self.r=LEFT+PAD,self.w-PAD
        self.cw=self.r-self.x

    def txt(self,x,y,value,size=11,color=TEXT,*,bold=False,anchor='nw',width=0):
        return self.app._text(x,y,str(value),size,color,anchor=anchor,width=width,
                              weight='bold' if bold else 'normal')

    def line(self,x1,y1,x2,y2,color=STROKE):
        self.canvas.create_line(x1,y1,x2,y2,fill=color)

    def dot(self,x,y,color=GREEN,r=4):
        self.canvas.create_oval(x-r,y-r,x+r,y+r,fill=color,outline='')

    def icon(self,x,y,kind,size=38):
        icon=ImageTk.PhotoImage(_service_icon(kind,size))
        self.app._button_images.append(icon)  # image lifetime is bound to the redraw
        self.canvas.create_image(x,y,image=icon,anchor='nw')

    def badge(self,x,y,value,*,tone='quiet',width=None):
        colors={'quiet':MUTED,'positive':GREEN,'warning':AMBER,'negative':RED,'active':BLUE_BRIGHT}
        color=colors.get(tone,MUTED)
        w=width or max(95,round(len(value)*6.4)+22)
        self.canvas.create_polygon(self.app._rounded_coords(x,y,x+w,y+27,12),
                smooth=True,splinesteps=10,fill={
                'positive':'#124336','warning':'#4A382A','negative':'#49303E',
                'active':'#263F73'}.get(tone,'#1A2D49'),outline='',width=0)
        self.txt(x+w//2,y+13,value,9,color,bold=True,anchor='center')
        return w

    def button(self,x,y,w,h,text,callback,*,primary=False,disabled=False,
               icon=None,selected=False,small=False):
        """Custom controlled surface; no clickable decorative placeholders."""
        if w < 38 or h < 24:return
        a=self.app
        serial=a._control_serial
        a._control_serial+=1
        tag=f'prod_ui_{serial}'
        color=('#6C8DFA' if primary or selected else '#1B3558')
        border=('#B0C4FF' if primary or selected else '#34537C')
        if disabled: color,border='#1A2940','#2A3B53'
        item=self.canvas.create_polygon(a._rounded_coords(x,y,x+w,y+h,min(14,h//3)),
              smooth=True,splinesteps=12,fill=color,outline=border,width=1,tags=(tag,))
        content=text
        if icon:content=icon+'  '+text
        self.canvas.create_text(x+w/2,y+h/2,text=content,anchor='center',
             fill='#0A1430' if primary or selected else (DIM if disabled else TEXT),
             font=('Segoe UI',9 if small else 10,'bold'),tags=(tag,))
        if not disabled:
            index=a._register_control((x,y,x+w,y+h),callback,text)
            self.canvas.tag_bind(tag,'<Button-1>',lambda e,n=index:a._mouse_activate(n))
            self.canvas.tag_bind(tag,'<Enter>',lambda e,i=item,p=primary or selected:self.hover(i,True,p))
            self.canvas.tag_bind(tag,'<Leave>',lambda e,i=item,p=primary or selected:self.hover(i,False,p))
        return item

    def hover(self,item,on,primary):
        self.canvas.itemconfigure(item,fill=('#94ACFF' if on else '#6C8DFA') if primary else
                                            ('#294A78' if on else '#1B3558'))
        self.canvas.configure(cursor='hand2' if on else '')

    def switch(self,x,y,checked,action,*,disabled=False):
        """Clickable modern pill switch with visible thumb, registered for Tab."""
        a=self.app; w,h=52,28
        tag=f'prod_switch_{a._control_serial}';a._control_serial+=1
        self.canvas.create_polygon(a._rounded_coords(x,y,x+w,y+h,14),
              smooth=True,splinesteps=12,fill=('#577EFD' if checked else '#304765'),
              outline='#6A88BA' if checked else '#48607D',tags=(tag,))
        center=(x+37 if checked else x+15,y+14)
        self.canvas.create_oval(center[0]-10,center[1]-10,center[0]+10,center[1]+10,
                 fill='#F6F9FF',outline='',tags=(tag,))
        if not disabled:
            index=a._register_control((x,y,x+w,y+h),action,'Переключатель')
            self.canvas.tag_bind(tag,'<Button-1>',lambda e,n=index:a._mouse_activate(n))
            self.canvas.tag_bind(tag,'<Enter>',lambda e:self.canvas.configure(cursor='hand2'))
            self.canvas.tag_bind(tag,'<Leave>',lambda e:self.canvas.configure(cursor=''))

    def preference(self,x,y,w,title,detail,checked,action,*,last=False):
        self.txt(x,y,title,11,bold=True)
        self.txt(x,y+24,detail,9,MUTED,width=max(110,w-79))
        self.switch(x+w-59,y+3,checked,action)
        if not last:self.line(x,y+61,x+w-4,y+61)

    def header(self,title,subtitle,*,eyebrow=None):
        # Eyebrow lives on every page for a consistent information hierarchy.
        self.txt(self.x,98,eyebrow or 'VORQELI  /  WINDOWS',9,BLUE_BRIGHT,bold=True)
        self.txt(self.x,120,title,24,bold=True)
        self.txt(self.x,159,subtitle,10,MUTED,width=self.cw-20)

    def chrome(self):
        a=self.app
        # Brand mark and sidebar spacing match concept more closely.
        self.canvas.create_polygon(a._rounded_coords(26,25,79,78,14),
            smooth=True,splinesteps=12,fill='#6C8FFF',outline='#91A9FF',width=1)
        self.txt(52,51,'V',27,'#08162C',bold=True,anchor='center')
        self.txt(89,26,'VORQELI',17,bold=True)
        self.txt(90,50,'CONNECT',10,MUTED,bold=True)
        self.line(22,101,214,101)
        self.txt(28,121,'НАВИГАЦИЯ',9,DIM,bold=True)
        nav=(('Главная','⌂'),('Диагностика','◇'),('История','◷'),
             ('О проекте','?'),('Настройки','⚙'))
        for i,(page,glyph) in enumerate(nav):
            y=151+i*54
            active=(a.selected_page==page or page=='Настройки' and a.selected_page=='Сеть и стратегии')
            # Draw a left active indicator and embedded nav surface, not oversized
            # saturated blue buttons used in the previous failed v0.37 design.
            tag=f'nav_{i}'
            if active:
                self.canvas.create_polygon(a._rounded_coords(18,y,220,y+43,11),
                         smooth=True,splinesteps=12,fill='#244373',outline='#375A90',tags=(tag,))
                self.canvas.create_rectangle(17,y+6,21,y+37,fill=BLUE,outline='',tags=(tag,))
            glyph_id=self.txt(40,y+21,glyph,18,BLUE_BRIGHT if active else '#7188AA',anchor='w')
            label_id=self.txt(84,y+21,page,11,TEXT if active else MUTED,bold=active,anchor='w')
            # Foreground text must share the same clickable tag.
            self.canvas.addtag_withtag(tag,glyph_id)
            self.canvas.addtag_withtag(tag,label_id)
            index=a._register_control((18,y,220,y+43),lambda n=page:a._page(n),page)
            self.canvas.tag_bind(tag,'<Button-1>',lambda e,n=index:a._mouse_activate(n))
            self.canvas.tag_bind(tag,'<Enter>',lambda e:self.canvas.configure(cursor='hand2'))
            self.canvas.tag_bind(tag,'<Leave>',lambda e:self.canvas.configure(cursor=''))
        bottom=self.h-151
        self.canvas.create_polygon(a._rounded_coords(21,bottom,216,bottom+98,14),
            smooth=True,splinesteps=10,fill='#14253E',outline='#304D73')
        report=a.controller.status()
        state=report.overall if a.settings.desired_enabled else 'off'
        self.dot(37,bottom+22,status_tone(state),5)
        self.txt(52,bottom+15,'Соединение активно' if state=='connected' else
                 'Часть модулей' if state=='partial' else 'Требует внимания' if state=='error'
                 else 'Режим ожидания',10,bold=True)
        self.txt(36,bottom+43,'WinWS  ·  Telegram  ·  DNS',9,MUTED)
        self.txt(35,bottom+70,'v'+VERSION+'   /   Windows 10 · 11',9,DIM)
        self.txt(self.x,29,'VORQELI   /   NETWORK CONTROL',10,MUTED,bold=True)
        self.dot(self.r-128,41,status_tone(state),4)
        self.txt(self.r-115,33,'АКТИВЕН' if state=='connected' else
                 'ЧАСТИЧНО' if state=='partial' else 'ОШИБКА' if state=='error' else 'ОЖИДАНИЕ',9,MUTED,bold=True)
        self.txt(self.x,self.h-29,'VORQELI Connect  ·  Локальное приложение',9,DIM)
        self.txt(self.r,self.h-29,'WINDOWS 10 / 11',9,DIM,anchor='ne')

    def home(self):
        a=self.app
        report=a.controller.status(); active=a.settings.desired_enabled
        busy=a.running_job or a._disconnecting
        state=report.overall if active else 'off'
        self.header('Управление подключением','Все важные сетевые инструменты — в одном окне',eyebrow='01  /  ГЛАВНАЯ')
        hx,hy=self.x,193
        # Functional visually expressive halo, not a fake VPN connection indicator.
        cx,cy=hx+94,286
        for rr,cc,width in ((76,'#31568A',2),(65,'#4977BE',2),(54,status_tone(state),4)):
            self.canvas.create_oval(cx-rr,cy-rr,cx+rr,cy+rr,outline=cc,width=width)
        self.canvas.create_oval(cx-42,cy-42,cx+42,cy+42,fill='#254981',outline=BLUE,width=2)
        self.txt(cx,cy,'V',34,BLUE_BRIGHT,bold=True,anchor='center')
        tx=hx+187
        title=('Отключение…' if a._disconnecting else 'Обход активен' if state=='connected' else
                'Частичное подключение' if state=='partial' else 'Подключение не удалось' if state=='error'
                else 'Подключение…' if busy else 'Готов к подключению')
        self.badge(tx,213, '●  ВСЕ МОДУЛИ ЗАПУЩЕНЫ' if state=='connected' else
                           '●  НЕ ВСЕ МОДУЛИ РАБОТАЮТ' if state in ('partial','error')
                           else '●  ОЖИДАНИЕ ПОДКЛЮЧЕНИЯ',tone='positive' if state=='connected'
                           else 'warning' if state in ('partial','error') else 'quiet',width=229)
        self.txt(tx,256,title,19,bold=True,width=max(200,self.cw-385))
        strategy=(a.controller.active_dpi_mode or a.settings.dpi_mode).upper()
        self.txt(tx,291,'WinWS · '+('Авто 1–13' if strategy=='ALT_AUTO' else strategy),10,MUTED)
        selected=sum((a.settings.connect_dpi,a.settings.connect_telegram,a.settings.connect_dns))
        count=sum(getattr(report,k)=='on' for k in ('dpi','telegram','dns'))
        self.txt(tx,315,f'Модули: {count}/{selected}  ·  '+('Соединение проверяется' if busy else 'Локальный статус'),9,MUTED)
        self.button(self.r-192,305,167,46,'ОТКЛЮЧИТЬ' if active else 'ПОДКЛЮЧИТЬ',
                    a._start_disconnect if active else a._start_connect,primary=not active,
                    disabled=a._disconnecting or (busy and not active))
        cw=(self.cw-24)//3
        cards=[('DPI / WinWS','dpi','dpi','Стратегия: '+strategy,a.settings.connect_dpi),
               ('Telegram','telegram','telegram','MTProto / прокси',a.settings.connect_telegram),
               ('GeoHide DNS','dns','dns','DoH · HTTPS' if a.settings.dns_mode=='doh' else
                'IPv4 DNS · Windows',a.settings.connect_dns)]
        for i,(name,kind,key,detail,enabled) in enumerate(cards):
            xx=hx+i*(cw+12)
            self.icon(xx+16,404,kind,43)
            self.txt(xx+70,405,name,11,bold=True)
            actual=getattr(report,key)
            tone=status_tone(actual if enabled else 'off')
            self.dot(xx+73,440,tone,4)
            self.txt(xx+85,432,_label_for_module(actual,enabled),9,tone,bold=True,width=max(110,cw-95))
            self.txt(xx+17,478,detail,9,MUTED,width=cw-30)
        self.txt(hx+23,541,'Быстрые действия',14,bold=True)
        self.txt(hx+23,568,'Подключение, диагностика и параметры подключения',9,MUTED)
        available=self.cw-46
        bw=(available-18)//3
        opts=[('Диагностика',lambda:a._page('Диагностика')),
              ('История событий',lambda:a._page('История')),
              ('Настройки сети',lambda:a._page('Сеть и стратегии'))]
        for j,(label,callback) in enumerate(opts):
            self.button(hx+23+j*(bw+9),self.h-126,bw,43,label,callback)
        if state in ('partial','error'):
            self.txt(hx+25,self.h-78,str(a.detail).replace('\n',' ')[:112],9,AMBER,width=self.cw-50)
        else:
            self.txt(hx+25,self.h-78,'Проверка сайтов находится в разделе «Диагностика».',9,DIM)

    def diagnostics(self):
        a=self.app
        self.header('Диагностика сети','Реальные HTTPS-ответы. Статус не подтверждает вход в аккаунт.',eyebrow='02  /  ДИАГНОСТИКА')
        self.button(self.r-173,112,170,42,'◌  ПРОВЕРИТЬ ВСЁ',a._diagnose,
                    primary=True,disabled=a.running_job,small=True)
        self.txt(self.x+23,203,'ДОСТУПНОСТЬ СЕРВИСОВ',10,BLUE_BRIGHT,bold=True)
        result=dict(a.last_results or ())
        for i,(title,key,kind) in enumerate((
            ('Discord','Discord','discord'),('YouTube','YouTube','youtube'),
            ('Telegram','Telegram Web','telegram'),('ChatGPT','ChatGPT','chatgpt'),
            ('Microsoft','Microsoft (Copilot, Designer, Xbox)','microsoft'))):
            y=239+i*61
            self.icon(self.x+31,y+8,kind,38)
            self.txt(self.x+82,y+7,title,12,bold=True)
            self.txt(self.x+82,y+31,'Copilot · Designer · Xbox' if title=='Microsoft'
                     else 'Telegram Web · HTTPS' if title=='Telegram' else 'HTTPS-проверка сервиса',9,MUTED)
            value=result.get(key,'Не проверено')
            summary,tone=service_summary(value)
            self.dot(self.r-288,y+27,tone,4)
            self.txt(self.r-277,y+19,summary,9,tone,bold=True,width=137)
            self.button(self.r-139,y+10,113,34,'ПРОВЕРИТЬ',lambda n=key:a._diagnose_service(n),
                        disabled=a.running_job,small=True)
        self.txt(self.x+25,544,'СЕТЕВЫЕ ИНСТРУМЕНТЫ',10,BLUE_BRIGHT,bold=True)
        labels=(('DNS / HOSTS',a._show_dns_audit),('ЖУРНАЛЫ',a._show_engine_logs),
                ('TELEGRAM WEB',a._show_telegram_web_audit))
        bw=(self.cw-80)//3
        for j,(name,fn) in enumerate(labels):
            self.button(self.x+30+j*(bw+9),584,bw,43,name,fn,small=True)
        self.txt(self.x+25,self.h-76,'Microsoft показывается одной категорией; внутри проверяются 3 адреса.',9,MUTED,width=self.cw-55)

    def history(self):
        a=self.app
        self.header('История действий','Локальный журнал событий программы и проверок соединения',eyebrow='03  /  ИСТОРИЯ')
        self.button(self.r-171,112,163,41,'ЭКСПОРТ JSON',a._export_diagnostics,
                    disabled=not bool(a.last_results),small=True)
        # All tabs are interactive; the filter genuinely changes visible rows.
        allowed=('Все события','Подключение','Настройки','Ошибки')
        current=getattr(a,'_visual_history_filter','Все события')
        for j,name in enumerate(allowed):
            self.button(self.x+23+j*141,201,132,36,name,
                       lambda n=name:self.change_history_filter(n),selected=current==name,small=True)
        self.txt(self.x+30,276,'ВРЕМЯ',9,DIM,bold=True)
        self.txt(self.x+166,276,'СОБЫТИЕ',9,DIM,bold=True)
        self.txt(self.r-170,276,'ИСТОЧНИК',9,DIM,bold=True)
        events=recent_events(limit=80)
        for_filter={'Подключение':('connection','подключ','обход','отключ'),
                    'Настройки':('settings','настро','профил','режим'),
                    'Ошибки':('error','ошиб','не удалось','сбой')}
        if current in for_filter:
            keywords=for_filter[current]
            events=[e for e in events if any(k in (str(e.get('kind',''))+' '+str(e.get('message',''))).lower() for k in keywords)]
        cap=max(2,min(8,(self.h-398)//46))
        if not events:self.txt(self.x+40,340,'Нет событий для выбранного фильтра.',12,MUTED)
        for i,event in enumerate(events[:cap]):
            y=317+i*45
            text=str(event.get('message','')).replace('\n',' ')
            ts=str(event.get('timestamp',''))
            self.dot(self.x+39,y+19,RED if any(k in text.lower() for k in ('ошибка','сбой')) else BLUE,3)
            self.txt(self.x+54,y+11,ts[11:19] or '--:--:--',10,MUTED)
            self.txt(self.x+166,y+10,text[:92],10,TEXT,width=self.cw-356)
            self.txt(self.r-160,y+11,str(event.get('kind','событие'))[:19],9,DIM)
        self.txt(self.x+25,self.h-94,'Запусков сетевой диагностики: '+str(len(load_history())),9,MUTED)

    def change_history_filter(self,name):
        self.app._visual_history_filter=name
        self.app._draw()

    def about(self):
        a=self.app
        self.header('Поддержка и о проекте','Информация о VORQELI Connect, документация и обновления',eyebrow='04  /  ПОДДЕРЖКА')
        self.icon(self.x+28,224,'info',67)
        self.txt(self.x+111,226,'VORQELI CONNECT',18,bold=True)
        self.txt(self.x+112,257,'Windows 10 / 11 · сетевые инструменты',10,MUTED)
        self.txt(self.x+112,279,'Без аккаунтов и скрытой телеметрии',9,DIM)
        self.badge(self.r-129,226,'v'+VERSION,tone='active',width=103)
        self.txt(self.x+24,373,'КАНАЛЫ И ДОКУМЕНТАЦИЯ',10,BLUE_BRIGHT,bold=True)
        links=(('Исходный код','github','https://github.com/Zeihos/VORQELI'),
               ('GeoHide DNS','dns','https://geohide.ru/'),
               ('Обновления','history',None))
        bw=(self.cw-66)//3
        for i,(name,kind,url) in enumerate(links):
            xx=self.x+22+i*(bw+11)
            self.canvas.create_polygon(self.app._rounded_coords(xx,406,xx+bw,492,13),
                  smooth=True,splinesteps=12,fill='#192D4B',outline='#304D73')
            self.icon(xx+13,423,kind,36)
            callback=(lambda u=url:webbrowser.open(u)) if url else a._check_updates
            self.button(xx+57,429,max(51,bw-69),38,name,callback,small=True)
        self.txt(self.x+26,557,'КОМПОНЕНТЫ ПРИЛОЖЕНИЯ',10,BLUE_BRIGHT,bold=True)
        for j,(name,detail) in enumerate((('WinWS / Flowseal','DPI-обход'),
                ('Telegram MTProto','Локальный прокси'),('GeoHide DNS','Сторонний DNS-провайдер'))):
            yy=575+j*23
            if yy>self.h-83:break
            self.dot(self.x+34,yy+6,GREEN,4)
            self.txt(self.x+47,yy,name,10,bold=True)
            self.txt(self.x+271,yy,detail,10,MUTED)

    def settings(self):
        a=self.app
        self.header('Настройки приложения','Поведение при запуске Windows и управление компонентами',eyebrow='05  /  НАСТРОЙКИ')
        left=int(self.cw*.54)
        lx=self.x+23;rx=self.x+left+30
        lw=left-49;rw=self.r-rx-23
        self.txt(lx,215,'ОБЩИЕ',10,BLUE_BRIGHT,bold=True)
        options=(('Автозапуск с Windows','Запускать при входе в систему','launch_at_startup'),
                 ('Восстановление режима','Включать ранее выбранный режим','restore_last_mode'),
                 ('Сворачивать в трей','Продолжать работу при закрытии окна','minimize_to_tray'),
                 ('Запуск от администратора','Запрашивать UAC при запуске','admin_on_launch'))
        for i,(name,desc,key) in enumerate(options):
            self.preference(lx,246+i*65,lw,name,desc,getattr(a.settings,key),
                            lambda k=key:a._toggle_setting(k),last=i==3)
        self.txt(rx,215,'КОМПОНЕНТЫ',10,BLUE_BRIGHT,bold=True)
        modules=(('Обход DPI / WinWS','Обход ограничений','connect_dpi'),
                 ('Telegram MTProto','Локальный прокси Desktop','connect_telegram'),
                 ('GeoHide DNS','Системное разрешение DNS','connect_dns'))
        for i,(name,desc,key) in enumerate(modules):
            self.preference(rx,252+i*84,rw,name,desc,getattr(a.settings,key),
                            lambda k=key:a._toggle_setting(k),last=i==2)
        self.icon(self.x+24,self.h-141,'settings',48)
        self.txt(self.x+88,self.h-140,'Сеть и стратегии DPI',15,bold=True)
        self.txt(self.x+88,self.h-109,'13 профилей · GeoHide DNS · HOSTS · восстановление',9,MUTED)
        self.button(self.r-209,self.h-137,182,47,'ОТКРЫТЬ  →',lambda:a._page('Сеть и стратегии'),primary=True)

    def advanced(self):
        a=self.app
        self.header('Сеть и стратегии DPI','ALT1–ALT13, GeoHide DNS и инструменты восстановления',eyebrow='06  /  ПАРАМЕТРЫ СЕТИ')
        left=int(self.cw*.636)
        lx=self.x+23;rx=self.x+left+25
        lw=left-38;rw=self.r-rx-17
        self.txt(lx,213,'ПРОФИЛЬ DPI / WINWS',10,BLUE_BRIGHT,bold=True)
        chosen=a.settings.dpi_mode
        self.txt(lx,250,'Подбор стратегии',11,bold=True)
        self.button(self.x+left-183,239,161,41,'АВТО 1–13',lambda:a._set_dpi_mode('alt_auto'),
                    selected=chosen=='alt_auto',small=True)
        self.txt(lx,305,'РУЧНОЙ ВЫБОР',9,DIM,bold=True)
        cols=7;gap=7
        chip_width=max(39,min(59,(lw-12-(cols-1)*gap)//cols))
        for i,mode in enumerate(ALT_MODES):
            row,col=divmod(i,cols)
            self.button(lx+col*(chip_width+gap),337+row*51,chip_width,37,
                        mode.upper(),lambda m=mode:a._set_dpi_mode(m),selected=chosen==mode,small=True)
        self.badge(lx,463,'Автоматический режим' if chosen=='alt_auto' else chosen.upper()+' выбран',
                   tone='positive' if chosen=='alt_auto' else 'active',width=217)
        self.txt(rx,213,'GEOHIDE DNS',10,BLUE_BRIGHT,bold=True)
        self.icon(rx,248,'dns',39)
        self.txt(rx+53,252,'Системный DNS',12,bold=True)
        self.txt(rx,305,'ТРАНСПОРТ',9,DIM,bold=True)
        sw=(rw-7)//2
        self.button(rx,333,sw,42,'IPv4 DNS',lambda:a._set_dns_mode('plain'),
                    selected=a.settings.dns_mode=='plain',disabled=a.settings.desired_enabled,small=True)
        self.button(rx+sw+7,333,sw,42,'DoH / HTTPS',lambda:a._set_dns_mode('doh'),
                    selected=a.settings.dns_mode=='doh',disabled=a.settings.desired_enabled,small=True)
        self.txt(rx,402,'DoH зависит от поддержки Windows.',9,MUTED,width=rw)
        self.txt(rx,426,'Переключение после отключения.',9,DIM,width=rw)
        self.txt(self.x+24,553,'СЕТЕВЫЕ ИНСТРУМЕНТЫ',10,BLUE_BRIGHT,bold=True)
        self.txt(self.x+24,577,'Параметры WinWS задаются выбранным профилем Flowseal.',9,MUTED)
        bw=(self.cw-64)//3
        for j,(name,callback) in enumerate((('ВОССТАНОВИТЬ DNS',a._restore_dns),
                ('HOSTS / ПРАВИЛА',a._show_hosts_manager),
                ('К НАСТРОЙКАМ',lambda:a._page('Настройки')))):
            self.button(self.x+22+j*(bw+10),self.h-128,bw,43,name,callback,
                        primary=j==2,small=True)


def draw(app) -> None:
    """Main actual Win32/Tk renderer with cache, no network side effects."""
    if app._quitting or not app.winfo_exists():
        return
    app._logical_size=(max(MIN_WIDTH,app.canvas.winfo_width()),
                       max(MIN_HEIGHT,app.canvas.winfo_height()))
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
    actions={'Главная':p.home,'Диагностика':p.diagnostics,'История':p.history,
             'О проекте':p.about,'Настройки':p.settings,'Сеть и стратегии':p.advanced}
    actions.get(app.selected_page,p.home)()
    app._sync_scrollbars(w,h)
    app._render_focus()
