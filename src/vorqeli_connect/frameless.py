"""Fixed-size Windows frameless shell: UAC, DNS and worker commands unaffected.

The application remains a normal top-level process with an accessible taskbar
entry. Only the GUI window uses override-redirect; minimize is handled safely.
"""
from __future__ import annotations
import os


def fixed_geometry(screen_width:int,screen_height:int)->str:
    """Center a fixed 3:2 window, scaled only for genuinely small displays."""
    sw=max(600,screen_width);sh=max(440,screen_height)
    scale=min(1.,(sw-32)/1260,(sh-72)/840)
    w=max(540,int(1260*scale));h=max(360,int(840*scale))
    x=max(0,(sw-w)//2);y=max(0,(sh-h)//2)
    return f'{w}x{h}+{x}+{y}'


def configure(app)->None:
    """Apply fixed geometry and Tk-managed frameless client window."""
    app.geometry(fixed_geometry(app.winfo_screenwidth(),app.winfo_screenheight()))
    app.resizable(False,False)
    app.overrideredirect(True)
    app._frameless_mouse=None
    app.after(350,lambda: _fix_taskbar(app))


def _fix_taskbar(app):
    """On Win32 expose the undecorated toplevel to Alt+Tab and taskbar."""
    if os.name!='nt':return
    import ctypes
    try:
        app.update_idletasks()
        child=app.winfo_id()
        user32=ctypes.windll.user32
        hwnd=user32.GetParent(child) or child
        # GWL_EXSTYLE, WS_EX_APPWINDOW, WS_EX_TOOLWINDOW.
        get=user32.GetWindowLongW;set_=user32.SetWindowLongW
        get.argtypes=(ctypes.c_void_p,ctypes.c_int)
        set_.argtypes=(ctypes.c_void_p,ctypes.c_int,ctypes.c_long)
        get.restype=ctypes.c_long;set_.restype=ctypes.c_long
        flags=get(hwnd,-20)
        wanted=(flags|0x00040000)&~0x00000080
        if wanted!=flags:set_(hwnd,-20,wanted)
        user32.SetWindowPos(hwnd,0,0,0,0,0,0x0027) # NOZORDER|NOMOVE|NOSIZE|FRAMECHANGED
    except (OSError,ValueError,AttributeError,TypeError):
        # Never prevent network management because chrome is unavailable.
        pass


def begin_move(app,screen_x:int,screen_y:int)->None:
    app._frameless_mouse=(screen_x,screen_y,app.winfo_x(),app.winfo_y())


def move(app,screen_x:int,screen_y:int)->None:
    base=getattr(app,'_frameless_mouse',None)
    if base is None:return
    sx,sy,x,y=base
    new_x=max(0,min(app.winfo_screenwidth()-app.winfo_width(),x+screen_x-sx))
    new_y=max(0,min(app.winfo_screenheight()-app.winfo_height(),y+screen_y-sy))
    app.geometry(f'+{new_x}+{new_y}')


def end_move(app):
    app._frameless_mouse=None


def minimize(app):
    """An override-redirect window cannot be iconified by Tk directly."""
    if not app.winfo_exists():return
    try:
        if app.overrideredirect():
            app.overrideredirect(False)
            app._premium_minimized=True
        app.iconify()
        if getattr(app,'_premium_minimized',False):
            app.bind('<Map>',lambda event:app.after(60,lambda:_restore(app)),add='+')
    except Exception:
        # Last resort stays visible in the taskbar instead of disappearing.
        try:app.deiconify()
        except Exception:pass


def _restore(app):
    if not getattr(app,'_premium_minimized',False) or not app.winfo_exists():return
    if str(app.state()) not in ('normal','zoomed'):return
    try:
        app.overrideredirect(True)
        app._premium_minimized=False
        _fix_taskbar(app)
    except Exception:pass
