"""Supervise only subprocesses started by this application."""
from __future__ import annotations
from pathlib import Path
import subprocess
from typing import Optional
from .engine_adapters import LaunchSpec


class EngineProcess:
    def __init__(self, label: str):
        self.label = label
        self._proc: Optional[subprocess.Popen] = None
        self._log_handle = None

    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    @property
    def pid(self) -> int | None:
        return self._proc.pid if self.running else None

    @property
    def exit_code(self) -> int | None:
        return None if self._proc is None else self._proc.poll()

    def start(self, spec: LaunchSpec, log_path: Path) -> int:
        if self.running:
            raise RuntimeError(f"{self.label} уже запущен")
        if self._log_handle:
            self._log_handle.close()
            self._log_handle = None
        log_path.parent.mkdir(parents=True, exist_ok=True)
        # Binary log capture: no stdout pipe to deadlock and no unbounded event-list memory.
        log = log_path.open("ab")
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            process = subprocess.Popen(
                list(spec.argv), cwd=str(spec.cwd), stdin=subprocess.DEVNULL,
                stdout=log, stderr=subprocess.STDOUT, shell=False,
                creationflags=flags,
            )
        except Exception:
            log.close()
            raise
        self._log_handle = log
        self._proc = process
        return process.pid

    def stop(self, timeout: float = 5) -> bool:
        if not self.running:
            self._close_log()
            return False
        self._proc.terminate()
        try:
            self._proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self._proc.kill()
            self._proc.wait(timeout=timeout)
        self._close_log()
        return True

    def _close_log(self):
        if self._log_handle:
            self._log_handle.close()
            self._log_handle = None

    def close(self):
        self.stop()
