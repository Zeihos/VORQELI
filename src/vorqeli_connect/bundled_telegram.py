"""Start the upstream Flowseal proxy inside the same packaged executable.

Only the proxy core is invoked, not upstream GUI or tray. The upstream source is
installed and bundled by the Windows CI workflow at a pinned Git commit.
"""
from __future__ import annotations
import importlib.util
import os
import secrets
import sys
from pathlib import Path
from .engine_adapters import LaunchSpec, validate_proxy_settings


def proxy_available() -> bool:
    try:
        return importlib.util.find_spec('proxy.tg_ws_proxy') is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def build_worker_spec(port: int) -> LaunchSpec:
    if not proxy_available():
        raise RuntimeError('Сборка не содержит tg-ws-proxy. Переустановите полную версию VORQELI из GitHub Actions.')
    validate_proxy_settings(port, 'a'*32)
    if getattr(sys, 'frozen', False):
        args = (sys.executable, '--tg-worker', '--port', str(port))
    else:
        args = (sys.executable, '-m', 'vorqeli_connect', '--tg-worker', '--port', str(port))
    return LaunchSpec(args, Path(sys.executable).resolve().parent, 'Telegram · Flowseal')


def start_worker(port: int) -> None:
    """Executed only in the --tg-worker child process, never in the GUI."""
    import sys
    secret = os.environ.pop('VORQELI_TG_SECRET', '')
    validate_proxy_settings(port, secret)
    sys.argv = ['tg-ws-proxy', '--host', '127.0.0.1', '--port', str(port), '--secret', secret]
    from proxy.tg_ws_proxy import main
    main()
