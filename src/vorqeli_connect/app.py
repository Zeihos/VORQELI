"""VORQELI Connect desktop dashboard. Network changes are deliberately disabled until engines are integrated."""
import json
import queue
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox
from .config import load_settings, save_settings
from .diagnostics import check_all, SERVICES

BG="#0b0d15"; SIDEBAR="#111420"; PANEL="#171b2a"; PANEL2="#20253a"
TEXT="#f3f0ff"; MUTED="#969bb5"; ACCENT="#a68bff"; GREEN="#75d6a8"; AMBER="#f5bf7c"

class ConnectApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("VORQELI Connect  ·  0.3.0")
        self.geometry("1080x700"); self.minsize(920,620); self.configure(bg=BG)
        self.settings=load_settings(); self.events=queue.Queue(); self.checking=False
        self.last_results=[]; self.current_page="Обзор"
        self._shell(); self.show_page("Обзор"); self.after(100,self._poll)

    def label(self,parent,text,size=11,color=TEXT,bold=False,**kw):
        return tk.Label(parent,text=text,bg=parent.cget("bg"),fg=color,
                        font=("Segoe UI",size,"bold" if bold else "normal"),anchor="w",**kw)

    def button(self,parent,text,action,primary=False):
        return tk.Button(parent,text=text,command=action,bg=ACCENT if primary else PANEL2,
                         fg=BG if primary else TEXT,activebackground="#bba9ff",activeforeground=BG,
                         relief="flat",bd=0,cursor="hand2",font=("Segoe UI",10,"bold"),padx=16,pady=10)

    def _shell(self):
        self.sidebar=tk.Frame(self,bg=SIDEBAR,width=238);self.sidebar.pack(side="left",fill="y");self.sidebar.pack_propagate(False)
        brand=tk.Frame(self.sidebar,bg=SIDEBAR,padx=20,pady=26);brand.pack(fill="x")
        self.label(brand,"◆  VORQELI",20,ACCENT,True).pack(anchor="w")
        self.label(brand,"CONNECT  /  NETWORK HUB",9,MUTED).pack(anchor="w",pady=(5,0))
        self.nav={}
        for name,icon in [("Обзор","◫"),("Диагностика","◎"),("Модули","◇"),("Настройки","⚙"),("О программе","ⓘ")]:
            b=tk.Button(self.sidebar,text=f"  {icon}    {name}",anchor="w",command=lambda n=name:self.show_page(n),
                        bg=SIDEBAR,fg=MUTED,activebackground=PANEL2,activeforeground=TEXT,
                        relief="flat",bd=0,padx=20,pady=14,font=("Segoe UI",11),cursor="hand2")
            b.pack(fill="x",padx=10,pady=2);self.nav[name]=b
        tk.Frame(self.sidebar,bg=SIDEBAR).pack(fill="both",expand=True)
        self.label(self.sidebar,"●  Локальное приложение",9,GREEN).pack(anchor="w",padx=24,pady=(0,8))
        self.label(self.sidebar,"Версия 0.3.0  •  Preview",9,MUTED).pack(anchor="w",padx=24,pady=(0,24))
        self.main=tk.Frame(self,bg=BG,padx=32,pady=26);self.main.pack(side="left",fill="both",expand=True)

    def panel(self,parent,padx=22,pady=18):
        return tk.Frame(parent,bg=PANEL,padx=padx,pady=pady)

    def heading(self,title,subtitle):
        self.label(self.main,title,25,TEXT,True).pack(anchor="w")
        self.label(self.main,subtitle,11,MUTED).pack(anchor="w",pady=(6,24))

    def show_page(self,name):
        self.current_page=name
        for child in self.main.winfo_children():child.destroy()
        for key,btn in self.nav.items():btn.configure(bg=PANEL2 if key==name else SIDEBAR,fg=TEXT if key==name else MUTED)
        {"Обзор":self.overview,"Диагностика":self.diagnostics,"Модули":self.modules,
         "Настройки":self.preferences,"О программе":self.about}[name]()

    def overview(self):
        self.heading("Центр управления","Контролируйте состояние сети и проверяйте доступность сервисов")
        hero=self.panel(self.main,26,24);hero.pack(fill="x")
        self.label(hero,"СОСТОЯНИЕ СИСТЕМЫ",10,ACCENT,True).pack(anchor="w")
        self.label(hero,"Готов к диагностике",23,TEXT,True).pack(anchor="w",pady=(10,4))
        self.label(hero,"Сетевые настройки Windows не изменяются. DPI и прокси ещё не подключены.",10,MUTED).pack(anchor="w")
        self.button(hero,"Проверить соединения  →",self.start_scan,True).pack(anchor="w",pady=(20,0))
        tiles=tk.Frame(self.main,bg=BG);tiles.pack(fill="x",pady=18)
        for i,(title,value,desc) in enumerate([("DPI-движок","Не установлен","Ожидается интеграция"),("Telegram-прокси","Не установлен","Локальный модуль"),("Проверка сети",str(len(SERVICES))+" сервиса","HTTPS-запросы")]):
            card=self.panel(tiles,17,16);card.grid(row=0,column=i,sticky="nsew",padx=(0,10) if i<2 else 0)
            tiles.columnconfigure(i,weight=1)
            self.label(card,title,10,MUTED).pack(anchor="w")
            self.label(card,value,15,TEXT,True).pack(anchor="w",pady=(12,5))
            self.label(card,desc,9,ACCENT).pack(anchor="w")
        self.label(self.main,"БЫСТРЫЙ ДОСТУП",10,MUTED,True).pack(anchor="w",pady=(10,10))
        row=tk.Frame(self.main,bg=BG);row.pack(fill="x")
        self.button(row,"Диагностика",lambda:self.show_page("Диагностика")).pack(side="left",padx=(0,10))
        self.button(row,"Настройки",lambda:self.show_page("Настройки")).pack(side="left")

    def diagnostics(self):
        self.heading("Диагностика сети","Проверка HTTPS-доступности. Это не тест качества видео или голосовой связи.")
        top=tk.Frame(self.main,bg=BG);top.pack(fill="x",pady=(0,18))
        self.scan_btn=self.button(top,"Запустить проверку",self.start_scan,True);self.scan_btn.pack(side="left")
        self.button(top,"Экспорт результатов",self.export).pack(side="left",padx=12)
        self.status=self.label(self.main,"Ожидание проверки",10,MUTED);self.status.pack(anchor="w",pady=(0,10))
        self.status_labels={}
        for name in SERVICES:
            card=self.panel(self.main,16,13);card.pack(fill="x",pady=5)
            self.label(card,name,12,TEXT,True).pack(side="left")
            result=next((status for n,status in self.last_results if n==name),"Не проверено")
            lbl=self.label(card,result,10,GREEN if result=="Доступен" else MUTED);lbl.pack(side="right")
            self.status_labels[name]=lbl

    def modules(self):
        self.heading("Сетевые модули","Состояние интеграций и безопасное управление")
        for name,desc in [("DPI-стратегии","Сетевой движок пока не включён в поставку."),
                          ("Telegram MTProto","Локальный прокси пока не включён в поставку.")]:
            card=self.panel(self.main);card.pack(fill="x",pady=(0,14))
            self.label(card,name,15,TEXT,True).pack(anchor="w")
            self.label(card,desc,10,MUTED).pack(anchor="w",pady=(9,12))
            self.label(card,"○  Не настроено",10,AMBER,True).pack(anchor="w")
        self.label(self.main,"Приложение не запускает сторонние процессы и не меняет системные правила.",10,MUTED).pack(anchor="w",pady=8)

    def preferences(self):
        self.heading("Настройки","Локальные параметры приложения")
        card=self.panel(self.main);card.pack(fill="x")
        self.label(card,"Порт будущего Telegram-прокси",12,TEXT,True).pack(anchor="w")
        self.label(card,"Допустимый диапазон: 1024–65535. Изменение не запускает прокси.",10,MUTED).pack(anchor="w",pady=(6,12))
        self.port=tk.StringVar(value=str(self.settings.telegram_port))
        tk.Entry(card,textvariable=self.port,bg=PANEL2,fg=TEXT,insertbackground=TEXT,relief="flat",
                 font=("Segoe UI",12),width=14).pack(anchor="w",ipady=9)
        self.button(card,"Сохранить настройки",self.save,True).pack(anchor="w",pady=(18,0))
        self.label(self.main,"Параметры хранятся в профиле пользователя Windows.",10,MUTED).pack(anchor="w",pady=16)

    def about(self):
        self.heading("О VORQELI Connect","Информация о проекте")
        card=self.panel(self.main);card.pack(fill="x")
        self.label(card,"◆  VORQELI CONNECT",20,ACCENT,True).pack(anchor="w")
        self.label(card,"Версия 0.3.0  •  Предварительная сборка",11,MUTED).pack(anchor="w",pady=(12,18))
        self.label(card,"Открытый проект сетевого менеджера для Windows.",11,TEXT).pack(anchor="w")
        self.label(card,"GitHub: github.com/Zeihos/VORQELI",10,MUTED).pack(anchor="w",pady=(10,0))

    def save(self):
        try:
            port=int(self.port.get())
            if not 1024<=port<=65535:raise ValueError
            self.settings.telegram_port=port;save_settings(self.settings)
            messagebox.showinfo("VORQELI Connect","Настройки сохранены")
        except ValueError:messagebox.showerror("Ошибка","Укажите порт от 1024 до 65535")
        except OSError as e:messagebox.showerror("Ошибка сохранения",str(e))

    def start_scan(self):
        if self.checking:return
        self.checking=True
        if self.current_page!="Диагностика":self.show_page("Диагностика")
        self.scan_btn.configure(state="disabled",text="Проверка...")
        self.status.configure(text="Выполняется проверка")
        for lbl in self.status_labels.values():lbl.configure(text="Проверяется...",fg=MUTED)
        threading.Thread(target=self._worker,daemon=True).start()

    def _worker(self):
        try:self.events.put(("results",check_all()))
        except Exception as exc:self.events.put(("error",str(exc)))

    def _poll(self):
        try:
            while True:
                kind,payload=self.events.get_nowait();self.checking=False
                if kind=="results":
                    self.last_results=payload
                    if self.current_page=="Диагностика":
                        for name,status in payload:
                            self.status_labels[name].configure(text=status,fg=GREEN if status=="Доступен" else AMBER)
                        self.status.configure(text="Последняя проверка: "+datetime.now().strftime("%H:%M:%S"))
                else:messagebox.showerror("Диагностика",payload)
                if self.current_page=="Диагностика":self.scan_btn.configure(state="normal",text="Запустить проверку")
        except queue.Empty:pass
        self.after(100,self._poll)

    def export(self):
        if not self.last_results:
            messagebox.showinfo("Экспорт","Сначала запустите диагностику");return
        path=filedialog.asksaveasfilename(title="Сохранить диагностику",defaultextension=".json",
                                           filetypes=[("JSON","*.json")])
        if not path:return
        data={"app":"VORQELI Connect","version":"0.3.0","exported_at":datetime.now().astimezone().isoformat(),
              "results":dict(self.last_results)}
        try:Path(path).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
        except OSError as exc:messagebox.showerror("Экспорт",str(exc))

def main():ConnectApp().mainloop()
if __name__=="__main__":main()
