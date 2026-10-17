"""Single-action connect/disconnect for DPI, Telegram and optional GeoHide DNS.

No background global process killing. All engine processes are owned by VORQELI.
Desired connection state is persisted separately from observed runtime health.
"""
from __future__ import annotations
import os
import secrets
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from .assets_manager import ensure_zapret
from .bundled_telegram import build_worker_spec
from .config import APP_DIR, Settings, save_settings
from .engine_adapters import build_dpi_spec, port_is_free, port_is_listening
from .engine_processes import EngineProcess
from .geohide import enable_dns, restore_dns, STATE_FILE
from .startup import configure_startup


@dataclass(frozen=True)
class ConnectionReport:
    overall: str
    dpi: str
    telegram: str
    dns: str
    detail: str = ''


class UnifiedController:
    def __init__(self, settings: Settings, *, emit: Callable[[str, object], None] | None = None,
                 assets=ensure_zapret, dns_on=enable_dns, dns_off=restore_dns,
                 startup=configure_startup):
        self.settings = settings
        self.emit = emit or (lambda name, value: None)
        self.dpi = EngineProcess('DPI')
        self.telegram = EngineProcess('Telegram')
        self.assets = assets
        self.dns_on = dns_on
        self.dns_off = dns_off
        self.startup = startup
        self._lock = threading.Lock()
        self._cancel = threading.Event()
        self._connecting = False
        self._dns_managed = False
        self._last = ConnectionReport('off','off','off','off')

    def status(self) -> ConnectionReport:
        return self._last

    def _send(self, message: str):
        self.emit('progress', message)

    def connect(self) -> ConnectionReport:
        self._cancel.clear()
        self.settings.desired_enabled = True
        save_settings(self.settings)
        with self._lock:
            self._connecting = True
            errors: list[str] = []
            states = {'dpi': 'off', 'telegram': 'off', 'dns': 'off'}
            try:
                if self.settings.launch_at_startup and os.name == 'nt':
                    try:
                        mode = self.startup(True)
                        if mode == 'registry' and (self.settings.connect_dpi or self.settings.connect_dns):
                            errors.append('Автозапуск добавлен, но без повышенных прав: для DPI/DNS может понадобиться UAC.')
                    except Exception as exc:
                        errors.append(f'Автозапуск: {exc}')
                if self._cancel.is_set():
                    return self._cancelled()
                if self.settings.connect_dpi:
                    try:
                        self._send('Подготавливаем DPI-движок…')
                        bundle = self.assets(progress=self._send)
                        if self._cancel.is_set():
                            return self._cancelled()
                        spec = build_dpi_spec(bundle, self.settings.dpi_mode)
                        if not self.dpi.running:
                            self.dpi.start(spec, APP_DIR / 'dpi-engine.log')
                        time.sleep(.45)
                        if not self.dpi.running:
                            raise RuntimeError('DPI-процесс завершился сразу после запуска; откройте журнал.')
                        states['dpi'] = 'on'
                    except Exception as exc:
                        states['dpi'] = 'error'
                        errors.append(f'DPI: {exc}')
                if self._cancel.is_set():
                    return self._cancelled()
                if self.settings.connect_telegram:
                    try:
                        self._send('Запускаем локальный Telegram-прокси…')
                        if not self.settings.telegram_secret:
                            self.settings.telegram_secret = secrets.token_hex(16)
                            save_settings(self.settings)
                        spec = build_worker_spec(self.settings.telegram_port)
                        if not self.telegram.running:
                            if not port_is_free(self.settings.telegram_port):
                                raise RuntimeError('Локальный порт Telegram уже занят')
                            env = {**os.environ, 'VORQELI_TG_SECRET': self.settings.telegram_secret}
                            self.telegram.start(spec, APP_DIR / 'telegram-engine.log', env=env)
                        for _ in range(12):
                            if not self.telegram.running:
                                raise RuntimeError('Telegram-процесс неожиданно завершился; откройте журнал.')
                            if port_is_listening(self.settings.telegram_port):
                                break
                            if self._cancel.is_set():
                                return self._cancelled()
                            time.sleep(.25)
                        if not port_is_listening(self.settings.telegram_port):
                            raise RuntimeError('Порт 127.0.0.1 не открылся')
                        states['telegram'] = 'on'
                    except Exception as exc:
                        states['telegram'] = 'error'
                        errors.append(f'Telegram: {exc}')
                        try: self.telegram.stop()
                        except OSError: pass
                if self._cancel.is_set():
                    return self._cancelled()
                if self.settings.connect_dns:
                    try:
                        self._send('Подключаем GeoHide DNS…')
                        self.dns_on()
                        self._dns_managed = True
                        states['dns'] = 'on'
                    except Exception as exc:
                        states['dns'] = 'error'
                        errors.append(f'GeoHide: {exc}')
                successful = sum(1 for state in states.values() if state == 'on')
                selected = sum((self.settings.connect_dpi, self.settings.connect_telegram, self.settings.connect_dns))
                overall = 'connected' if selected and successful == selected and not errors else ('partial' if successful else 'error')
                self._last = ConnectionReport(overall, **states, detail='\n'.join(errors))
                self.emit('state', self._last)
                return self._last
            finally:
                self._connecting = False

    def _cancelled(self):
        self._last = ConnectionReport('off','off','off','off', 'Подключение отменено')
        self.emit('state', self._last)
        return self._last

    def disconnect(self, *, remember: bool = True) -> ConnectionReport:
        # Persist OFF at once even if a download is still running.
        self._cancel.set()
        if remember:
            self.settings.desired_enabled = False
            save_settings(self.settings)
        with self._lock:
            errors = []
            for name, engine in (('DPI', self.dpi), ('Telegram', self.telegram)):
                try:
                    engine.stop()
                except Exception as exc:
                    errors.append(f'{name}: {exc}')
            if self._dns_managed or STATE_FILE.exists():
                try:
                    self.dns_off()
                    self._dns_managed = False
                except Exception as exc:
                    errors.append(f'DNS: {exc}')
            self._last = ConnectionReport('off' if not errors else 'error', 'off','off',
                                          'off' if not errors else 'error', '\n'.join(errors))
            self.emit('state', self._last)
            return self._last

    def runtime_health(self) -> ConnectionReport:
        """Observed status, separate from user's persisted desired switch."""
        dpi = 'on' if self.dpi.running else ('error' if self.settings.connect_dpi and self.settings.desired_enabled else 'off')
        tg = ('on' if self.telegram.running and port_is_listening(self.settings.telegram_port)
              else ('error' if self.settings.connect_telegram and self.settings.desired_enabled else 'off'))
        dns = 'on' if STATE_FILE.is_file() else 'off'
        previous = self._last
        if previous.overall in ('off','error') and not self.settings.desired_enabled:
            return previous
        if previous.overall == 'connected' and (
              (self.settings.connect_dpi and dpi != 'on') or
              (self.settings.connect_telegram and tg != 'on') or
              (self.settings.connect_dns and dns != 'on')):
            self._last = ConnectionReport('partial',dpi,tg,dns,'Один из компонентов перестал отвечать')
        return self._last
