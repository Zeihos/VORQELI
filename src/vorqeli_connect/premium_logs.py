"""VORQELI v0.39 premium Windows logs dialog (bounded, redacted, offline)."""
from __future__ import annotations
import tkinter as tk
from tkinter import messagebox

from .config import APP_DIR
from .log_tools import redact_secrets, tail_log

NAVY='#06142B';PANEL='#091C37';INK='#0C2448';BLUE='#1B72E8';EDGE='#2366AC'
WHITE='#F6F8FF';SUB='#A3BCE2';GREEN='#24E3B1'


def read_log(name,secret):
    if name not in ('DPI','Telegram'):raise ValueError('Неизвестный журнал')
    path=APP_DIR / ('dpi-engine.log' if name=='DPI' else 'telegram-engine.log')
    try:content=redact_secrets(tail_log(path,max_bytes=65536),secret)
    except (OSError,ValueError) as exc:content='Не удалось прочитать журнал: '+str(exc)
    return f'{name}  /  {path.name}\n'+('─'*65)+'\n\n'+content


def show_engine_logs(app):
    dlg=tk.Toplevel(app)
    dlg.title('VORQELI · Журналы')
    dlg.configure(bg=NAVY)
    dlg.resizable(False,False)
    scale=min(1, (app.winfo_screenwidth()-80)/970, (app.winfo_screenheight()-110)/640)
    w,h=int(970*scale),int(640*scale)
    dlg.geometry(f'{w}x{h}+{app.winfo_rootx()+max(0,(app.winfo_width()-w)//2)}+{app.winfo_rooty()+max(0,(app.winfo_height()-h)//2)}')
    dlg.overrideredirect(True)
    dlg.transient(app)
    dlg.attributes('-topmost',True)
    dlg.after(150,lambda:dlg.attributes('-topmost',False))
    header=tk.Frame(dlg,bg='#0A2854',height=76,highlightbackground=EDGE,highlightthickness=1)
    header.pack(fill='x');header.pack_propagate(False)
    left=tk.Frame(header,bg='#0A2854');left.pack(side='left',fill='y',padx=27)
    tk.Label(left,text='VORQELI   /   NETWORK CONTROL',bg='#0A2854',fg='#56CBFF',font=('Segoe UI',9,'bold')).pack(anchor='w',pady=(11,0))
    tk.Label(left,text='Журналы компонентов',bg='#0A2854',fg=WHITE,font=('Segoe UI',17,'bold')).pack(anchor='w')
    close=tk.Label(header,text='✕',bg='#0A2854',fg=SUB,font=('Segoe UI',17),width=4,cursor='hand2')
    close.pack(side='right',padx=10);close.bind('<Button-1>',lambda e:dlg.destroy())
    close.bind('<Enter>',lambda e:close.config(bg='#692948',fg='white'))
    close.bind('<Leave>',lambda e:close.config(bg='#0A2854',fg=SUB))
    dragging={'xy':None}
    def start(event):dragging['xy']=(event.x_root,event.y_root,dlg.winfo_x(),dlg.winfo_y())
    def motion(event):
        if dragging['xy']:
            sx,sy,x,y=dragging['xy'];dlg.geometry(f'+{max(0,x+event.x_root-sx)}+{max(0,y+event.y_root-sy)}')
    def stop(_):dragging['xy']=None
    for widget in (header,left):
        widget.bind('<ButtonPress-1>',start);widget.bind('<B1-Motion>',motion);widget.bind('<ButtonRelease-1>',stop)
    bar=tk.Frame(dlg,bg=NAVY,padx=22,pady=14)
    bar.pack(fill='x')
    selected={'name':'DPI'}
    buttons={}
    content=tk.Frame(dlg,bg=NAVY,padx=22)
    content.pack(fill='both',expand=True)
    text=tk.Text(content,wrap='none',state='disabled',bg=PANEL,fg='#C6E0FF',
                 insertbackground=WHITE,selectbackground='#245EA2',bd=0,
                 font=('Consolas',10),padx=17,pady=14,relief='flat',undo=False)
    text.pack(side='left',fill='both',expand=True)
    scroll=tk.Scrollbar(content,command=text.yview,bg=INK,troughcolor=NAVY,relief='flat')
    scroll.pack(side='right',fill='y')
    text.configure(yscrollcommand=scroll.set)
    horizontal=tk.Scrollbar(dlg,orient='horizontal',command=text.xview,bg=INK,troughcolor=NAVY)
    horizontal.pack(fill='x',padx=22,pady=(0,7));text.configure(xscrollcommand=horizontal.set)
    text.tag_config('error',foreground='#FF7893')
    text.tag_config('success',foreground=GREEN)
    def load(name):
        selected['name']=name
        for n,b in buttons.items():b.configure(bg=BLUE if n==name else INK,fg=WHITE)
        log=read_log(name,app.settings.telegram_secret)
        text.config(state='normal');text.delete('1.0','end');text.insert('1.0',log)
        # Highlight lines only; no parsing/executing log content.
        for no,line in enumerate(log.splitlines(),start=1):
            low=line.lower()
            tag='error' if any(x in low for x in ('error','failed','ошибка','traceback','exception')) else 'success' if 'success' in low else None
            if tag:text.tag_add(tag,f'{no}.0',f'{no}.end')
        text.config(state='disabled');text.see('end')
    def button(parent,title,action):
        b=tk.Button(parent,text=title,command=action,bg=INK,fg=WHITE,activebackground=BLUE,
                    activeforeground=WHITE,bd=0,relief='flat',cursor='hand2',font=('Segoe UI',10,'bold'),padx=18,pady=9)
        b.pack(side='left',padx=(0,9));return b
    for name in ('DPI','Telegram'):
        buttons[name]=button(bar,name,lambda n=name:load(n))
    button(bar,'ОБНОВИТЬ',lambda:load(selected['name']))
    tk.Label(bar,text='До 64 КБ  ·  Секреты скрыты',bg=NAVY,fg=SUB,font=('Segoe UI',10)).pack(side='right')
    bottom=tk.Frame(dlg,bg=NAVY,padx=22,pady=10)
    bottom.pack(fill='x')
    tk.Label(bottom,text='Локальные журналы · данные не отправляются в интернет',bg=NAVY,fg=SUB,font=('Segoe UI',9)).pack(side='left')
    tk.Button(bottom,text='ЗАКРЫТЬ',command=dlg.destroy,bg=INK,fg=WHITE,bd=0,
              font=('Segoe UI',10,'bold'),cursor='hand2',padx=18,pady=7).pack(side='right')
    load('DPI')
    dlg.bind('<Escape>',lambda e:dlg.destroy())
    dlg.focus_set()
    return dlg
