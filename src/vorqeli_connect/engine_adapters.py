"""Launch adapters for user-provided Flowseal engines.

No bundled binaries, automatic downloads, privileges, shell commands or service edits.
Each engine runs with a controlled argument list and working directory.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import re
import shutil
import socket
from urllib.parse import urlencode
from .flowseal_alts import ALT_MODES, build_alt_arguments


VALID_DPI_MODES = {"fake": "fake", "multisplit": "multisplit",
                   **{mode: mode for mode in ALT_MODES}}


@dataclass(frozen=True)
class LaunchSpec:
    argv: tuple[str, ...]
    cwd: Path
    label: str


def _bundle_dir(folder: str | Path) -> Path:
    if not str(folder).strip():
        raise ValueError("Выберите распакованную папку Flowseal zapret")
    root = Path(folder).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Папка zapret не найдена")
    return root


def build_dpi_spec(folder: str | Path, mode: str = "fake") -> LaunchSpec:
    """Build an experimental TCP host-list strategy, not a Flowseal .bat preset."""
    root = _bundle_dir(folder)
    if mode not in VALID_DPI_MODES:
        raise ValueError("Неизвестная DPI-стратегия")
    executable = root / "bin" / "winws.exe"
    hostlist = root / "lists" / "list-general.txt"
    if not executable.is_file() or not hostlist.is_file():
        raise ValueError("Не найдены bin/winws.exe и lists/list-general.txt")
    if not (root / "LICENSE.txt").is_file():
        raise ValueError("Нет LICENSE.txt: выберите оригинальный пакет Flowseal")
    if mode in ALT_MODES:
        return LaunchSpec((str(executable), *build_alt_arguments(root, mode)),
                          root / "bin", f"Flowseal {mode.upper()}")
    args = [str(executable), "--wf-tcp=80,443", "--filter-tcp=80,443",
            f"--hostlist={hostlist}", f"--dpi-desync={mode}"]
    if mode == "fake":
        args += ["--dpi-desync-repeats=6"]
    else:
        args += ["--dpi-desync-split-pos=1"]
    return LaunchSpec(tuple(args), root / "bin", f"DPI: {mode}")


def _python_command(python_executable: str | Path) -> tuple[str, ...]:
    candidate = str(python_executable).strip()
    if not candidate:
        candidate = "py" if os.name == "nt" and shutil.which("py") else "python"
    # Deliberately accept only an executable path OR command (no extra flags).
    if not re.fullmatch(r"[\w.\-]+", candidate):
        path = Path(candidate).expanduser().resolve(strict=True)
        if not path.is_file() or path.suffix.lower() != ".exe":
            raise ValueError("Укажите путь к python.exe или команду py/python")
        return (str(path),)
    if candidate.casefold() not in {"py", "python", "python3", "python.exe", "python3.exe"}:
        raise ValueError("Используйте py, python или полный путь к python.exe")
    found = shutil.which(candidate)
    if not found:
        raise ValueError(f"Python не найден в PATH: {candidate}")
    return (found, "-3") if candidate.casefold() == "py" else (found,)


def validate_proxy_settings(port: int, secret: str) -> tuple[int, str]:
    if isinstance(port, bool) or not isinstance(port, int) or not 1024 <= port <= 65535:
        raise ValueError("Порт Telegram должен быть от 1024 до 65535")
    if not isinstance(secret, str) or re.fullmatch(r"[0-9a-fA-F]{32}", secret) is None:
        raise ValueError("Secret должен содержать 32 шестнадцатеричных символа")
    return port, secret.lower()


def build_telegram_spec(folder: str | Path, port: int, secret: str,
                        python_executable: str = "") -> LaunchSpec:
    """Run Flowseal console proxy from local source checkout (requires dependencies)."""
    root = Path(folder).expanduser().resolve(strict=True) if str(folder).strip() else None
    if root is None or not root.is_dir() or not (root / "proxy" / "tg_ws_proxy.py").is_file():
        raise ValueError("Выберите папку tg-ws-proxy с proxy/tg_ws_proxy.py")
    if not (root / "LICENSE").is_file():
        raise ValueError("В исходниках tg-ws-proxy отсутствует LICENSE")
    port, secret = validate_proxy_settings(port, secret)
    prefix = _python_command(python_executable)
    argv = (*prefix, "-m", "proxy.tg_ws_proxy", "--host", "127.0.0.1",
            "--port", str(port), "--secret", secret)
    return LaunchSpec(argv, root, "Telegram MTProto proxy")


def proxy_link(port: int, secret: str) -> str:
    port, secret = validate_proxy_settings(port, secret)
    return "tg://proxy?" + urlencode({"server": "127.0.0.1", "port": port, "secret": secret})


def port_is_free(port: int, host: str = "127.0.0.1") -> bool:
    """Check just before launch. Race is unavoidable; proxy handles actual bind errors."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((host, port))
        except OSError:
            return False
        return True


def port_is_listening(port: int, host: str = "127.0.0.1") -> bool:
    """TCP readiness probe; this does not validate Telegram protocol reachability."""
    if not isinstance(port, int) or not 1 <= port <= 65535:
        return False
    try:
        with socket.create_connection((host, port), timeout=0.25):
            return True
    except OSError:
        return False
