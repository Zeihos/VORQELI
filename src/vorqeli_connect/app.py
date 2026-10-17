"""VORQELI Connect network dashboard with opt-in, local engine adapters."""
import json
import os
import secrets
import webbrowser
import subprocess
import queue
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox
from .config import APP_DIR, load_settings, save_settings
from .process_manager import ModuleManager
from .module_registry import MODULES
from .integrations import inspect_file
from .engine_adapters import build_dpi_spec, build_telegram_spec, proxy_link, port_is_free, port_is_listening
from .engine_processes import EngineProcess
from .profiles import load_profiles, save_profiles, validate_profile
from .event_log import record_event, recent_events
from tkinter import simpledialog
from .diagnostics import check_all, SERVICES
from .network_tools import check_network
from .history import load_history, record_scan

BG="#0b0d15"; SIDEBAR="#111420"; PANEL="#171b2a"; PANEL2="#20253a"
TEXT="#f3f0ff"; MUTED="#969bb5"; ACCENT="#a68bff"; GREEN="#75d6a8"; AMBER="#f5bf7c"

class ConnectApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("VORQELI Connect  ·  0.10.0")
        self.geometry("1080x700"); self.minsize(920,620); self.configure(bg=BG)
        self.settings=load_settings(); self.module_manager=ModuleManager(); self.dpi_engine=EngineProcess("DPI"); self.tg_engine=EngineProcess("Telegram"); self.profiles=load_profiles(); self.events=queue.Queue(); self.checking=False
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
        for name,icon in [("Обзор","◫"),("Диагностика","◎"),("История","◷"),("События","≡"),("DPI","◈"),("Telegram","↗"),("Модули","◇"),("Настройки","⚙"),("О программе","ⓘ")]:
            b=tk.Button(self.sidebar,text=f"  {icon}    {name}",anchor="w",command=lambda n=name:self.show_page(n),
                        bg=SIDEBAR,fg=MUTED,activebackground=PANEL2,activeforeground=TEXT,
                        relief="flat",bd=0,padx=20,pady=14,font=("Segoe UI",11),cursor="hand2")
            b.pack(fill="x",padx=10,pady=2);self.nav[name]=b
        tk.Frame(self.sidebar,bg=SIDEBAR).pack(fill="both",expand=True)
        self.label(self.sidebar,"●  Локальное приложение",9,GREEN).pack(anchor="w",padx=24,pady=(0,8))
        self.label(self.sidebar,"Версия 0.10.0  •  Preview",9,MUTED).pack(anchor="w",padx=24,pady=(0,24))
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
        {"Обзор":self.overview,"Диагностика":self.diagnostics,"История":self.history_page,"События":self.events_page,"DPI":self.dpi_page,"Telegram":self.telegram_page,"Модули":self.modules,
         "Настройки":self.preferences,"О программе":self.about}[name]()

    def overview(self):
        self.heading("Центр управления","Контролируйте состояние сети и проверяйте доступность сервисов")
        hero=self.panel(self.main,26,24);hero.pack(fill="x")
        self.label(hero,"СОСТОЯНИЕ СИСТЕМЫ",10,ACCENT,True).pack(anchor="w")
        self.label(hero,"Готов к диагностике",23,TEXT,True).pack(anchor="w",pady=(10,4))
        self.label(hero,"DPI и Telegram управляются отдельно; запуск только по вашему действию.",10,MUTED).pack(anchor="w")
        self.button(hero,"Проверить соединения  →",self.start_scan,True).pack(anchor="w",pady=(20,0))
        tiles=tk.Frame(self.main,bg=BG);tiles.pack(fill="x",pady=18)
        for i,(title,value,desc) in enumerate([("DPI-движок","Запущен" if self.dpi_engine.running else "Не запущен","Экспериментально"),("Telegram-прокси","Запущен" if self.tg_engine.running else "Не запущен","Локальный MTProto"),("Проверка сети",str(len(SERVICES))+" сервиса","HTTPS-запросы")]):
            card=self.panel(tiles,17,16);card.grid(row=0,column=i,sticky="nsew",padx=(0,10) if i<2 else 0)
            tiles.columnconfigure(i,weight=1)
            self.label(card,title,10,MUTED).pack(anchor="w")
            self.label(card,value,15,TEXT,True).pack(anchor="w",pady=(12,5))
            self.label(card,desc,9,ACCENT).pack(anchor="w")
        self.label(self.main,"БЫСТРЫЙ ДОСТУП",10,MUTED,True).pack(anchor="w",pady=(10,10))
        row=tk.Frame(self.main,bg=BG);row.pack(fill="x")
        self.button(row,"Диагностика",lambda:self.show_page("Диагностика")).pack(side="left",padx=(0,10))
        self.button(row,"DPI",lambda:self.show_page("DPI")).pack(side="left",padx=(0,10))
        self.button(row,"Telegram",lambda:self.show_page("Telegram")).pack(side="left",padx=(0,10))
        self.button(row,"Настройки",lambda:self.show_page("Настройки")).pack(side="left")

    def diagnostics(self):
        self.heading("Диагностика сети","Проверка HTTPS-доступности. Это не тест качества видео или голосовой связи.")
        top=tk.Frame(self.main,bg=BG);top.pack(fill="x",pady=(0,18))
        self.scan_btn=self.button(top,"Запустить проверку",self.start_scan,True);self.scan_btn.pack(side="left")
        self.button(top,"Экспорт результатов",self.export).pack(side="left",padx=12)
        self.button(top,"История",lambda:self.show_page("История")).pack(side="left")
        self.button(top,"Проверить DNS/TCP",self.start_network_scan).pack(side="left",padx=12)
        self.status=self.label(self.main,"Ожидание проверки",10,MUTED);self.status.pack(anchor="w",pady=(0,10))
        self.status_labels={}
        for name in SERVICES:
            card=self.panel(self.main,16,13);card.pack(fill="x",pady=5)
            self.label(card,name,12,TEXT,True).pack(side="left")
            result=next((status for n,status in self.last_results if n==name),"Не проверено")
            lbl=self.label(card,result,10,GREEN if result=="Доступен" else MUTED);lbl.pack(side="right")
            self.status_labels[name]=lbl

    def history_page(self):
        self.heading("История проверок", "Последние 100 диагностик сохраняются только на этом компьютере")
        records = load_history()
        if not records:
            self.label(self.main,"История пуста. Запустите диагностику.",11,MUTED).pack(anchor="w")
            return
        self.button(self.main,"Экспорт последней проверки",self.export).pack(anchor="w",pady=(0,12))
        for item in reversed(records[-8:]):
            card=self.panel(self.main,14,11);card.pack(fill="x",pady=4)
            timestamp=item.get("timestamp", "Неизвестное время")
            self.label(card,timestamp[:19].replace("T"," ")+" UTC",10,ACCENT,True).pack(anchor="w")
            summary="  ·  ".join(f"{k}: {v}" for k,v in item["results"].items())
            self.label(card,summary,9,MUTED).pack(anchor="w",pady=(4,0))

    def _save_engine_settings(self):
        save_settings(self.settings)

    def _engine_controls(self, parent, engine, on_start, on_stop, log_file):
        bar=tk.Frame(parent,bg=PANEL);bar.pack(anchor="w",pady=(12,0))
        self.button(bar,"Запустить",on_start,True).pack(side="left",padx=(0,8))
        self.button(bar,"Остановить",on_stop).pack(side="left",padx=(0,8))
        self.button(bar,"Журнал",lambda p=log_file:self.open_engine_log(p)).pack(side="left",padx=(0,8))
        self.button(bar,"Обновить",lambda:self.show_page(self.current_page)).pack(side="left")
        status=f"Запущен · PID {engine.pid}" if engine.running else "Остановлен"
        if not engine.running and engine.exit_code is not None:
            status+=f" · Код завершения: {engine.exit_code}"
        if engine is self.tg_engine and engine.running:
            status+=(" · Порт слушает" if port_is_listening(self.settings.telegram_port)
                     else " · Ожидание локального порта")
        self.label(parent,status,11,GREEN if engine.running else AMBER,True).pack(anchor="w",pady=(14,0))

    def open_engine_log(self, filename):
        path=APP_DIR / filename
        if not path.is_file():
            messagebox.showinfo("Журнал","Файл журнала ещё не создан")
            return
        try:
            if os.name == "nt": os.startfile(str(path))
            else: messagebox.showinfo("Журнал",str(path))
        except OSError as exc:
            messagebox.showerror("Журнал",str(exc))

    def dpi_page(self):
        self.heading("DPI · WinWS", "Экспериментальный прямой запуск локального движка Flowseal")
        card=self.panel(self.main);card.pack(fill="x")
        self.label(card,"Источник: Flowseal / zapret-discord-youtube",13,TEXT,True).pack(anchor="w")
        self.label(card,"Выберите распакованный оригинальный пакет. Ничего не скачиваем автоматически.",10,MUTED).pack(anchor="w",pady=(7,12))
        self.label(card,"Папка: "+(self.settings.dpi_bundle_dir or "не выбрана"),10,MUTED).pack(anchor="w")
        self.button(card,"Выбрать папку zapret",self.select_dpi_bundle).pack(anchor="w",pady=(10,14))
        bar=tk.Frame(card,bg=PANEL);bar.pack(anchor="w")
        self.label(bar,"TCP-стратегия:",11,TEXT).pack(side="left",padx=(0,12))
        self.dpi_mode=tk.StringVar(value=self.settings.dpi_mode if self.settings.dpi_mode in ("fake","multisplit") else "fake")
        for name, value in [("FAKE", "fake"),("MULTISPLIT", "multisplit")]:
            tk.Radiobutton(bar,text=name,variable=self.dpi_mode,value=value,bg=PANEL,fg=TEXT,
                           selectcolor=PANEL2,activebackground=PANEL,activeforeground=TEXT).pack(side="left",padx=(0,12))
        self.label(card,"Только TCP 80/443 из lists/list-general.txt. Это НЕ точные стратегии general*.bat.",10,AMBER).pack(anchor="w",pady=(12,0))
        self.label(card,"WinDivert может потребовать запуск с правами администратора. Без автозапуска и службы.",10,MUTED).pack(anchor="w",pady=(5,0))
        self._engine_controls(card,self.dpi_engine,self.start_dpi,self.stop_dpi,"dpi-engine.log")

    def select_dpi_bundle(self):
        folder=filedialog.askdirectory(title="Папка с bin/winws.exe")
        if folder:
            self.settings.dpi_bundle_dir=folder
            try: self._save_engine_settings(); self.show_page("DPI")
            except OSError as exc: messagebox.showerror("Ошибка",str(exc))

    def start_dpi(self):
        if os.name != "nt":
            messagebox.showerror("Только Windows","DPI-адаптер работает только в Windows")
            return
        try:
            mode=self.dpi_mode.get()
            spec=build_dpi_spec(self.settings.dpi_bundle_dir,mode)
            self.settings.dpi_mode=mode
            self._save_engine_settings()
            pid=self.dpi_engine.start(spec,APP_DIR / "dpi-engine.log")
            record_event("dpi_start",f"DPI запущен PID {pid}; стратегия {mode}")
            self.show_page("DPI")
        except (OSError,ValueError,RuntimeError) as exc:
            messagebox.showerror("DPI не запущен",f"{exc}\n\nПроверьте файлы пакета, права Windows и журнал.")

    def stop_dpi(self):
        try:
            stopped=self.dpi_engine.stop()
            if stopped: record_event("dpi_stop","DPI завершён из приложения")
            self.show_page("DPI")
        except (OSError,subprocess.TimeoutExpired) as exc:
            messagebox.showerror("Ошибка остановки DPI",str(exc))

    def telegram_page(self):
        self.heading("Telegram · MTProto", "Локальный tg-ws-proxy через консольный Python-модуль Flowseal")
        card=self.panel(self.main);card.pack(fill="x")
        self.label(card,"Источник: Flowseal / tg-ws-proxy",13,TEXT,True).pack(anchor="w")
        self.label(card,"Выберите локальную копию исходников. Сначала установите её Python-зависимости.",10,MUTED).pack(anchor="w",pady=(7,12))
        self.label(card,"Папка: "+(self.settings.telegram_source_dir or "не выбрана"),10,MUTED).pack(anchor="w")
        self.button(card,"Выбрать папку tg-ws-proxy",self.select_tg_bundle).pack(anchor="w",pady=(10,10))
        self.label(card,"Python (py, python или полный путь к python.exe)",10,TEXT).pack(anchor="w")
        self.tg_python=tk.StringVar(value=self.settings.telegram_python)
        tk.Entry(card,textvariable=self.tg_python,bg=PANEL2,fg=TEXT,insertbackground=TEXT,
                 relief="flat",font=("Segoe UI",11),width=48).pack(anchor="w",ipady=7,pady=(6,10))
        self.label(card,f"Локальный адрес: 127.0.0.1:{self.settings.telegram_port}",11,ACCENT).pack(anchor="w")
        self.label(card,"Порт изменяется во вкладке «Настройки». Secret сохраняется локально.",10,MUTED).pack(anchor="w",pady=(6,0))
        self._engine_controls(card,self.tg_engine,self.start_telegram,self.stop_telegram,"telegram-engine.log")
        self.button(card,"Открыть ссылку подключения в Telegram",self.open_telegram_link).pack(anchor="w",pady=(15,0))
        self.label(card,"Не используется внешний сервер прокси; исходящий WebSocket-трафик выполняет Flowseal.",10,MUTED).pack(anchor="w",pady=(10,0))

    def select_tg_bundle(self):
        folder=filedialog.askdirectory(title="Папка с proxy/tg_ws_proxy.py")
        if folder:
            self.settings.telegram_source_dir=folder
            try: self._save_engine_settings();self.show_page("Telegram")
            except OSError as exc: messagebox.showerror("Ошибка",str(exc))

    def _ensure_telegram_secret(self):
        if not self.settings.telegram_secret:
            self.settings.telegram_secret=secrets.token_hex(16)
        return self.settings.telegram_secret

    def start_telegram(self):
        if os.name != "nt":
            messagebox.showerror("Только Windows","Эта сборка предназначена для Windows")
            return
        try:
            self.settings.telegram_python=self.tg_python.get().strip()
            secret=self._ensure_telegram_secret()
            spec=build_telegram_spec(self.settings.telegram_source_dir,self.settings.telegram_port,
                                     secret,self.settings.telegram_python)
            if not self.tg_engine.running and not port_is_free(self.settings.telegram_port):
                raise ValueError(f"Порт {self.settings.telegram_port} уже занят")
            self._save_engine_settings()
            pid=self.tg_engine.start(spec,APP_DIR / "telegram-engine.log")
            record_event("telegram_start",f"Telegram запущен PID {pid} на порту {self.settings.telegram_port}")
            self.show_page("Telegram")
        except (OSError,ValueError,RuntimeError) as exc:
            messagebox.showerror("Telegram не запущен",f"{exc}\n\nПроверьте Python, зависимости и журнал.")

    def stop_telegram(self):
        try:
            stopped=self.tg_engine.stop()
            if stopped: record_event("telegram_stop","Локальный Telegram-прокси остановлен")
            self.show_page("Telegram")
        except (OSError,subprocess.TimeoutExpired) as exc:
            messagebox.showerror("Ошибка остановки Telegram",str(exc))

    def open_telegram_link(self):
        if not self.tg_engine.running:
            messagebox.showwarning("Telegram","Сначала запустите прокси и убедитесь, что он работает")
            return
        if not port_is_listening(self.settings.telegram_port):
            messagebox.showwarning("Telegram","Локальный порт пока не отвечает; проверьте журнал прокси")
            return
        try:
            webbrowser.open(proxy_link(self.settings.telegram_port,self.settings.telegram_secret))
        except ValueError as exc:messagebox.showerror("Прокси",str(exc))

    def modules(self):
        self.heading("Сетевые модули", "Ручное управление отдельным исполняемым файлом; для DPI и Telegram есть специальные вкладки")
        card=self.panel(self.main);card.pack(fill="x")
        self.label(card,"Внешний модуль (экспериментально)",15,TEXT,True).pack(anchor="w")
        self.label(card,"Выбирайте только доверенный .exe. Запуск без аргументов и без повышения прав.",10,MUTED).pack(anchor="w",pady=(8,12))
        self.module_path=tk.StringVar(value=getattr(self,"selected_module",None) or self.module_manager.executable or "Файл не выбран")
        self.label(card,self.module_path.get(),10,MUTED).pack(anchor="w",pady=(0,10))
        actions=tk.Frame(card,bg=PANEL);actions.pack(anchor="w")
        self.button(actions,"Выбрать .exe",self.select_module).pack(side="left",padx=(0,8))
        self.button(actions,"Проверить SHA-256",self.inspect_module).pack(side="left",padx=(0,8))
        self.button(actions,"Запустить",self.start_module,True).pack(side="left",padx=(0,8))
        self.button(actions,"Остановить",self.stop_module).pack(side="left")
        state=f"Работает (PID {self.module_manager.pid})" if self.module_manager.running else "Остановлен"
        self.label(card,"Состояние: "+state,11,GREEN if self.module_manager.running else AMBER,True).pack(anchor="w",pady=(15,0))
        self.label(card,"Поддерживаемые адаптеры",13,TEXT,True).pack(anchor="w",pady=(18,8))
        for module in MODULES:
            self.label(card,f"{module.display_name}: {module.detail}",10,MUTED).pack(anchor="w",pady=2)
        self.label(card,"Сохранённые профили",13,TEXT,True).pack(anchor="w",pady=(18,8))
        for profile in self.profiles:
            bar=tk.Frame(card,bg=PANEL);bar.pack(fill="x",pady=3)
            self.label(bar,profile.name,10,TEXT).pack(side="left")
            self.button(bar,"Удалить",lambda p=profile:self.remove_profile(p)).pack(side="right",padx=(8,0))
            self.button(bar,"Выбрать",lambda p=profile:self.use_profile(p)).pack(side="right")
        self.button(card,"Сохранить выбранный .exe как профиль",self.add_profile).pack(anchor="w",pady=(12,0))
        self.label(self.main,"Для Flowseal используйте отдельные вкладки DPI и Telegram.",10,MUTED).pack(anchor="w",pady=14)

    def select_module(self):
        selected=filedialog.askopenfilename(title="Выбрать внешний модуль",filetypes=[("Windows executable","*.exe")])
        if selected:
            self.selected_module=selected
            self.show_page("Модули")

    def inspect_module(self):
        selected=getattr(self,"selected_module",None)
        if not selected:
            messagebox.showwarning("Проверка файла","Сначала выберите файл .exe")
            return
        try:
            item=inspect_file(selected)
            messagebox.showinfo("Контрольная сумма",f"Файл: {item.name}\\nРазмер: {item.size} байт\\nSHA-256:\\n{item.sha256}\\n\\nСравните сумму с официальным источником.")
            record_event("inspect",f"Проверен SHA-256: {item.name}")
        except (OSError,ValueError) as exc:
            messagebox.showerror("Ошибка проверки",str(exc))

    def start_module(self):
        selected=getattr(self,"selected_module",None)
        if not selected:
            messagebox.showwarning("Модуль","Сначала выберите исполняемый файл")
            return
        try:
            pid=self.module_manager.start(selected)
            record_event("start",f"Запущен PID {pid}: {selected}")
            self.show_page("Модули")
        except (OSError,ValueError,RuntimeError) as exc:
            messagebox.showerror("Ошибка запуска",str(exc))

    def stop_module(self):
        try:
            stopped=self.module_manager.stop()
            record_event("stop", "Остановлен внешний модуль" if stopped else "Модуль уже остановлен")
            self.show_page("Модули")
        except (OSError,subprocess.TimeoutExpired) as exc:
            messagebox.showerror("Ошибка остановки",str(exc))

    def use_profile(self, profile):
        self.selected_module=profile.executable
        self.show_page("Модули")

    def add_profile(self):
        selected=getattr(self,"selected_module",None)
        if not selected:
            messagebox.showwarning("Профили","Сначала выберите .exe")
            return
        name=simpledialog.askstring("Новый профиль","Название профиля:",parent=self)
        if name is None:
            return
        try:
            profile=validate_profile(name,selected)
            save_profiles([*self.profiles,profile])
            self.profiles=load_profiles()
            record_event("profile",f"Добавлен профиль {profile.name}")
            self.show_page("Модули")
        except (OSError,ValueError) as exc:
            messagebox.showerror("Ошибка профиля",str(exc))

    def remove_profile(self, profile):
        if not messagebox.askyesno("Удаление профиля",f"Удалить профиль «{profile.name}»?"):
            return
        try:
            updated=[p for p in self.profiles if p.name != profile.name]
            save_profiles(updated)
            self.profiles=updated
            record_event("profile",f"Удалён профиль {profile.name}")
            self.show_page("Модули")
        except OSError as exc:
            messagebox.showerror("Ошибка удаления",str(exc))

    def events_page(self):
        self.heading("Журнал событий","Локальная история запуска и остановки модулей")
        items=recent_events()
        if not items:
            self.label(self.main,"Событий пока нет",11,MUTED).pack(anchor="w")
        for item in items:
            card=self.panel(self.main,14,9);card.pack(fill="x",pady=3)
            self.label(card,f"{item.get('timestamp','')[:19]}  ·  {item.get('action','')}",10,ACCENT,True).pack(anchor="w")
            self.label(card,str(item.get("message",""))[:180],9,MUTED).pack(anchor="w")

    def destroy(self):
        try:
            for engine in (self.dpi_engine,self.tg_engine,self.module_manager):
                try: engine.close()
                except (OSError,subprocess.TimeoutExpired): pass
        finally:super().destroy()

    def preferences(self):
        self.heading("Настройки","Локальные параметры приложения")
        card=self.panel(self.main);card.pack(fill="x")
        self.label(card,"Порт локального Telegram-прокси",12,TEXT,True).pack(anchor="w")
        self.label(card,"Диапазон 1024–65535. Изменение применяется при следующем запуске прокси.",10,MUTED).pack(anchor="w",pady=(6,12))
        self.port=tk.StringVar(value=str(self.settings.telegram_port))
        tk.Entry(card,textvariable=self.port,bg=PANEL2,fg=TEXT,insertbackground=TEXT,relief="flat",
                 font=("Segoe UI",12),width=14).pack(anchor="w",ipady=9)
        self.button(card,"Сохранить настройки",self.save,True).pack(anchor="w",pady=(18,0))
        self.label(self.main,"Параметры хранятся в профиле пользователя Windows.",10,MUTED).pack(anchor="w",pady=16)

    def about(self):
        self.heading("О VORQELI Connect","Информация о проекте")
        card=self.panel(self.main);card.pack(fill="x")
        self.label(card,"◆  VORQELI CONNECT",20,ACCENT,True).pack(anchor="w")
        self.label(card,"Версия 0.10.0  •  Предварительная сборка",11,MUTED).pack(anchor="w",pady=(12,18))
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

    def start_network_scan(self):
        if self.checking:return
        self.checking=True
        if self.current_page!="Диагностика":self.show_page("Диагностика")
        self.scan_btn.configure(state="disabled",text="Проверка...")
        self.status.configure(text="Проверка DNS и TCP:443...")
        for lbl in self.status_labels.values():lbl.configure(text="Проверяется...",fg=MUTED)
        threading.Thread(target=self._network_worker,daemon=True).start()

    def _network_worker(self):
        try:self.events.put(("network_results",check_network()))
        except Exception as exc:self.events.put(("error",str(exc)))

    def _worker(self):
        try:self.events.put(("results",check_all()))
        except Exception as exc:self.events.put(("error",str(exc)))

    def _poll(self):
        try:
            while True:
                kind,payload=self.events.get_nowait();self.checking=False
                if kind in ("results","network_results"):
                    self.last_results=payload
                    try: record_scan(payload)
                    except OSError as exc: messagebox.showwarning("История",f"Не удалось сохранить историю: {exc}")
                    if self.current_page=="Диагностика":
                        for name,status in payload:
                            self.status_labels[name].configure(text=status,fg=GREEN if status in ("Доступен","TCP доступен") else AMBER)
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
        data={"app":"VORQELI Connect","version":"0.10.0","exported_at":datetime.now().astimezone().isoformat(),
              "results":dict(self.last_results)}
        try:Path(path).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
        except OSError as exc:messagebox.showerror("Экспорт",str(exc))

def main():ConnectApp().mainloop()
if __name__=="__main__":main()
