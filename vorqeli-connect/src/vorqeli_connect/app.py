"""Minimal Windows desktop shell for independently developed connectivity modules."""
import queue
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from .config import load_settings, save_settings
from .diagnostics import check_all, SERVICES

BG = "#0d111b"
SURFACE = "#171d2b"
FOREGROUND = "#f4f2ff"
MUTED = "#a6aabd"
PURPLE = "#ab98ff"


class ConnectApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("VORQELI Connect • 0.2.0")
        self.geometry("760x620")
        self.minsize(680, 560)
        self.configure(bg=BG)
        self.settings = load_settings()
        self.results = queue.Queue()
        self.status_labels: dict[str, tk.Label] = {}
        self._build_ui()
        self.after(150, self._poll_results)

    def _label(self, parent, text, size=12, color=FOREGROUND, weight="normal"):
        return tk.Label(parent, text=text, bg=parent.cget("bg"), fg=color,
                        font=("Segoe UI", size, weight), anchor="w")

    def _build_ui(self):
        outer = tk.Frame(self, bg=BG, padx=28, pady=24)
        outer.pack(fill="both", expand=True)
        self._label(outer, "◆  VORQELI CONNECT", 21, PURPLE, "bold").pack(anchor="w")
        self._label(outer, "Центр управления сетевыми подключениями", 11, MUTED).pack(anchor="w", pady=(4, 20))
        panel = tk.Frame(outer, bg=SURFACE, padx=18, pady=16)
        panel.pack(fill="x")
        self._label(panel, "Модули", 15, FOREGROUND, "bold").pack(anchor="w")
        self._label(panel, "DPI-стратегии: ожидается настройка сетевого движка", 11, MUTED).pack(anchor="w", pady=(8, 3))
        self._label(panel, "Telegram: ожидается подключение локального MTProto-модуля", 11, MUTED).pack(anchor="w", pady=(3, 4))
        self._label(panel, "На этой стадии приложение не изменяет сетевые параметры Windows.", 10, PURPLE).pack(anchor="w", pady=(8, 0))
        settings_frame = tk.Frame(outer, bg=BG)
        settings_frame.pack(fill="x", pady=(18, 14))
        self._label(settings_frame, "Порт Telegram-прокси (для будущего модуля)", 11, MUTED).pack(anchor="w")
        row = tk.Frame(settings_frame, bg=BG)
        row.pack(fill="x", pady=(7, 0))
        self.port_var = tk.StringVar(value=str(self.settings.telegram_port))
        tk.Entry(row, textvariable=self.port_var, bg=SURFACE, fg=FOREGROUND,
                 insertbackground=FOREGROUND, relief="flat", width=14, font=("Segoe UI", 12)).pack(side="left", ipady=8)
        tk.Button(row, text="Сохранить", command=self._save, bg=PURPLE, fg=BG,
                  relief="flat", font=("Segoe UI", 11, "bold"), padx=16, pady=6).pack(side="left", padx=12)
        diag = tk.Frame(outer, bg=SURFACE, padx=18, pady=16)
        diag.pack(fill="both", expand=True)
        head = tk.Frame(diag, bg=SURFACE)
        head.pack(fill="x")
        self._label(head, "Диагностика сервисов", 15, FOREGROUND, "bold").pack(side="left")
        self.scan_button = tk.Button(head, text="Проверить", command=self._scan,
                                     bg=PURPLE, fg=BG, relief="flat", padx=14, pady=5,
                                     font=("Segoe UI", 10, "bold"))
        self.scan_button.pack(side="right")
        for service in SERVICES:
            line = tk.Frame(diag, bg=SURFACE)
            line.pack(fill="x", pady=11)
            self._label(line, service, 12).pack(side="left")
            result = self._label(line, "Не проверено", 11, MUTED)
            result.pack(side="right")
            self.status_labels[service] = result
        self._label(outer, "VORQELI Connect 0.2.0 • независимый прототип • Windows", 9, MUTED).pack(anchor="w", pady=(18, 0))

    def _save(self):
        try:
            port = int(self.port_var.get())
            if not 1024 <= port <= 65535:
                raise ValueError()
            self.settings.telegram_port = port
            save_settings(self.settings)
            messagebox.showinfo("VORQELI Connect", "Настройки сохранены")
        except ValueError:
            messagebox.showerror("Ошибка", "Введите порт от 1024 до 65535")
        except OSError as exc:
            messagebox.showerror("Ошибка сохранения", str(exc))

    def _scan(self):
        self.scan_button.configure(state="disabled", text="Проверка...")
        for label in self.status_labels.values():
            label.configure(text="Проверяется", fg=MUTED)
        threading.Thread(target=self._scan_worker, daemon=True).start()

    def _scan_worker(self):
        try:
            self.results.put(("ok", check_all()))
        except Exception as exc:
            self.results.put(("error", str(exc)))

    def _poll_results(self):
        try:
            while True:
                kind, data = self.results.get_nowait()
                if kind == "ok":
                    for name, status in data:
                        self.status_labels[name].configure(
                            text=status, fg="#82d8b2" if status == "Доступен" else "#ffbb82")
                else:
                    messagebox.showerror("Ошибка диагностики", data)
                self.scan_button.configure(state="normal", text="Проверить")
        except queue.Empty:
            pass
        self.after(150, self._poll_results)


def main():
    ConnectApp().mainloop()

if __name__ == "__main__":
    main()
