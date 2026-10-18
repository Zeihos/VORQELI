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
from .smart_dpi import select_strategy, SelectionCancelled
from .geohide import enable_dns, restore_dns, STATE_FILE
from .geohide_doh import enable_geo_dns, restore_geo_dns, DOH_STATE_FILE
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
        # Keep dependency injection compatible with offline controller tests.
        self.dns_on = (lambda: enable_geo_dns(mode=self.settings.dns_mode)) if dns_on is enable_dns else dns_on
        self.dns_off = restore_geo_dns if dns_off is restore_dns else dns_off
        self.startup = startup
        self._lock = threading.Lock()
        self._intent_lock = threading.RLock()
        self._cancel = threading.Event()
        self._connecting = False
        self._dns_managed = False
        self._last = ConnectionReport('off','off','off','off')
        self.active_dpi_mode: str | None = None

    def status(self) -> ConnectionReport:
        return self._last

    def _send(self, message: str):
        self.emit('progress', message)

    def request_connect(self) -> None:
        """Commit ON before activation; rollback the in-memory choice on I/O errors."""
        with self._intent_lock:
            previous = self.settings.desired_enabled
            self.settings.desired_enabled = True
            try:
                save_settings(self.settings)
            except Exception:
                self.settings.desired_enabled = previous
                raise
            self._cancel.clear()

    def connect(self, *, requested: bool = True) -> ConnectionReport:
        """Start components. Queued UI jobs use requested=False to honor later OFF."""
        if requested:
            self.request_connect()
        with self._lock:
            if self._cancel.is_set() or not self.settings.desired_enabled:
                return self._cancelled()
            self._connecting = True
            errors: list[str] = []
            warnings: list[str] = []
            states = {'dpi': 'off', 'telegram': 'off', 'dns': 'off'}
            try:
                if self.settings.launch_at_startup and os.name == 'nt':
                    try:
                        mode = self.startup(True)
                        if mode == 'registry' and (self.settings.connect_dpi or self.settings.connect_dns):
                            warnings.append('Автозапуск без повышенных прав: для DPI/DNS может понадобиться UAC.')
                    except Exception as exc:
                        warnings.append(f'Автозапуск: {exc}')
                if self._cancel.is_set():
                    return self._cancelled()
                if self.settings.connect_dpi:
                    try:
                        self._send('Подготавливаем DPI-движок…')
                        bundle = self.assets(progress=self._send)
                        if self._cancel.is_set():
                            return self._cancelled()
                        if self.settings.dpi_mode == 'auto':
                            # Sequential, bounded probes; manual OFF takes priority.
                            def launch(mode: str) -> None:
                                spec = build_dpi_spec(bundle, mode)
                                self.dpi.start(spec, APP_DIR / 'dpi-engine.log')
                                time.sleep(.45)
                            result = select_strategy(
                                start=launch, stop=self.dpi.stop,
                                running=lambda: self.dpi.running,
                                cancelled=self._cancel.is_set, progress=self._send)
                            self.active_dpi_mode = result.active_mode
                            if result.warning:
                                warnings.append(result.warning)
                        else:
                            self.active_dpi_mode = self.settings.dpi_mode
                            spec = build_dpi_spec(bundle, self.settings.dpi_mode)
                            if not self.dpi.running:
                                self.dpi.start(spec, APP_DIR / 'dpi-engine.log')
                            time.sleep(.45)
                        if not self.dpi.running:
                            raise RuntimeError('DPI-процесс завершился сразу после запуска; откройте журнал.')
                        states['dpi'] = 'on'
                    except Exception as exc:
                        self.active_dpi_mode = None
                        try: self.dpi.stop()
                        except OSError: pass
                        states['dpi'] = 'error'
                        errors.append(f'DPI: {exc}')
                if self._cancel.is_set():
                    return self._cancelled()
                if self.settings.connect_telegram:
                    try:
                        self._send('Запускаем локальный Telegram-прокси…')
                        if self.settings.telegram_secret_error:
                            raise RuntimeError(self.settings.telegram_secret_error)
                        if not self.settings.telegram_secret:
                            self.settings.telegram_secret = secrets.token_hex(16)
                            save_settings(self.settings)
                        spec = build_worker_spec(self.settings.telegram_port)
                        # A live worker without an open listening socket is unhealthy.
                        # Restart only our own child, never terminate a foreign process.
                        if self.telegram.running and not port_is_listening(self.settings.telegram_port):
                            self._send('Локальный прокси не отвечает — перезапускаем свой процесс…')
                            self.telegram.stop()
                        if not self.telegram.running:
                            if not port_is_free(self.settings.telegram_port):
                                raise RuntimeError('Локальный порт Telegram уже занят другой программой')
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
                self._last = ConnectionReport(overall, **states, detail='\n'.join(errors + warnings))
                self.emit('state', self._last)
                return self._last
            finally:
                self._connecting = False

    def _cancelled(self):
        self._last = ConnectionReport('off','off','off','off', 'Подключение отменено')
        self.emit('state', self._last)
        return self._last

    def request_disconnect(self) -> None:
        """Stop pending activations even if writing OFF to disk fails.

        A settings-storage error must *never* keep engines running. The UI
        reports the persistence problem, and disconnect() still stops them.
        """
        with self._intent_lock:
            self._cancel.set()
            self.settings.desired_enabled = False
            save_settings(self.settings)

    def disconnect(self, *, remember: bool = True) -> ConnectionReport:
        """Always stop owned components, even when persisting OFF fails."""
        self._cancel.set()
        errors: list[str] = []
        if remember:
            try:
                self.request_disconnect()
            except Exception as exc:
                # The OFF intent has already been applied in memory; keep going.
                errors.append('Не удалось сохранить ВЫКЛ. (после перезагрузки возможен автозапуск): ' + str(exc))
        with self._lock:
            states = {'dpi': 'off', 'telegram': 'off', 'dns': 'off'}
            self.active_dpi_mode = None
            for key, name, engine in (('dpi', 'DPI', self.dpi), ('telegram', 'Telegram', self.telegram)):
                try:
                    engine.stop()
                    # Detect processes that were not actually stopped.
                    if engine.running:
                        raise RuntimeError('процесс продолжает работать')
                except Exception as exc:
                    states[key] = 'error'
                    errors.append(f'{name}: {exc}')
            if self._dns_managed or STATE_FILE.exists() or DOH_STATE_FILE.exists():
                try:
                    restored = self.dns_off()
                    if restored is False:
                        raise RuntimeError('резервная копия DNS не была восстановлена')
                    self._dns_managed = False
                except Exception as exc:
                    states['dns'] = 'error'
                    errors.append(f'DNS: {exc}')
            self._last = ConnectionReport('off' if not errors else 'error',
                                          **states, detail='\n'.join(errors))
            self.emit('state', self._last)
            return self._last

    def runtime_health(self) -> ConnectionReport:
        """Report observed process/port state, not proof of censorship bypass.

        The DNS state file only indicates managed DNS configuration was applied;
        it does not independently verify resolver functionality on every poll.
        """
        if not self.settings.desired_enabled:
            return self._last
        states = {
            'dpi': ('on' if self.dpi.running else 'error') if self.settings.connect_dpi else 'off',
            'telegram': ('on' if self.telegram.running and port_is_listening(self.settings.telegram_port)
                         else 'error') if self.settings.connect_telegram else 'off',
            'dns': ('on' if STATE_FILE.is_file() and
                    (self.settings.dns_mode == 'plain' or DOH_STATE_FILE.is_file()) else 'error')
                    if self.settings.connect_dns else 'off',
        }
        selected = [key for key, enabled in (
            ('dpi', self.settings.connect_dpi), ('telegram', self.settings.connect_telegram),
            ('dns', self.settings.connect_dns)) if enabled]
        successful = sum(states[k] == 'on' for k in selected)
        overall = ('error' if not selected or successful == 0 else
                   'connected' if successful == len(selected) else 'partial')
        old = self._last
        new_states = (overall, states['dpi'], states['telegram'], states['dns'])
        old_states = (old.overall, old.dpi, old.telegram, old.dns)
        if new_states != old_states:
            bad = [dict(dpi='DPI', telegram='Telegram', dns='GeoHide')[k]
                   for k in selected if states[k] != 'on']
            detail = ('Не работают: ' + ', '.join(bad)) if bad else ''
            self._last = ConnectionReport(*new_states, detail)
        return self._last
