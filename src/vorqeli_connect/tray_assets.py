"""Small status-readable images for the Windows notification area."""
from __future__ import annotations
from PIL import Image, ImageDraw

STATUS_COLORS = {
    'connected': '#80E4C6',
    'partial': '#F8CF93',
    'error': '#FC9DBA',
    'off': '#8FBDFE',
}


def tray_icon(logo: Image.Image, state: str = 'off') -> Image.Image:
    """Overlay a badge without mutating the original logo."""
    icon = Image.new('RGBA',(64,64),(0,0,0,0))
    inner = logo.convert('RGBA').copy()
    inner.thumbnail((55,55),Image.Resampling.LANCZOS)
    icon.alpha_composite(inner, ((64-inner.width)//2,(64-inner.height)//2))
    draw=ImageDraw.Draw(icon)
    # A dark outline makes the status visible in both light and dark Windows themes.
    draw.ellipse((39,39,63,63),fill='#121629')
    draw.ellipse((44,44,59,59),fill=STATUS_COLORS.get(state,STATUS_COLORS['off']))
    return icon
