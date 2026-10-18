"""Small privacy-preserving diagnostics export for user-initiated bug reports.

No logs, secrets, usernames, absolute paths, host/IP addresses or registry data.
"""
from __future__ import annotations
from datetime import datetime, timezone
from .config import Settings
from .unified import ConnectionReport

_SAFE_SCAN_STATES = {'Доступен', 'Нет ответа', 'Не проверено'}
_SAFE_MODULE_STATES = {'on', 'off', 'error'}
_SAFE_OVERALL_STATES = {'connected', 'partial', 'off', 'error'}


def build_report(settings: Settings, status: ConnectionReport,
                 results: list[tuple[str, str]], version: str) -> dict:
    """Allow only known enumerated states; raw diagnostic text may contain PII."""
    return {
        'schema_version': 1,
        'app_version': str(version),
        'captured_at': datetime.now(timezone.utc).isoformat(),
        'desired_enabled': bool(settings.desired_enabled),
        'launch_at_startup_requested': bool(settings.launch_at_startup),
        'dpi_mode': settings.dpi_mode if settings.dpi_mode in ('fake', 'multisplit', 'auto') else 'unknown',
        'geohide_transport': settings.dns_mode if settings.dns_mode in ('plain', 'doh') else 'unknown',
        'components': {
            'dpi': {'enabled': bool(settings.connect_dpi),
                    'state': status.dpi if status.dpi in _SAFE_MODULE_STATES else 'unknown'},
            'telegram': {'enabled': bool(settings.connect_telegram),
                         'state': status.telegram if status.telegram in _SAFE_MODULE_STATES else 'unknown'},
            'dns': {'enabled': bool(settings.connect_dns),
                    'state': status.dns if status.dns in _SAFE_MODULE_STATES else 'unknown'},
        },
        'overall': status.overall if status.overall in _SAFE_OVERALL_STATES else 'unknown',
        'checks': {str(label)[:32]: result if result in _SAFE_SCAN_STATES else 'Другой результат'
                   for label, result in results[:10] if label in ('Discord', 'YouTube', 'Telegram', 'GitHub')},
        'notice': 'Не является подтверждением успешного обхода DPI или DNS/Telegram-трафика.',
    }
