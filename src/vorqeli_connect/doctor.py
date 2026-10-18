"""Local, read-only installation diagnostics for Windows acceptance testing.

Do NOT include network adapters, usernames, file paths, environment values,
proxy secrets, DNS addresses or process command lines in the JSON report.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

from .config import APP_DIR, Settings, load_settings


def create_report(settings: Settings, *, is_windows: bool, admin: bool,
                  tray_available: bool, telegram_available: bool,
                  dpi_available: bool, dns_backup_present: bool,
                  dpi_integrity: str = 'unknown',
                  startup_mode: str = 'unknown',
                  doh_recovery_pending: bool = False,
                  off_intent_guard: bool = False) -> dict:
    """Return only non-sensitive booleans and enumerated status values."""
    if startup_mode not in {'task', 'registry', 'conflict', 'missing', 'unknown', 'unsupported', 'untrusted'}:
        startup_mode = 'unknown'
    if dpi_integrity not in ('verified', 'missing', 'legacy', 'tampered', 'unknown'):
        dpi_integrity = 'unknown'
    return {
        'schema': 1,
        'platform': 'windows' if is_windows else 'other',
        'administrator': bool(admin),
        'desired_connection': 'on' if settings.desired_enabled else 'off',
        'modules_selected': {
            'dpi': bool(settings.connect_dpi),
            'telegram': bool(settings.connect_telegram),
            'geohide_dns': bool(settings.connect_dns),
        },
        'components_available': {
            'dpi_files': bool(dpi_available),
            'telegram_python_module': bool(telegram_available),
            'tray_library': bool(tray_available),
        },
        'dns_recovery_pending': bool(dns_backup_present),
        'geohide_transport': settings.dns_mode if settings.dns_mode in ('plain', 'doh') else 'unknown',
        'doh_recovery_pending': bool(doh_recovery_pending),
        'dpi_integrity': dpi_integrity,
        'startup_preference': bool(settings.launch_at_startup),
        'explicit_off_guard': bool(off_intent_guard),
        'startup_registration': startup_mode,
        'telegram_secret_status': ('unreadable' if settings.telegram_secret_error else
                                   'configured' if settings.telegram_secret else 'missing'),
        'disclaimer': 'Проверка файлов/настроек НЕ доказывает работу обхода DPI или доступность Telegram.',
    }


def startup_registration() -> str:
    """Read only a sanitised enum from the Windows startup controller."""
    from .startup import registration_status
    return registration_status()


def collect_report(settings: Settings | None = None) -> dict:
    from .assets_manager import engine_cache_root, engine_integrity
    from .startup import is_admin
    from .geohide import STATE_FILE
    from .geohide_doh import DOH_STATE_FILE
    from .bundled_telegram import proxy_available
    from .config import off_intent_path
    if settings is None:
        settings = load_settings()
    root = engine_cache_root() / 'zapret-1.10.3'
    return create_report(
        settings,
        is_windows=os.name == 'nt',
        admin=is_admin(),
        tray_available=importlib.util.find_spec('pystray') is not None,
        telegram_available=proxy_available(),
        dpi_available=(root / 'bin/winws.exe').is_file() and
                      (root / 'lists/list-general.txt').is_file() and
                      (root / 'LICENSE.txt').is_file(),
        dns_backup_present=STATE_FILE.is_file() or DOH_STATE_FILE.is_file(),
        doh_recovery_pending=DOH_STATE_FILE.is_file(),
        dpi_integrity=engine_integrity(root),
        startup_mode=startup_registration(),
        off_intent_guard=off_intent_path().exists(),
    )


def print_diagnostic(output: str | Path | None = None) -> Path | None:
    """Write JSON to file for --windowed EXEs (no stdout), or print in console.

    Explicit output path is intended for automated Windows acceptance checks.
    Creating the report does not start DPI, Telegram or change DNS.
    """
    payload = json.dumps(collect_report(), ensure_ascii=False, sort_keys=True, indent=2)
    if output is None and sys.stdout is not None:
        print(payload)
        return None
    location = Path(output) if output is not None else APP_DIR / 'doctor-report.json'
    location.parent.mkdir(parents=True, exist_ok=True)
    location.write_text(payload + '\n', encoding='utf-8')
    return location

