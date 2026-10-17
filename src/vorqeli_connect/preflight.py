"""Preflight checks for manually installed Flowseal dependencies.

All checks are read-only. A PASS never claims the external engine will work.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from .engine_adapters import build_dpi_spec, build_telegram_spec, port_is_free


@dataclass(frozen=True)
class Check:
    label: str
    passed: bool
    detail: str


def check_dpi(folder: str, mode: str = "fake") -> list[Check]:
    """Ensure local source files exist and a command can be prepared."""
    try:
        spec = build_dpi_spec(folder, mode)
    except (OSError, ValueError) as exc:
        return [Check("Пакет DPI", False, str(exc))]
    return [
        Check("Файлы DPI", True, "winws.exe, hostlist и LICENSE.txt найдены"),
        Check("Режим запуска", True, f"Подготовлена экспериментальная стратегия {mode}"),
        Check("Папка запуска", True, str(spec.cwd)),
    ]


def check_telegram(folder: str, port: int, secret: str,
                   python_executable: str = "", *, port_busy_ok: bool = False) -> list[Check]:
    """Check source, Python command and TCP binding eligibility without starting a proxy."""
    try:
        spec = build_telegram_spec(folder, port, secret, python_executable)
    except (OSError, ValueError) as exc:
        return [Check("Telegram-прокси", False, str(exc))]
    # Deliberately do NOT display the generated command; it embeds a secret.
    checks = [Check("Исходники и Python", True,
                    f"Исходники и интерпретатор найдены ({Path(spec.argv[0]).name})")]
    try:
        available = port_is_free(port)
    except (OSError, ValueError) as exc:
        return checks + [Check("Локальный порт", False, str(exc))]
    if available:
        checks.append(Check("Локальный порт", True, f"127.0.0.1:{port} свободен"))
    elif port_busy_ok:
        checks.append(Check("Локальный порт", True,
                            f"127.0.0.1:{port} занят; VORQELI запустил процесс, но принадлежность порта не подтверждена"))
    else:
        checks.append(Check("Локальный порт", False,
                            f"127.0.0.1:{port} занят другим процессом"))
    return checks


def checks_ok(checks: list[Check]) -> bool:
    return bool(checks) and all(item.passed for item in checks)


def format_checks(checks: list[Check]) -> str:
    return "\n\n".join(
        f"{'✓' if item.passed else '✗'} {item.label}\n{item.detail}"
        for item in checks
    )
