"""VORQELI's desktop visual system.

All translucent panels are composited by Pillow; Tk widgets are never used to
simulate transparency over a flat solid color. Scene images are cached by size
and page, so a diagnostics event does not reblur the background.
"""
from __future__ import annotations
from functools import lru_cache
from PIL import Image, ImageDraw, ImageFilter

INK = '#090D1A'
FG = '#F5F6FF'
SECONDARY = '#A7AEC8'
DIM = '#7D87A9'
VIOLET = '#AF9AFF'
PURPLE = '#9475F6'
BLUE = '#86BFFF'
AQUA = '#82DEC9'
YELLOW = '#FAD39A'
ROSE = '#FC9DBA'


def layout(width: int, height: int) -> dict[str, int]:
    """Reusable measurements for every page, including resize."""
    width, height = max(1060, width), max(710, height)
    main = 276
    right = width - 28
    return {
        'w': width, 'h': height, 'left': main, 'right': right,
        'content_width': right - main, 'hero_top': 115, 'hero_bottom': 345,
        'cards_top': 365, 'cards_bottom': 546, 'footer_top': 566,
        'bottom': height - 24,
    }


def _glow(width: int, height: int, cx: float, cy: float, radius: float,
          rgb: tuple[int,int,int], alpha: int) -> Image.Image:
    # Downsample while blurring large glows to keep UI responsive.
    scale = 5
    small = Image.new('RGBA',(width//scale+2,height//scale+2),(0,0,0,0))
    d = ImageDraw.Draw(small)
    x,y,r=cx/scale,cy/scale,radius/scale
    d.ellipse((int(x-r),int(y-r),int(x+r),int(y+r)),fill=(*rgb,alpha))
    small = small.filter(ImageFilter.GaussianBlur(max(2,r/2)))
    return small.resize((width,height),Image.Resampling.BILINEAR)


def _glass(layer: Image.Image, rectangle: tuple[int,int,int,int],
           *, accent: bool = False, radius: int = 24):
    x1,y1,x2,y2=rectangle
    if x2<=x1 or y2<=y1:return
    draw=ImageDraw.Draw(layer,'RGBA')
    # Shadow and low-alpha fill create frosted multi-layer effect.
    draw.rounded_rectangle((x1+2,y1+7,x2+2,y2+7),radius=radius,fill=(0,0,0,60))
    draw.rounded_rectangle(rectangle,radius=radius,
                           fill=(41,40,77,199) if accent else (24,30,53,202),
                           outline=(196,179,249,128) if accent else (135,154,202,80),width=1)
    # Top light catch and inset soft glass sheen.
    draw.rounded_rectangle((x1+12,y1+5,x2-12,y1+7),radius=1,
                           fill=(233,224,255,79) if accent else (208,220,250,40))


def _render_uncached(width: int, height: int, page: str) -> Image.Image:
    geo=layout(width,height)
    w,h=geo['w'],geo['h']
    # Smooth gradient, no hard bars or repeating textures.
    base=Image.new('RGBA',(w,h),'#080B17')
    painter=ImageDraw.Draw(base)
    for y in range(h):
        t=y/max(h-1,1)
        painter.line((0,y,w,y),fill=(9+int(t*7),12+int(t*9),27+int(t*17),255))
    for glow in [
        (w*.87,h*.13,h*.53,(129,65,246),95),
        (w*.50,h*.91,h*.54,(36,89,211),64),
        (w*.17,h*.20,h*.34,(110,62,183),45),
    ]:
        base=Image.alpha_composite(base,_glow(w,h,*glow))
    glass=Image.new('RGBA',(w,h),(0,0,0,0))
    _glass(glass,(16,16,246,h-16),radius=28)
    _glass(glass,(geo['left'],geo['hero_top'],geo['right'],geo['hero_bottom']),accent=True,radius=29)
    if page=='Главная':
        card_width=(geo['content_width']-28)//3
        for n in range(3):
            x=geo['left']+n*(card_width+14)
            _glass(glass,(x,geo['cards_top'],x+card_width,geo['cards_bottom']),radius=23)
        _glass(glass,(geo['left'],geo['footer_top'],geo['right'],geo['bottom']),radius=23)
    else:
        _glass(glass,(geo['left'],geo['cards_top'],geo['right'],geo['bottom']),radius=23)
    return Image.alpha_composite(base,glass)


@lru_cache(maxsize=12)
def scene(width: int, height: int, page: str) -> Image.Image:
    # Cache is safe because returned images are treated as immutable.
    return _render_uncached(width,height,page)


def tint_status(state: str) -> str:
    return {'connected':AQUA,'partial':YELLOW,'error':ROSE,'off':BLUE,
            'on':AQUA}.get(state,SECONDARY)


def fit_line(value: object, *, count: int = 72) -> str:
    """Single-line elision for small cards. UI never executes this text."""
    text=' '.join(str(value).split())
    return text if len(text)<=count else text[:count-1]+'…'

@lru_cache(maxsize=48)
def button_skin(width: int, height: int, *, accent: bool = False,
                hover: bool = False, disabled: bool = False) -> Image.Image:
    """Glossy, translucent button skin with a real pixel gradient and curved specular edge.

    The RGBA outside the rounded mask is transparent, so the background glass
    panel shows through around every control.
    """
    width, height = max(40, width), max(24, height)
    result = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    mask = Image.new('L', (width, height), 0)
    ImageDraw.Draw(mask).rounded_rectangle((1, 1, width-2, height-2),
                                           radius=min(16, height//3), fill=255)
    fill = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(fill, 'RGBA')
    if disabled:
        top, bottom = (60, 66, 85), (39, 46, 65)
    elif accent:
        top, bottom = ((197, 172, 255), (126, 96, 230)) if hover else ((180, 158, 255), (122, 91, 226))
    else:
        top, bottom = ((74, 87, 121), (42, 53, 83)) if hover else ((62, 72, 105), (32, 42, 69))
    for y in range(height):
        t = y / max(height-1, 1)
        color = tuple(round(top[c]*(1-t) + bottom[c]*t) for c in range(3))
        draw.line((0,y,width,y), fill=(*color,255))
    result.paste(fill, (0,0), mask)
    border = ImageDraw.Draw(result, 'RGBA')
    border.rounded_rectangle((1,1,width-2,height-2),radius=min(16,height//3),
                             outline=(217, 201, 255, 180) if accent and not disabled
                                     else (177, 190, 234, 89),width=1)
    border.line((14,4,width-14,4),
                fill=(255,255,255,90) if accent and not disabled else (220,226,255,35),width=1)
    return result
